"""Land ID, Season and Crop lead every lifecycle table."""

import re
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "src" / "openg2p_registry_cropsown_extension"
SEED = (PACKAGE_DIR / "meta_data" / "register-metadata" / "zzzzzzzzz_lifecycle_context_columns.sql").read_text(encoding="utf-8")
BASE = (PACKAGE_DIR / "meta_data" / "register-metadata" / "g2p_register_sections.sql").read_text(encoding="utf-8")

TABLES = {
    "cropsown_planning_details_section_01": ("cs_planning_details_table", "commodity"),
    "cropsown_cultivation_details_section_01": ("cs_cultivation_details_table", "commodity"),
    "cropsown_cultivation_cluster_details_section_01": ("cs_cultivation_cluster_details_table", "primary_commodity"),
    "cropsown_sowing_details_section_01": ("cs_sowing_details_table", "commodity"),
    "cropsown_harvest_details_section_01": ("cs_harvest_details_table", "commodity"),
    "cropsown_infestation_details_section_01": ("cs_infestation_details_table", "commodity"),
    "cropsown_cluster_details_section_01": ("cs_cluster_details_table", "primary_commodity"),
}


def test_every_lifecycle_table_is_listed_in_the_seed_with_its_crop_column():
    for section, (table, crop) in TABLES.items():
        assert section in SEED and f"'{table}'" in SEED, section
        assert re.search(rf"'{section}',\s+'{table}',\s+'{crop}'", SEED), (section, table, crop)


def test_base_tables_define_land_and_crop_columns_the_seed_moves_to_the_front():
    for section, (table, crop) in TABLES.items():
        row = next(line for line in BASE.splitlines() if f"'{section}'" in line and f'"widget-id": "{table}"' in line)
        assert '"column-key": "land_id"' in row, section
        assert f'"column-key": "{crop}"' in row, (section, crop)


def test_harvest_and_infestation_have_a_season_column():
    for kind in ("harvest", "infestation"):
        model = (PACKAGE_DIR / "register_domain" / "models" / f"{kind}.py").read_text(encoding="utf-8")
        schema = (PACKAGE_DIR / "register_domain" / "schemas" / f"{kind}.py").read_text(encoding="utf-8")
        assert re.search(r"^\s+season: Mapped\[str\] = mapped_column\(String, nullable=True\)", model, re.M), kind
        assert re.search(r"^\s+season: Optional\[str\] = None", schema, re.M), kind


def test_seed_adds_season_after_land_id_and_is_rerunnable():
    assert "CROP_SEASON" in SEED
    assert "WHERE c->>'column-key' = 'season'" in SEED  # only adds Season when absent
    assert "must show land_id, season and" in SEED  # self-check fails the seed loudly
