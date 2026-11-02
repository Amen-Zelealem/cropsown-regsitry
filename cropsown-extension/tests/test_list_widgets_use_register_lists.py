"""Dropdowns whose lists the registry already holds stay list-backed, and the
land preparation column stays convertible on databases created before it was a list.
"""

import json
import re
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "src" / "openg2p_registry_cropsown_extension"
SECTIONS = (PACKAGE_DIR / "meta_data" / "register-metadata" / "g2p_register_sections.sql").read_text(encoding="utf-8")
COMPAT = (PACKAGE_DIR / "native_schema_compat.sql").read_text(encoding="utf-8")

# field -> register list it must read (codes carry the list name as a prefix)
LISTED_FIELDS = {
    "plot_category": "PLOT_CATEGORY",
    "water_source_frequency": "WATER_SOURCE_FREQUENCY",
    "cultivation_type": "MACHINERY",
    "cluster_status": "CLUSTER_STATUS",
    "pest_name": "PEST",
    "pesticide_method": "PEST_CONTROL_ACTION",
}


def selects():
    for line in SECTIONS.splitlines():
        match = re.search(r"'(\{.*\})'", line)
        if not match or "widget-data-columns" not in line:
            continue
        schema = json.loads(match.group(1))
        stack = [schema]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("widget") == "select" and node.get("widget-data-path") in LISTED_FIELDS:
                    yield node
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)


def test_listed_selects_read_the_register_list():
    found = list(selects())
    assert found, "no select widgets found"
    for node in found:
        source = node.get("widget-data-source") or {}
        field = node["widget-data-path"]
        assert source.get("type") == "api", f"{field} must read its register list, not a typed-in option list"
        assert source["params"]["attribute_id"] == LISTED_FIELDS[field], field


def test_land_prep_method_text_column_is_converted_to_a_list():
    assert "land_prep_method TYPE jsonb" in COMPAT
    for table in ("g2p_register_cultivations", "g2p_register_history_cultivations", "g2p_intake_form_cultivations"):
        assert table in COMPAT
