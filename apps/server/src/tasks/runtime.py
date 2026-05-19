from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from celery_app import configure_celery
from config import Settings, get_settings
from db import DatabaseSessionFactory, create_session_factory, db_session_context, init_db
from logging_utils import configure_logging

type JobPayload = dict[str, object]


@dataclass(slots=True)
class TaskRuntime:
    session_factory: DatabaseSessionFactory
    settings: Settings
    db_initialized: bool = False


_task_runtime: TaskRuntime | None = None


def init_task_runtime(
    *,
    settings: Settings,
    session_factory: DatabaseSessionFactory | None = None,
    db_initialized: bool = True,
) -> TaskRuntime:
    runtime = TaskRuntime(
        db_initialized=db_initialized,
        session_factory=session_factory or create_session_factory(settings.database_url),
        settings=settings,
    )
    global _task_runtime
    _task_runtime = runtime
    return runtime


def get_task_runtime() -> TaskRuntime:
    runtime = _task_runtime
    if runtime is None:
        raise RuntimeError("Task runtime has not been initialized.")
    return runtime


def ensure_task_runtime() -> TaskRuntime:
    runtime = _task_runtime
    if runtime is None:
        settings = get_settings()
        configure_logging(settings.sku_lens_log_level)
        configure_celery(settings)
        runtime = init_task_runtime(settings=settings, db_initialized=False)

    if not runtime.db_initialized:
        run_coroutine(init_db(runtime.session_factory.engine))
        runtime.db_initialized = True

    return runtime


async def close_task_runtime() -> None:
    global _task_runtime
    runtime = _task_runtime
    if runtime is None:
        return

    _task_runtime = None
    await runtime.session_factory.engine.dispose()


@asynccontextmanager
async def task_session_context() -> AsyncGenerator[AsyncSession]:
    runtime = get_task_runtime()
    async with db_session_context(runtime.session_factory) as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def run_coroutine[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)
