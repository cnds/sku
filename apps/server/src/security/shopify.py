from __future__ import annotations

import base64
import hashlib
import hmac
import inspect
from collections.abc import Awaitable, Callable, Mapping
from functools import wraps
from typing import ParamSpec, TypeVar

from fastapi import HTTPException, Request, status

type SecretResolver = str | Callable[[Request], str]
P = ParamSpec("P")
T = TypeVar("T")

def build_shopify_hmac(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def verify_shopify_hmac(secret: str, body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    expected = build_shopify_hmac(secret, body)
    return hmac.compare_digest(signature, expected)


def build_shopify_oauth_hmac(secret: str, params: Mapping[str, str]) -> str:
    encoded = "&".join(
        f"{key}={value}"
        for key, value in sorted(params.items())
        if key not in {"hmac", "signature"}
    )
    return hmac.new(secret.encode("utf-8"), encoded.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_shopify_oauth_hmac(secret: str, params: Mapping[str, str]) -> bool:
    signature = params.get("hmac")
    if not signature:
        return False
    expected = build_shopify_oauth_hmac(secret, params)
    return hmac.compare_digest(signature, expected)


def shopify_hmac_required(
    secret: SecretResolver,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    def decorator(function: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(function)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            request = _extract_request(args, kwargs)
            resolved_secret = secret(request) if callable(secret) else secret
            body = await request.body()
            signature = request.headers.get("X-Shopify-Hmac-Sha256")

            if not verify_shopify_hmac(resolved_secret, body, signature):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Shopify HMAC signature.",
                )

            return await function(*args, **kwargs)

        wrapper.__signature__ = inspect.signature(function)  # type: ignore[attr-defined]
        return wrapper

    return decorator


def _extract_request(args: tuple[object, ...], kwargs: dict[str, object]) -> Request:
    for value in [*args, *kwargs.values()]:
        if isinstance(value, Request):
            return value
    raise RuntimeError("shopify_hmac_required requires a FastAPI Request argument.")
