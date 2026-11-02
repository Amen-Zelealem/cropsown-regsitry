"""Existing-database additions through the registered extension migration hook."""

from pathlib import Path

from sqlalchemy import text


async def migrate_existing_schema(engine, schema: str | None = None):
    statement = Path(__file__).with_name("native_schema_compat.sql").read_text(encoding="utf-8")
    schema_map = (
        engine.sync_engine.get_execution_options().get("schema_translate_map") or {}
    )
    target_schema = schema or schema_map.get(None)
    async with engine.begin() as connection:
        if target_schema:
            quote = connection.dialect.identifier_preparer.quote
            await connection.execute(text(f"SET LOCAL search_path TO {quote(target_schema)}, public"))
        await connection.execute(text(statement))


