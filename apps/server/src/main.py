from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from config import Settings, get_settings
from controllers.router import api_router
from db import (
    create_session_factory,
    db_session_context,
    init_db,
)
from job_queue import close_redis_client, init_redis_client
from logging_utils import configure_logging
from services.diagnosis import DiagnosisNotFoundError
from services.ingest_auth import (
    IngestAuthError,
    IngestRequestExpiredError,
    InvalidIngestTokenError,
    ShopInstallationNotFoundError,
)
from services.job_dispatch import AfterCommitCallbacks
from services.shopify import InvalidShopifyOAuthCallbackError

REQUEST_ID_HEADER = "X-SKU-Lens-Request-Id"
LOGGER = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.sku_lens_log_level)
    session_factory = create_session_factory(resolved_settings.database_url)
    init_redis_client(resolved_settings.redis_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved_settings
        app.state.session_factory = session_factory
        await init_db(session_factory.engine)
        app.state.db_initialized = True
        try:
            yield
        finally:
            await close_redis_client()
            await session_factory.engine.dispose()

    app = FastAPI(
        title="SKU Lens",
        description=(
            "AI Winner & Loser Analysis. "
            "Use AI to audit product pages by tracking component-level engagement "
            "(Size Chart, Reviews, etc.) and quantifying Order Gaps."
        ),
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.session_factory = session_factory
    app.state.db_initialized = False
    app.include_router(api_router)

    @app.exception_handler(DiagnosisNotFoundError)
    async def diagnosis_not_found_handler(
        request: Request,
        exc: DiagnosisNotFoundError,
    ) -> JSONResponse:
        del request
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(IngestAuthError)
    async def ingest_auth_error_handler(
        request: Request,
        exc: IngestAuthError,
    ) -> JSONResponse:
        del request
        status_code = 404 if isinstance(exc, ShopInstallationNotFoundError) else 401
        if not isinstance(
            exc,
            (IngestRequestExpiredError, InvalidIngestTokenError, ShopInstallationNotFoundError),
        ):
            return JSONResponse(
                status_code=401,
                content={"detail": "Ingest authentication failed."},
            )
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    @app.exception_handler(InvalidShopifyOAuthCallbackError)
    async def shopify_oauth_callback_error_handler(
        request: Request,
        exc: InvalidShopifyOAuthCallbackError,
    ) -> JSONResponse:
        del request
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.middleware("http")
    async def db_session_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
        request.state.request_id = request_id
        request.state.after_commit_callbacks = AfterCommitCallbacks()
        await _ensure_db(request)
        started_at = perf_counter()
        request_log_parts = [
            f"request_id={request_id}",
            f"method={request.method}",
            f"path={request.url.path}",
        ]
        product_id = request.path_params.get("product_id") or request.path_params.get("productId")
        if product_id is not None:
            request_log_parts.append(f"product_id={product_id}")
        shop_domain = request.headers.get("X-Shopify-Shop-Domain")
        if shop_domain is not None:
            request_log_parts.append(f"shop_domain={shop_domain}")
        shop_id = request.query_params.get("shop_id") or request.query_params.get("shop")
        if shop_id is not None:
            request_log_parts.append(f"shop_id={shop_id}")
        request_log_context = " ".join(request_log_parts)

        async with db_session_context(request.app.state.session_factory) as session:
            try:
                response = await call_next(request)
            except Exception as exc:
                await session.rollback()
                LOGGER.exception(
                    "request failed %s duration_ms=%s error=%s",
                    request_log_context,
                    int((perf_counter() - started_at) * 1000),
                    exc,
                )
                raise

            response.headers[REQUEST_ID_HEADER] = request_id

            if response.status_code >= 400:
                await session.rollback()
                LOGGER.log(
                    logging.ERROR if response.status_code >= 500 else logging.WARNING,
                    "request completed %s status=%s duration_ms=%s",
                    request_log_context,
                    response.status_code,
                    int((perf_counter() - started_at) * 1000),
                )
                return response

            await session.commit()
            await request.state.after_commit_callbacks.run()
            LOGGER.info(
                "request completed %s status=%s duration_ms=%s",
                request_log_context,
                response.status_code,
                int((perf_counter() - started_at) * 1000),
            )
            return response

    return app


def run() -> None:
    uvicorn.run("main:create_app", access_log=False, factory=True, reload=True)


async def _ensure_db(request: Request) -> None:
    if request.app.state.db_initialized:
        return
    await init_db(request.app.state.session_factory.engine)
    request.app.state.db_initialized = True
