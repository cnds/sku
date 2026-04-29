from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy import inspect
from sqlalchemy.engine import Connection
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
        await connection.run_sync(_upgrade_legacy_shop_installations_schema)
        await connection.run_sync(_upgrade_legacy_product_diagnoses_schema)


def _upgrade_legacy_shop_installations_schema(connection: Connection) -> None:
    inspector = inspect(connection)
    if "shop_installations" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"] for column in inspector.get_columns("shop_installations")
    }
    statements: list[str] = []
    if "timezone_name" not in existing_columns:
        statements.append(
            "ALTER TABLE shop_installations "
            "ADD COLUMN timezone_name VARCHAR(255) NOT NULL DEFAULT 'UTC'"
        )
    if "last_completed_local_date" not in existing_columns:
        statements.append(
            "ALTER TABLE shop_installations "
            "ADD COLUMN last_completed_local_date DATE NULL"
        )
    if "next_rollup_at_utc" not in existing_columns:
        statements.append(
            "ALTER TABLE shop_installations "
            "ADD COLUMN next_rollup_at_utc DATETIME NULL"
        )

    for statement in statements:
        connection.exec_driver_sql(statement)


def _upgrade_legacy_product_diagnoses_schema(connection: Connection) -> None:
    inspector = inspect(connection)
    if "product_diagnoses" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]: column for column in inspector.get_columns("product_diagnoses")
    }
    report_markdown = existing_columns.get("report_markdown")
    if report_markdown is None:
        return

    normalized_type = str(report_markdown["type"]).upper()
    if not normalized_type.startswith(("VARCHAR", "CHAR")):
        return

    statement = _product_diagnoses_report_markdown_upgrade_statement(
        connection.dialect.name
    )
    if statement is None:
        return
    connection.exec_driver_sql(statement)


def _product_diagnoses_report_markdown_upgrade_statement(
    dialect_name: str,
) -> str | None:
    if dialect_name == "mysql":
        return (
            "ALTER TABLE product_diagnoses "
            "MODIFY COLUMN report_markdown LONGTEXT NULL"
        )
    if dialect_name == "postgresql":
        return (
            "ALTER TABLE product_diagnoses "
            "ALTER COLUMN report_markdown TYPE TEXT"
        )
    return None
