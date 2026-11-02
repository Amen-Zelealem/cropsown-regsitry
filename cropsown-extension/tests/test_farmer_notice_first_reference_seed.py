"""A Farmer Registry notice about an unknown farmer classifies as ADD onto a pipeline-only Farmer intake form."""
import os
import re
from pathlib import Path

PACKAGE = os.environ.get("REGISTRY_EXTENSION_MODULE", "openg2p_registry_cropsown_extension")
META = Path(__file__).resolve().parents[1] / "src" / PACKAGE / "meta_data"
OVERLAY = next((META / "zz-oan").glob("*_farmer_notice_first_reference.sql"))
FORM = "farmer_registry_notice_to_farmer_reference_form"
FARMER = "fa120001-0000-4000-8000-000000000001" if "cropsown" in PACKAGE else "f9c6a359-9563-5a43-b0fe-6c7e452037a3"
SECTION = ("cropsown" if "cropsown" in PACKAGE else "livestock") + "_farmer_identity_section_01"
SQL = re.sub(r"^--.*$", "", OVERLAY.read_text(encoding="utf-8"), flags=re.M)


def seed(folder):
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted((META / folder).glob("*.sql")))


def test_form_belongs_to_the_farmer_register_and_is_pipeline_only():
    assert re.search(rf"\('{FORM}','{FARMER}','[^']+','[^']+',0,TRUE\)", SQL)
    assert "ON CONFLICT (\"form_id\") DO UPDATE" in SQL


def test_form_holds_only_the_farmer_identity_section():
    assert len(re.findall(r"INSERT INTO \"public\".\"g2p_intake_form_ui_tab_sections\"", SQL)) == 1
    assert re.findall(r"'([a-z_0-9]+)',10\)\nON CONFLICT \(\"tab_section_id\"", SQL) == [SECTION]
    assert f"'{FARMER}','{SECTION}','{FARMER}'" in seed("register-metadata").replace("\n", "")


def test_both_notice_patterns_match_the_form_for_add_and_keep_their_update_section():
    update = re.search(r"UPDATE \"public\".\"incoming_model_semantic_patterns\"\nSET (.*?)\nWHERE \"semantic_pattern_id\" IN \((.*?)\);", SQL, re.S)
    assert update
    assignments, ids = update.groups()
    assert f"\"intake_form_id\" = '{FORM}'" in assignments
    # The ADD match is the same event match the register pattern makes; no NEVER_ADD guard remains.
    assert '"pattern_for_intake_form" = "pattern_for_register"' in assignments
    assert "section_id" not in assignments and "pattern_for_section" not in assignments
    inbound = seed("registry-inbound-message-rules")
    patterns = re.findall(r"'([^']+)'", ids)
    assert len(patterns) == 2
    for pattern_id in patterns:
        assert f"'{pattern_id}'" in inbound
        assert re.search(rf"'{pattern_id}','[^']+','{FARMER}',NULL,'{SECTION}'", inbound)


def test_seed_is_idempotent_and_never_deletes():
    assert "DELETE" not in SQL.upper() and "DO NOTHING" not in SQL
    assert SQL.count("ON CONFLICT") == 3

