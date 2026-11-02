"""Add-only migration behavior on owned PostgreSQL schemas."""

import importlib
import os
import re
import unittest
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Column,
    Date,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    text,
)
from sqlalchemy import (
    inspect as sa_inspect,
)
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.types import UserDefinedType

PACKAGE = os.environ.get(
    "REGISTRY_EXTENSION_MODULE", "openg2p_registry_cropsown_extension"
)
upgrade = importlib.import_module(PACKAGE + ".schema_migration")


@unittest.skipUnless(
    os.environ.get("FARMER_TEST_DATABASE_URL"), "Requires owned disposable PostgreSQL"
)
class AddOnlyMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.url = os.environ["FARMER_TEST_DATABASE_URL"]
        self.assertTrue(self.url.startswith("postgresql+asyncpg://"))
        self.schema = "coss_schema_test_" + uuid4().hex
        engine = create_async_engine(self.url)
        async with engine.begin() as conn:
            await conn.execute(text('CREATE SCHEMA "' + self.schema + '"'))
        await engine.dispose()
        self.engine = create_async_engine(
            self.url, execution_options={"schema_translate_map": {None: self.schema}}
        )

    async def asyncTearDown(self):
        await self.engine.dispose()
        assert re.fullmatch("coss_schema_test_[0-9a-f]{32}", self.schema)
        engine = create_async_engine(self.url)
        async with engine.begin() as conn:
            await conn.execute(text('DROP SCHEMA "' + self.schema + '" CASCADE'))
        await engine.dispose()

    async def columns(self, name):
        async with self.engine.connect() as conn:
            return await conn.run_sync(
                lambda sync: sa_inspect(sync).get_columns(name, schema=self.schema)
            )

    async def test_adds_missing_columns_once_preserving_existing_types_constraints_unknown_columns_and_rows(
        self,
    ):
        table = "quoted-table"
        old = Table(
            table,
            MetaData(),
            Column("id", Integer, primary_key=True),
            Column("old_text", String(12), nullable=False),
            Column("unknown_extra", JSON),
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(old.metadata.create_all)
            await conn.execute(
                old.insert().values(
                    id=1, old_text="Synthetic", unknown_extra={"preserve": True}
                )
            )
        mapped = Table(
            table,
            MetaData(),
            Column("id", Integer, primary_key=True),
            Column("old_text", Text),
            Column("new_date", Date),
            Column('new"json', JSON),
            Column("new_nonnull", Integer, nullable=False, default=0),
        )
        models = [SimpleNamespace(__table__=mapped)]
        added = await upgrade.add_missing_mapped_columns(self.engine, models)
        self.assertEqual(len(added), 3)
        self.assertEqual(
            await upgrade.add_missing_mapped_columns(self.engine, models), []
        )
        columns = {column["name"]: column for column in await self.columns(table)}
        self.assertEqual(columns["old_text"]["type"].length, 12)
        self.assertFalse(columns["old_text"]["nullable"])
        self.assertIn("unknown_extra", columns)
        async with self.engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text('SELECT * FROM "' + self.schema + '"."quoted-table"')
                    )
                )
                .mappings()
                .one()
            )
            pk = await conn.run_sync(
                lambda sync: sa_inspect(sync).get_pk_constraint(
                    table, schema=self.schema
                )
            )
        self.assertEqual(row["old_text"], "Synthetic")
        self.assertEqual(row["unknown_extra"], {"preserve": True})
        self.assertIsNone(row["new_date"])
        self.assertIsNone(row['new"json'])
        self.assertIsNone(row["new_nonnull"])
        self.assertEqual(pk["constrained_columns"], ["id"])

    async def test_native_creation_still_owns_missing_tables(self):
        mapped = Table(
            "not-created", MetaData(), Column("id", Integer, primary_key=True)
        )
        self.assertEqual(
            await upgrade.add_missing_mapped_columns(
                self.engine, [SimpleNamespace(__table__=mapped)]
            ),
            [],
        )
        async with self.engine.connect() as conn:
            self.assertFalse(
                await conn.run_sync(
                    lambda sync: sa_inspect(sync).has_table(
                        "not-created", schema=self.schema
                    )
                )
            )

    async def test_failed_column_type_rolls_back_prior_adds_in_the_same_pass(self):
        class Unsupported(UserDefinedType):
            cache_ok = True

            def get_col_spec(self, **kwargs):
                return "COSS_UNSUPPORTED_TEST_TYPE"

        old = Table("atomic", MetaData(), Column("id", Integer, primary_key=True))
        async with self.engine.begin() as conn:
            await conn.run_sync(old.metadata.create_all)
        mapped = Table(
            "atomic",
            MetaData(),
            Column("id", Integer, primary_key=True),
            Column("first_new", Date),
            Column("unsupported", Unsupported()),
        )
        from sqlalchemy.exc import DBAPIError

        with self.assertRaises(DBAPIError):
            await upgrade.add_missing_mapped_columns(
                self.engine, [SimpleNamespace(__table__=mapped)]
            )
        self.assertEqual(
            [column["name"] for column in await self.columns("atomic")], ["id"]
        )

    async def test_native_schema_compat_converts_land_prep_method_to_jsonb(self):
        compat = importlib.import_module(PACKAGE + ".schema_compat")
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    'CREATE TABLE "' + self.schema + '"."g2p_register_cultivations" ('
                    '  internal_record_id VARCHAR PRIMARY KEY,'
                    '  land_prep_method VARCHAR'
                    ')'
                )
            )
            await conn.execute(
                text(
                    'INSERT INTO "' + self.schema + '"."g2p_register_cultivations" '
                    'VALUES (\'rec-1\', \'LAND_PREP_METHOD_SHILSHALO,LAND_PREP_METHOD_MANUAL_DIGGING\')'
                )
            )

        cols_before = {c["name"]: c for c in await self.columns("g2p_register_cultivations")}
        self.assertIn("land_prep_method", cols_before)
        self.assertNotEqual(cols_before["land_prep_method"]["type"].__class__.__name__.lower(), "jsonb")

        await compat.migrate_existing_schema(self.engine)

        cols_after = {c["name"]: c for c in await self.columns("g2p_register_cultivations")}
        self.assertEqual(cols_after["land_prep_method"]["type"].__class__.__name__.lower(), "jsonb")

        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    text('SELECT land_prep_method FROM "' + self.schema + '"."g2p_register_cultivations"')
                )
            ).mappings().one()
            self.assertEqual(
                row["land_prep_method"],
                ["LAND_PREP_METHOD_SHILSHALO", "LAND_PREP_METHOD_MANUAL_DIGGING"]
            )

    def test_reference_snapshot_matches_land_prep_method_json_schema(self):
        import json
        from pathlib import Path
        cur = Path(__file__).resolve()
        ref_path = None
        for parent in cur.parents:
            candidate = parent / "reference" / "new-dev" / "metadata.json"
            if candidate.exists():
                ref_path = candidate
                break
        if not ref_path or not ref_path.exists():
            return
        data = json.loads(ref_path.read_text(encoding="utf-8"))
        # Verify land_prep_method data_type in cultivation schema snapshot
        found = False
        def check_schemas(node):
            nonlocal found
            if isinstance(node, dict):
                if node.get("field_name") == "land_prep_method" and "data_type" in node:
                    self.assertEqual(node["data_type"], "json")
                    found = True
                for v in node.values():
                    check_schemas(v)
            elif isinstance(node, list):
                for item in node:
                    check_schemas(item)

        check_schemas(data)
        self.assertTrue(found, "Expected land_prep_method with data_type in reference snapshot")


