"""Lists, tasks and labels read as words, not codes.

Covers the planning record name, the list words (gender, change action, intake
source and form status, commodity and season), the Fayda number and farmer
status names, the intake form names, the register name and the planning labels
that did not say what they are. The seed overlay is zz-oan/86_readable_lists.sql.
"""

import importlib
import importlib.util
import json
import os
import re
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("openg2p_registry_core")

PACKAGE = "openg2p_registry_cropsown_extension"
CROP = "6b06a95a-9a6c-5a33-a33d-c1625716c59c"
SRC = Path(importlib.import_module(PACKAGE).__file__).parent
META = SRC / "meta_data"
OVERLAY = META / "zz-oan" / "86_readable_lists.sql"
LOADER = SRC.parents[2] / "docker" / "db-seed" / "load_sample_data.py"
plain = importlib.import_module(PACKAGE + ".register_domain.services.plain_text")
field_rules = importlib.import_module(PACKAGE + ".register_domain.services.field_rules")
INTAKE_FORMS = {
    "5bf0068c-ce19-46f8-874c-7147997f793b": "Crop planning intake",
    "6be15ab9-0f1b-4c38-995f-395d52a1b17a": "Crop cultivation intake",
    "4a7c2c98-0ffb-41d8-8fea-f22349823675": "Crop sowing intake",
    "52150a37-153d-496d-9cd9-2a3815d6e13b": "Crop harvesting intake",
}

NL = chr(10)
BLOCK = re.compile("'(\\{" + NL + ".*?" + NL + "\\})'::jsonb", re.S)


def overlay_blocks():
    return [json.loads(block) for block in BLOCK.findall(OVERLAY.read_text(encoding="utf-8"))]


def overlay_translations():
    merged = {}
    for block in overlay_blocks():
        merged.update(block)
    return merged


def test_corrected_keys_win_over_earlier_seeds_and_new_keys_keep_local_values():
    text = OVERLAY.read_text(encoding="utf-8")
    corrected, new_only = overlay_blocks()
    stored_first = 'COALESCE("domain_translation"::jsonb, \'{}\'::jsonb) ||' + NL + "'{" + NL
    ours_first = "}'::jsonb ||" + NL + '  COALESCE("domain_translation"::jsonb'
    assert stored_first in text  # the corrected keys: ours last, so they win
    assert ours_first in text  # the new keys: ours first, so a local value wins
    assert set(new_only) == {"ADD", "FEMALE", "FINAL", "MALE", "PARTNER", "STAFF_PORTAL", "UPDATE", "cs_farmer_identity"}
    assert not set(corrected) & set(new_only)
    earlier = "".join(path.read_text(encoding="utf-8") for path in sorted(META.rglob("*.sql")) if path != OVERLAY)
    for key in new_only:  # no other seed file writes these
        assert '"' + key + '":' not in earlier, key


# --- the planning record name -------------------------------------------------

@pytest.mark.parametrize("payload, name", [
    ({"commodity": "CROP_MAIZE", "season": "SEASON_MEHER", "planned_date": date(2026, 6, 15)}, "Maize, Meher 2026"),
    ({"commodity": "CROP_MAIZE", "season": "SEASON_MEHER", "planned_date": "2026-06-15"}, "Maize, Meher 2026"),
    ({"commodity": "CROP_MAIZE", "season": "SEASON_MEHER"}, "Maize, Meher"),
    ({"commodity": "CROP_TEFF", "season": "SEASON_MEHER", "planned_date": "2026-06-15", "planned_area": Decimal("1.50")},
     "Teff, Meher 2026, 1.5 hectares"),
    ({"commodity": "CROP_BLACK_CUMIN", "season": "SEASON_IRRIGATION", "planned_area": 10},
     "Black cumin, Irrigation, 10 hectares"),
    ({"commodity": "CROP_MARJORAM_OREGANO", "season": "CROP_SEASON_BELG"}, "Marjoram / oregano, Belg"),
    ({"commodity": "CROP_LEMON_SCENTED_EUCALYPTUS"}, "Lemon-scented eucalyptus"),
    ({"commodity": "Maize", "season": "Meher"}, "Maize, Meher"),
    ({"planned_date": "2026-06-15"}, ""),
])
def test_planning_name_is_words(payload, name):
    assert plain.planning_record_name(payload) == name


