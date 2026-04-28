from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

import db


@pytest.fixture
def sqlite_database_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'sku_lens.db'}"


@pytest.fixture
def redis_url() -> str:
    return "redis://localhost:6379/15"


@pytest_asyncio.fixture(autouse=True)
async def dispose_test_engines(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[None]:
    created_engines: list[AsyncEngine] = []
    original_create_async_engine = db.create_async_engine

    def tracked_create_async_engine(*args: object, **kwargs: object) -> AsyncEngine:
        engine = original_create_async_engine(*args, **kwargs)
        created_engines.append(engine)
        return engine

    monkeypatch.setattr(db, "create_async_engine", tracked_create_async_engine)

    try:
        yield
    finally:
        for engine in created_engines:
            await engine.dispose()
