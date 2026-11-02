"""Existing-database additions through the registered extension migration hook."""

from pathlib import Path

from sqlalchemy import text


async def migrate_existing_schema(engine):
    statement = Path(__file__).with_name("native_schema_compat.sql").read_text(encoding="utf-8")
    async with engine.begin() as connection:
        await connection.execute(text(statement))
