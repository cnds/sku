from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

_current_db_session: ContextVar[AsyncSession | None] = ContextVar(
    "current_db_session",
    default=None,
)


@dataclass(slots=True)
class DatabaseSessionFactory:
    engine: AsyncEngine
    session_maker: async_sessionmaker[AsyncSession]

    def __call__(self) -> AsyncSession:
        return self.session_maker()


def create_session_factory(database_url: str) -> DatabaseSessionFactory:
    engine = create_async_engine(database_url, echo=False, future=True)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return DatabaseSessionFactory(engine=engine, session_maker=session_maker)


def get_db_session() -> AsyncSession:
    session = _current_db_session.get()
    if session is None:
        raise RuntimeError("Database session is not available in the current context.")
    return session


@asynccontextmanager
async def db_session_context(session_factory: DatabaseSessionFactory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        token = _current_db_session.set(session)
        try:
            yield session
        finally:
            _current_db_session.reset(token)


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
