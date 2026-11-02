"""The sown ODK mapper reads the field names the published Sowing form sends, for
clustered and independent rows alike, and keeps the weed control method."""
import importlib
import json
import os
from pathlib import Path

import pytest
from jinja2 import Environment

PACKAGE = os.environ.get('REGISTRY_EXTENSION_MODULE', 'openg2p_registry_cropsown_extension')
ROOT = Path(importlib.import_module(PACKAGE).__file__).parent

pytestmark = pytest.mark.skipif('cropsown' not in PACKAGE, reason='crop transform')


def render(sowing, incidents=None):
    template = (ROOT / 'templates' / 'odk_to_crop_intake.j2').read_text(encoding='utf-8')
    data = {
        'farmer_identity': {'farmer_id': 'FR-000000000001', 'fayda_id': '001234567890'},
        'production_season_info': {'crop_year': '2026', 'production_season': 'meher'},
        'sowing_details': sowing,
        'infestation_incidents': incidents or [],
    }
    return json.loads(Environment().from_string(template).render(expanded=data))


def test_clustered_row_reads_the_cluster_field_names_of_the_form():
    row = render([{
        'land_info_id': 'L1', 'cluster_status_ids': 'clustered',
        'clustered_details': {'cluster_name': 'FPC', 'cluster_area_hectare': '2.0',
                              'cluster_area_sown': '1.0', 'cluster_has_pest_disease': 'yes'},
    }])['cs_sowing_details'][0]
    assert row['cluster_area_sown'] == 1.0
    assert row['cluster_has_pest_disease'] is True


def test_clustered_row_without_pest_flag_stays_false():
    row = render([{
        'land_info_id': 'L1', 'cluster_status_ids': 'clustered',
        'clustered_details': {'cluster_area_sown': '1.5'},
    }])['cs_sowing_details'][0]
    assert row['cluster_area_sown'] == 1.5
    assert row['cluster_has_pest_disease'] is False


def test_independent_row_keeps_area_sown_and_has_pest_disease():
    row = render([{
        'land_info_id': 'L2', 'cluster_status_ids': 'independent',
        'independant_details': {'area_sown': '0.75', 'has_pest_disease': 'yes'},
    }])['cs_sowing_details'][0]
    assert row['area_sown'] == 0.75
    assert row['has_pest_disease'] is True


def test_weed_control_method_is_kept_as_the_register_list_code():
    inc = render([{'land_info_id': 'L1'}], [{
        'infestation_land_info_id': 'L1',
        'weed_occurrence': {'weed_type': 'grassy', 'weed_control_method': 'hand_picking'},
    }])['cs_infestation_details'][0]
    assert inc['weed_control_method'] == 'hand_picking'
