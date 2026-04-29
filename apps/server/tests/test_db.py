from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlmodel import select

import db
from models import ProductDiagnosis, ShopInstallation


@pytest.mark.asyncio
async def test_init_db_upgrades_existing_shop_installations_schema(
    sqlite_database_url: str,
) -> None:
    session_factory = db.create_session_factory(sqlite_database_url)

    async with session_factory.engine.begin() as connection:
        await connection.exec_driver_sql(
            """
            CREATE TABLE shop_installations (
                id INTEGER PRIMARY KEY,
                shop_domain VARCHAR NOT NULL,
                access_token VARCHAR NULL,
                public_token VARCHAR NOT NULL,
                installed_at TIMESTAMP NOT NULL
            )
            """
        )
        await connection.exec_driver_sql(
            """
            INSERT INTO shop_installations (
                id,
                shop_domain,
                access_token,
                public_token,
                installed_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                1,
                "legacy.myshopify.com",
                "token",
                "public-token",
                datetime.now(UTC).isoformat(),
            ),
        )

    await db.init_db(session_factory.engine)

    async with session_factory() as session:
        installation = (
            await session.exec(
                select(ShopInstallation).where(
                    ShopInstallation.shop_domain == "legacy.myshopify.com"
                )
            )
        ).one()

    assert installation.timezone_name == "UTC"
    assert installation.last_completed_local_date is None
    assert installation.next_rollup_at_utc is None


def test_product_diagnosis_report_markdown_uses_text_column() -> None:
    assert str(ProductDiagnosis.__table__.c.report_markdown.type).upper() == "TEXT"


def test_product_diagnoses_upgrade_statement_expands_report_markdown_for_mysql() -> None:
    assert hasattr(db, "_product_diagnoses_report_markdown_upgrade_statement")

    statement = db._product_diagnoses_report_markdown_upgrade_statement("mysql")

    assert statement == (
        "ALTER TABLE product_diagnoses "
        "MODIFY COLUMN report_markdown LONGTEXT NULL"
    )
