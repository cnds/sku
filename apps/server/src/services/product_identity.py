from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import select

from db import get_db_session
from models import ShopProductIdentity
from schemas import IngestEvent

PRODUCT_GID_PATTERN = re.compile(r"^gid://shopify/Product/(\d+)$")
NUMERIC_PRODUCT_ID_PATTERN = re.compile(r"^\d+$")
HANDLE_PRODUCT_ID_PREFIX = "handle:"


class ProductIdentityService:
    def __init__(self) -> None:
        self._handle_product_ids: dict[tuple[str, str], str] = {}
        self._loaded_handles: set[tuple[str, str]] = set()
        self._learned_handles: set[tuple[str, str]] = set()

    async def resolve_event(
        self,
        *,
        default_source: str | None = None,
        event: IngestEvent,
        shop_id: str,
    ) -> IngestEvent:
        product_id = event.product_id
        context = dict(event.context)
        if default_source is not None and product_id is not None:
            context.setdefault("product_id_source", default_source)

        handle = _resolve_product_handle(product_id=product_id, context=context)
        if handle is not None:
            context.setdefault("product_handle", handle)

        canonical_product_id = normalize_product_id(product_id)
        if canonical_product_id is not None:
            if product_id != canonical_product_id:
                context.setdefault("original_product_id", product_id)
            context.setdefault("product_id_resolution", "canonical")
            await self._learn_identity(
                context=context,
                handle=handle,
                product_id=canonical_product_id,
                shop_id=shop_id,
            )
            return event.model_copy(update={"context": context, "product_id": canonical_product_id})

        if handle is None or product_id is None or not product_id.startswith(HANDLE_PRODUCT_ID_PREFIX):
            return event.model_copy(update={"context": context})

        context.setdefault("original_product_id", product_id)
        resolved_product_id = await self._product_id_for_handle(shop_id=shop_id, handle=handle)
        if resolved_product_id is None:
            context["product_id_resolution"] = "unresolved"
            return event.model_copy(update={"context": context})

        context["product_id_resolution"] = (
            "learned" if (shop_id, handle) in self._learned_handles else "resolved_from_cache"
        )
        return event.model_copy(update={"context": context, "product_id": resolved_product_id})

    async def _learn_identity(
        self,
        *,
        context: dict[str, Any],
        handle: str | None,
        product_id: str,
        shop_id: str,
    ) -> None:
        if handle is None:
            return

        session = get_db_session()
        now = datetime.now(UTC)
        source = _string_or_default(context.get("product_id_source"), default="unknown")
        title = _string_or_none(context.get("product_title"))
        values = {
            "handle": handle,
            "product_id": product_id,
            "shop_id": shop_id,
            "source": source,
            "title": title,
            "updated_at": now,
        }
        update_values = {
            "product_id": product_id,
            "source": source,
            "title": title,
            "updated_at": now,
        }
        table = ShopProductIdentity.__table__
        dialect_name = session.get_bind().dialect.name

        if dialect_name == "mysql":
            statement = mysql_insert(table).values(**values)
            await session.exec(statement.on_duplicate_key_update(**update_values))
        elif dialect_name == "postgresql":
            statement = postgresql_insert(table).values(**values)
            await session.exec(
                statement.on_conflict_do_update(
                    constraint="uq_shop_product_identity_handle",
                    set_=update_values,
                )
            )
        else:
            statement = sqlite_insert(table).values(**values)
            await session.exec(
                statement.on_conflict_do_update(
                    index_elements=["shop_id", "handle"],
                    set_=update_values,
                )
            )

        key = (shop_id, handle)
        self._handle_product_ids[key] = product_id
        self._loaded_handles.add(key)
        self._learned_handles.add(key)

    async def _product_id_for_handle(self, *, handle: str, shop_id: str) -> str | None:
        key = (shop_id, handle)
        if key in self._handle_product_ids:
            return self._handle_product_ids[key]
        if key in self._loaded_handles:
            return None

        session = get_db_session()
        statement = select(ShopProductIdentity).where(
            ShopProductIdentity.shop_id == shop_id,
            ShopProductIdentity.handle == handle,
        )
        identity = (await session.exec(statement)).first()
        self._loaded_handles.add(key)
        if identity is None:
            return None

        self._handle_product_ids[key] = identity.product_id
        return identity.product_id


def normalize_product_id(product_id: str | None) -> str | None:
    if product_id is None:
        return None

    text = product_id.strip()
    if NUMERIC_PRODUCT_ID_PATTERN.fullmatch(text):
        return text

    match = PRODUCT_GID_PATTERN.fullmatch(text)
    if match is not None:
        return match.group(1)

    return None


def _resolve_product_handle(*, context: dict[str, Any], product_id: str | None) -> str | None:
    from_context = _normalize_handle(context.get("product_handle"))
    if from_context is not None:
        return from_context

    if product_id is None or not product_id.startswith(HANDLE_PRODUCT_ID_PREFIX):
        return None

    return _normalize_handle(product_id[len(HANDLE_PRODUCT_ID_PREFIX) :])


def _normalize_handle(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if text.startswith(HANDLE_PRODUCT_ID_PREFIX):
        text = text[len(HANDLE_PRODUCT_ID_PREFIX) :]
    text = text.strip().strip("/")
    return text or None


def _string_or_default(value: object, *, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