def test_planning_name_never_shows_a_code():
    name = plain.planning_record_name({"commodity": "CROP_ALFALFA", "season": "SEASON_BELG",
                                       "planned_date": "2027-03-01", "planned_area": "0.25"})
    assert name == "Alfalfa, Belg 2027, 0.25 hectares"
    assert "_" not in name and not re.search(r"\b[A-Z]{3,}\b", name)


def test_the_extra_lead_words_come_first():
    assert plain.planning_record_name({"commodity": "CROP_MAIZE"}, ["Plot 4"]) == "Plot 4 Maize"


def test_the_domain_service_builds_the_name_from_words():
    services = importlib.import_module(PACKAGE + ".register_domain.services")
    service = services.G2PRegisterDomainServicePlanning()
    payload = {"commodity": "CROP_MAIZE", "season": "SEASON_MEHER", "planned_date": date(2026, 7, 1), "planned_area": 2}
    assert service.construct_record_name(payload) == "Maize, Meher 2026, 2 hectares"
    assert service.construct_intake_record_name({**payload, "application_reference": "APP-7"}) == \
        "Maize, Meher 2026, 2 hectares APP-7"
    assert "CROP_MAIZE" in service.construct_search_text(payload)  # search still finds the stored code


# --- the seed overlay ---------------------------------------------------------

def test_overlay_runs_after_the_readable_text_overlay_with_a_number_of_its_own():
    names = sorted(path.name for path in (META / "zz-oan").glob("*.sql"))
    assert names.index("85_readable_text.sql") < names.index("86_readable_lists.sql")
    assert len({name.split("_")[0] for name in names}) == len(names)


def test_overlay_leaves_the_fayda_verification_overlay_alone():
    raw = OVERLAY.read_bytes()
    text = raw.decode("utf-8")
    assert b"\r" not in raw
    assert "identity_verification" not in text
    assert "70_no_fayda_verification_widget" in text  # named only to say it is not touched


def test_list_words_for_gender_action_source_and_status():
    words = overlay_translations()
    assert (words["FEMALE"], words["MALE"], words["OTHER"]) == ("Female", "Male", "Other")
    assert (words["ADD"], words["UPDATE"]) == ("Add", "Update")
    assert (words["FINAL"], words["STAFF_PORTAL"], words["PARTNER"]) == ("Final", "Staff portal", "Partner")
    assert words["cs_farmer_identity"] == "Farmer identity"


GENERATOR = SRC.parents[2] / "docker" / "db-seed" / "build_list_words_sql.py"
PACK = Path(__file__).parent / "fixtures" / "pack"


def generator():
    spec = importlib.util.spec_from_file_location("list_words_generator", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generated_words():
    sql = generator().render(generator().words(PACK))
    block = re.search(r"'(\{\n.*?\n\})'::jsonb", sql, re.S).group(1)
    return sql, json.loads(block)


def test_no_commodity_or_season_word_is_typed_into_the_overlay():
    assert not [key for key in overlay_translations() if key.startswith(("CROP_", "SEASON_"))]
    assert "86b_list_words.sql" in (SRC.parents[2] / "docker" / "db-seed" / "Dockerfile").read_text(encoding="utf-8")


def test_the_generator_renders_the_pack_labels():
    sql, words = generated_words()
    assert words["CROP_MAIZE"] == "Maize"
    assert words["CROP_TEFF"] == "Teff"  # whatever the pack says, no special case
    assert words["CROP_MARJORAM_OREGANO"] == "Marjoram / oregano"
    assert words["SEASON_MEHER"] == "Meher (main rains)"
    assert words["SEASON_BELG"] == "Belg (short rains)"
    assert words["SEASON_IRRIGATION"] == "Irrigation (dry season)"
    assert len(words) == 8


def test_the_generated_sql_keeps_local_translations_and_is_repeatable():
    sql, _ = generated_words()
    assert "}'::jsonb || COALESCE(\"domain_translation\"::jsonb, '{}'::jsonb))::json" in sql  # defaults first, local last
    assert sql == generator().render(generator().words(PACK))
    assert chr(13) not in sql


def test_the_generator_escapes_quotes():
    assert "O''Brien" in generator().render({"CROP_X": "O'Brien"})


def test_record_name_words_match_the_pack_labels():
    _, words = generated_words()
    assert [key for key, label in words.items() if key.startswith("CROP_") and plain.commodity_label(key) != label] == []


def test_the_build_check_compares_record_name_words_with_the_pack():
    # The image build runs this check against the whole pinned pack.
    plain_text = Path(plain.__file__)
    assert generator().mismatched_names(generator().words(PACK), plain_text) == []
    assert generator().mismatched_names({"CROP_MAIZE": "Corn"}, plain_text) == ["CROP_MAIZE"]
    dockerfile = (SRC.parents[2] / "docker" / "db-seed" / "Dockerfile").read_text(encoding="utf-8")
    assert "build_list_words_sql.py /openg2p-data /tmp/plain_text.py" in dockerfile


def test_the_fayda_number_has_one_name():
    words = overlay_translations()
    for key in ("fayda_fan_id", "Fayda ID (FAN)", "link_foundational_id"):
        assert words[key] == "Fayda FAN ID"
    assert words["coss_input_fayda_fan_id"].startswith("Fayda FAN ID: enter exactly 16 digits")
    assert words["coss_input_fayda_fin"].startswith("Fayda FIN: enter exactly 12 digits")
    assert field_rules.LABELS["fayda_fan_id"] == "Fayda FAN ID"
    assert field_rules.LABELS["fayda_fin"] == "Fayda FIN"
    assert field_rules.LABELS["fayda_id"] == "Fayda ID (FAN or FIN)"
    for message in field_rules.MESSAGES.values():
        assert "FAN field" not in message.replace("Fayda FAN ID field", "")
        assert "FIN field" not in message.replace("Fayda FIN field", "")
    assert words["coss_field_fan_format"] == field_rules.MESSAGES["coss_field_fan_format"]
    assert words["coss_field_fin_format"] == field_rules.MESSAGES["coss_field_fin_format"]


def test_the_register_name_is_sentence_case():
    words = overlay_translations()
    assert words["Crop Sown Registry"] == "Crop sown registry"
    assert words["cropsown_intake_tab"] == "Crop sown registry intake form"
    assert "SET \"register_subject\" = 'Crop sown registry'" in OVERLAY.read_text(encoding="utf-8")


def test_overlay_names_every_intake_form_by_id():
    text = OVERLAY.read_text(encoding="utf-8")
    for form_id, name in INTAKE_FORMS.items():
        assert f"SET \"form_mnemonic\" = '{name}'\nWHERE \"form_id\" = '{form_id}'" in text
        assert not re.match(r"^\d", name)


def test_the_sample_loader_uses_the_new_form_names_and_keeps_its_record_ids():
    spec = importlib.util.spec_from_file_location("sample_loader_names", LOADER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert [stage[0] for stage in module.STAGES] == list(INTAKE_FORMS.values())
    assert module.SEED_KEYS["Crop planning intake"] == "1.Crop Sown Planning Intake"
    assert set(module.SEED_KEYS) == set(INTAKE_FORMS.values())


# --- the replayed metadata (needs a disposable PostgreSQL) ---------------------

@unittest.skipUnless(os.environ.get("FARMER_TEST_DATABASE_URL"), "Requires disposable PostgreSQL")
class ReadableListsReplayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture = importlib.import_module("test_farmer_reference_native").NativeReferenceTests()
        await self.fixture.asyncSetUp()

    async def asyncTearDown(self):
        await self.fixture.asyncTearDown()

    async def replay(self):
        files = sorted(
            list((META / "register-metadata").glob("*.sql"))
            + list((META / "registry-configurations").glob("registry_languages*.sql"))
            + list((META / "zz-oan").glob("*.sql"))
            + [META / "zzzzzz_field_translations.sql"])
        async with self.fixture.engine.begin() as connection:
            raw = await connection.get_raw_connection()
            for path in files:
                sql = (path.read_text(encoding="utf-8")
                       .replace('"public".', '"' + self.fixture.schema + '".')
                       .replace("public.", '"' + self.fixture.schema + '".'))
                await raw.driver_connection.execute(sql)

    async def state(self):
        from openg2p_registry_core.models import (
            G2PIntakeFormDefinition, G2PRegisterDefinition, G2PRegisterSection, G2PRegistryLanguage)
        from sqlalchemy import select
        async with self.fixture.sessions() as session:
            sections = (await session.execute(select(G2PRegisterSection))).scalars().all()
            english = (await session.execute(select(G2PRegistryLanguage).where(
                G2PRegistryLanguage.language_code == "en"))).scalar_one()
            forms = (await session.execute(select(G2PIntakeFormDefinition))).scalars().all()
            definitions = (await session.execute(select(G2PRegisterDefinition))).scalars().all()
        return sections, english, forms, definitions

    @staticmethod
    def widgets(section):
        found = []

        def walk(node):
            if isinstance(node, dict):
                if "widget-label" in node:
                    found.append(node)
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(section.section_ui_schema)
        return found

    def labels(self, sections, path):
        return sorted({widget["widget-label"] for section in sections for widget in self.widgets(section)
                       if str(widget.get("widget-data-path", "")).split(".")[-1] == path})

    async def test_labels_forms_and_words_after_two_replays(self):
        await self.replay()
        await self.replay()
        sections, english, forms, definitions = await self.state()
        shown = dict(english.domain_translation)

        assert self.labels(sections, "is_plot_not_registered") == ["Plot is not yet registered"]
        assert self.labels(sections, "water_source_method") == ["Water application method"]
        assert self.labels(sections, "water_source_frequency") == ["Watering frequency"]
        assert self.labels(sections, "reference") == ["Cluster reference"]
        assert self.labels(sections, "farmer_reference_status") == ["Farmer registry status"]
        assert self.labels(sections, "fayda_fan_id") == ["Fayda FAN ID"]
        assert self.labels(sections, "fayda_fin") == ["Fayda FIN"]
        assert self.labels(sections, "fayda_id") == ["Fayda ID (FAN or FIN)"]

        every = {widget["widget-label"] for section in sections for widget in self.widgets(section)}
        assert not every & {"Fayda FAN (16 digits)", "Fayda ID (FAN)", "Farmer reference", "Fayda FIN (from verification)"}
        # The pipeline-only Farmer notice form is not one of the staff-facing crop intakes.
        assert {form.form_id: form.form_mnemonic for form in forms if not form.used_only_in_ingestion_pipeline} == INTAKE_FORMS
        assert {d.register_id: d.register_subject for d in definitions}[CROP] == "Crop sown registry"
        assert shown["FEMALE"] == "Female"
        assert shown["fayda_fan_id"] == "Fayda FAN ID"
        assert shown["cropsown_farmer_tab"] == "Farmer"  # the earlier overlays' keys survive the merge


# --- the stored record names (needs a disposable PostgreSQL) -------------------

SQL_FUNCTIONS = re.compile(r"(CREATE OR REPLACE FUNCTION pg_temp\.list_code_words.*?\$\$ LANGUAGE plpgsql IMMUTABLE;"
                           r".*?CREATE OR REPLACE FUNCTION pg_temp\.planning_name.*?\$\$ LANGUAGE plpgsql IMMUTABLE;)", re.S)


@unittest.skipUnless(os.environ.get("FARMER_TEST_DATABASE_URL"), "Requires disposable PostgreSQL")
class StoredNameTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_rewrite_gives_the_names_new_records_get(self):
        import asyncpg
        url = os.environ["FARMER_TEST_DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
        connection = await asyncpg.connect(url)
        try:
            await connection.execute(SQL_FUNCTIONS.search(OVERLAY.read_text(encoding="utf-8")).group(1))
            cases = [
                ("CROP_MAIZE", "SEASON_MEHER", date(2026, 6, 15), Decimal("1.50")),
                ("CROP_TEFF", "SEASON_BELG", None, None),
                ("CROP_BLACK_CUMIN", "SEASON_IRRIGATION", date(2025, 12, 1), Decimal("10")),
                ("CROP_MARJORAM_OREGANO", "CROP_SEASON_BEGA", date(2026, 1, 1), Decimal("0.25")),
                ("CROP_LEMON_SCENTED_EUCALYPTUS", None, date(2026, 1, 1), Decimal("3")),
                ("CROP_MAIZE", "SEASON_MEHER", date(2026, 6, 15), Decimal("100")),
            ]
            for commodity, season, planned, area in cases:
                stored = await connection.fetchval("SELECT pg_temp.planning_name($1, $2, $3, $4)",
                                                   commodity, season, planned, area)
                built = plain.planning_record_name({"commodity": commodity, "season": season,
                                                    "planned_date": planned, "planned_area": area})
                assert stored == built, (commodity, season, stored, built)
        finally:
            await connection.close()
