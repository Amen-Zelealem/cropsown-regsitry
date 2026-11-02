"""The native "Import from file" menu: each intake form has its own file-import data model whose key paths,
pattern and Jinja template take one flat CSV or Excel row; the ODK connector's model stays as it was."""
import importlib
import json
import os
import re
from pathlib import Path

import pytest
from jinja2 import Environment
from jinja2.exceptions import UndefinedError

PACKAGE = os.environ.get('REGISTRY_EXTENSION_MODULE', 'openg2p_registry_cropsown_extension')
ROOT = Path(importlib.import_module(PACKAGE).__file__).parent
REPO = ROOT.parents[2]
META = ROOT / 'meta_data'

pytestmark = pytest.mark.skipif('cropsown' not in PACKAGE, reason='crop import')

REGISTER = '6b06a95a-9a6c-5a33-a33d-c1625716c59c'
FORMS = {
    'planning': {'config': '9ad583e8-b792-48f2-aeab-749156903a1f', 'form': '5bf0068c-ce19-46f8-874c-7147997f793b',
                 'details': 'cs_planning_details', 'season': 'cs_intake_season',
                 'required': {'land_id', 'commodity'}},
    'cultivation': {'config': 'c0755be4-bcea-4d8e-9bdf-f91f41bf1e42', 'form': '6be15ab9-0f1b-4c38-995f-395d52a1b17a',
                    'details': 'cs_cultivation_details', 'season': 'cs_common_intake_season',
                    'required': {'land_id', 'commodity'}},
    'sowing': {'config': 'be46f3fd-b78d-4308-bf86-91f8d665a9ab', 'form': '4a7c2c98-0ffb-41d8-8fea-f22349823675',
               'details': 'cs_sowing_details', 'season': 'cs_common_intake_season',
               'required': {'land_id', 'area_sown', 'commodity', 'sowing_date'}},
    'harvesting': {'config': '8fb0d6f0-8c6d-42df-99c3-6147390d6413', 'form': '52150a37-153d-496d-9cd9-2a3815d6e13b',
                   'details': 'cs_harvest_details', 'season': 'cs_common_intake_season',
                   'required': {'land_id', 'commodity', 'harvest_date', 'qty_harvested'}},
}
IDENTITY = {'farmer_id', 'fayda_id', 'crop_year', 'production_season'}
GEO = {'region', 'zone', 'woreda', 'kebele', 'latitude', 'longitude'}
CHILD_SECTIONS = {'cs_cluster_details', 'cs_cultivation_cluster_details', 'cs_infestation_details'}
BASE = {'farmer_id': 'FR-000000000001', 'fayda_id': '0000 1234 5678 9012', 'crop_year': '2026',
        'production_season': 'SEASON_MEHER'}


def sql(folder, name):
    return (META / folder / name).read_text(encoding='utf-8')


def render(form, row):
    template = (ROOT / 'templates' / f'crop_file_import_{form}_intake.j2').read_text(encoding='utf-8')
    return json.loads(Environment().from_string(template).render(expanded=row))


def header(form):
    return (REPO / 'import-templates' / f'crop_{form}_intake_import_template.csv').read_text(encoding='utf-8').strip().split(',')


def section_columns():
    """Section mnemonic -> {column key: column definition} of the dialog tables in the register metadata."""
    text = sql('register-metadata', 'g2p_register_sections.sql')
    found = {}

    def collect(node, out):
        if isinstance(node, dict):
            out.extend(node.get('widget-data-columns', []))
            for value in node.values():
                collect(value, out)
        elif isinstance(node, list):
            for value in node:
                collect(value, out)

    pattern = rf"\('{REGISTER}','\w+','[^']+','\w+','([^']+)','[^']*','\w+',\d+,'\w+',\d+,'(\{{.*?\}})',"
    for mnemonic, ui in re.findall(pattern, text):
        columns = []
        collect(json.loads(ui), columns)
        found[mnemonic] = {c['column-key']: c for c in columns}
    return found


def sample(column):
    """A value the column accepts, by the kind of widget the register shows for it."""
    widget = column['widget']
    source = column.get('widget-data-source', {})
    if widget == 'number':
        return '2.5'
    if widget == 'date':
        return '2026-06-01'
    if source.get('type') == 'static':
        values = [str(o['value']) for o in source['options']]
        if values == ['True', 'False']:
            return 'yes'
        return ';'.join(values) if widget == 'multi-select' else values[0]
    if source.get('type') == 'api':
        return 'CODE_A;CODE_B' if widget == 'multi-select' else 'CODE_A'
    return 'Sample text'


def full_row(form):
    details = section_columns()[FORMS[form]['details']]
    row = dict(BASE)
    for name in header(form):
        if name in IDENTITY:
            continue
        row[name] = {'region': 'ET04', 'zone': 'ET0404', 'woreda': 'ET040404', 'kebele': 'ET040404888003',
                     'latitude': '9.01', 'longitude': '38.74'}.get(name) or sample(details[name])
    return row


@pytest.mark.parametrize('form', FORMS)
def test_import_configuration_keeps_its_id_and_points_at_the_form_own_data_model(form):
    text = sql('registry-configurations', 'g2p_registry_import_file_configurations.sql')
    spec = FORMS[form]
    model = f'file_import_to_crop_{form}_intake'
    assert re.search(rf"'{spec['config']}',\s*'{REGISTER}',\s*'{spec['form']}',\s*'{model}',\s*'{model}',\s*'Import {form} intakes",
                     text)
    assert 'data_model_id = EXCLUDED.data_model_id' in text and 'import_file_template_mnemonic = EXCLUDED' in text
    assert 'odk_to_crop_intake' not in re.sub(r'^--.*$', '', text, flags=re.MULTILINE)
    assert f"('{spec['form']}','{REGISTER}'" in sql('register-metadata', 'g2p_intake_form_definitions.sql').replace('\n', '')


def test_every_form_has_a_separate_model_because_a_model_holds_one_template_per_register():
    ids = re.findall(r"^\s*'(file_import_to_crop_\w+_intake)',\s*$",
                     sql('registry-configurations', 'g2p_registry_import_file_configurations.sql'), re.MULTILINE)
    assert sorted(set(ids)) == sorted(f'file_import_to_crop_{form}_intake' for form in FORMS)
    models = sql('data-models', 'data_models.sql')
    for form in FORMS:
        model = f'file_import_to_crop_{form}_intake'
        assert f"('{model}','{model.upper()}','$.headers.sender_id=>^Staff Portal$',NULL,TRUE)" in models
    assert 'ON CONFLICT ("data_model_id") DO UPDATE' in models.split('-- FILE_IMPORT_TO_CROP')[1]


@pytest.mark.parametrize('form', FORMS)
def test_key_paths_match_the_import_envelope_and_pattern_reads_the_flat_body(form):
    model = f'file_import_to_crop_{form}_intake'
    paths = sql('registry-inbound-message-rules', 'incoming_model_key_paths.sql')
    assert (f"('{model}_key_path','{model}','$.headers.message_id','$.headers.sender_id',"
            f"'$.headers.signature','$.body','FALSE','')") in paths
    patterns = sql('registry-inbound-message-rules', 'incoming_model_semantic_patterns.sql')
    assert re.search(rf"\('{model}_pattern','{model}','{REGISTER}','{FORMS[form]['form']}',[^\n]*,'\$\.body',"
                     rf"'G2PPassThroughEnricherService'\)", patterns)
    enrichers = importlib.import_module(PACKAGE + '.ingestion_pipeline.enricher_services')
    assert hasattr(enrichers, 'G2PPassThroughEnricherService')
    assert 'ON CONFLICT ("semantic_pattern_id") DO UPDATE' in patterns.split('-- FILE_IMPORT_TO_CROP')[1]


@pytest.mark.parametrize('form', FORMS)
def test_template_row_document_and_file_are_registry_prefixed_and_exist(form):
    model = f'file_import_to_crop_{form}_intake'
    name = f'crop_file_import_{form}_intake.j2'
    templates = sql('registry-inbound-message-rules', 'incoming_templates.sql')
    assert f"('{model}_template','{REGISTER}','{model}','{model}_document','FALSE'" in templates
    documents = sql('register-metadata', 'g2p_registry_documents.sql')
    assert f"('{model}_document','{name}','templates','{name}','seeder'" in documents
    assert (ROOT / 'templates' / name).is_file()


def test_odk_connector_model_and_every_template_name_are_untouched_and_unique():
    paths = sql('registry-inbound-message-rules', 'incoming_model_key_paths.sql')
    assert re.search(r"'odk_to_crop_intake_key_path',\s*'odk_to_crop_intake',\s*'\$\.body\.header\.message_id',\s*"
                     r"'\$\.body\.header\.sender_id',\s*'\$\.body\.header\.signature',\s*'\$\.body\.message'", paths)
    assert re.search(r"'\$\.body\.message\.payload',\s*'G2PDciCropSownCreateEnricherService'", sql(
        'registry-inbound-message-rules', 'incoming_model_semantic_patterns.sql'))
    assert (ROOT / 'templates' / 'odk_to_crop_intake.j2').is_file()
    stores = re.findall(r"'([\w.]+\.j2)','templates'", sql('register-metadata', 'g2p_registry_documents.sql'))
    assert len(stores) == len(set(stores))
    assert all(n.startswith('crop_') for n in stores if 'file_import' in n)


@pytest.mark.parametrize('form', FORMS)
def test_blank_file_is_header_only_and_every_column_is_documented(form):
    path = REPO / 'import-templates' / f'crop_{form}_intake_import_template.csv'
    lines = path.read_text(encoding='utf-8').splitlines()
    assert len(lines) == 1, 'sample rows belong in openg2p-data'
    columns = lines[0].split(',')
    assert len(columns) == len(set(columns)) and IDENTITY <= set(columns)
    doc = (REPO / 'docs/file-import.md').read_text(encoding='utf-8')
    section = doc.split(f'## {form.capitalize()} intake')[1].split('\n## ')[0]
    documented = dict(re.findall(r'^\| `(\w+)` \|[^|]*\| (Yes|No) \|', section, re.MULTILINE))
    assert list(documented) == columns
    assert {c for c, required in documented.items() if required == 'Yes'} == IDENTITY | FORMS[form]['required']


@pytest.mark.parametrize('form', FORMS)
def test_columns_are_the_register_fields_and_every_column_is_read(form):
    spec = FORMS[form]
    details = section_columns()[spec['details']]
    columns = set(header(form))
    assert columns - IDENTITY - GEO <= set(details), 'a column that is no field of the register section'
    widget_required = {k for k, c in details.items() if c.get('widget-required')} - {'season'}
    assert widget_required <= spec['required']
    result = render(form, full_row(form))
    record = result[spec['details']][0]
    assert set(record) >= columns - IDENTITY - GEO
    assert set(record) <= set(details)
    assert result[spec['season']] == [{'crop_year': '2026', 'production_season': 'SEASON_MEHER'}]


def test_minimal_rows_render_what_the_odk_template_renders_for_the_same_intake():
    odk = (ROOT / 'templates/odk_to_crop_intake.j2').read_text(encoding='utf-8')
    identity = {'farmer_id': 'FR-000000000001', 'fayda_id': '0000123456789012'}
    season = {'crop_year': '2026', 'production_season': 'SEASON_MEHER'}
    cases = {
        'planning': {'address': {'region_display_id': 'ET04', 'kebele_display_id': 'ET040404888003'},
                     'planning': [{'land_info_id': 'L1', 'crop_details': {'crop_name_id': 'CROP_TEFF'}}]},
        'cultivation': {'cult_land_prep': [{'land_info_id': 'L1', 'crop_details': {'crop_name_id': 'CROP_TEFF'}}]},
        'sowing': {'sowing_details': [{'land_info_id': 'L1', 'independant_details': {
            'crop_name_id': 'CROP_TEFF', 'area_sown': 1.5, 'sowing_date_gc': '2026-06-01'}}]},
        'harvesting': {'harvesting': {'land_info_id': 'L1', 'cluster_status_ids': 'independent', 'independant_details': {
            'crop_name_id': 'CROP_TEFF', 'harvest_date': '2026-10-01', 'qty_harvested': 3}}},
    }
    rows = {
        'planning': {'land_id': 'L1', 'commodity': 'CROP_TEFF', 'region': 'ET04', 'kebele': 'ET040404888003'},
        'cultivation': {'land_id': 'L1', 'commodity': 'CROP_TEFF'},
        'sowing': {'land_id': 'L1', 'commodity': 'CROP_TEFF', 'area_sown': '1.5', 'sowing_date': '2026-06-01'},
        'harvesting': {'land_id': 'L1', 'commodity': 'CROP_TEFF', 'harvest_date': '2026-10-01', 'qty_harvested': '3',
                       'cluster_status': 'INDEPENDENT'},
    }
    for form, case in cases.items():
        expected = json.loads(Environment().from_string(odk).render(expanded={
            'farmer_identity': identity, 'production_season_info': season,
            '__system': {'submissionDate': '2026-12-31'}, **case}))
        actual = render(form, {**BASE, **rows[form]})
        assert set(actual) == set(expected) - CHILD_SECTIONS, form
        for key in ('farmer_id', 'fayda_fin', 'fayda_fan_id', 'status', 'lifecycle_stage'):
            assert actual['crop_farmer_lookup'][0][key] == expected['crop_farmer_lookup'][0][key], (form, key)
        assert actual[FORMS[form]['season']] == expected[FORMS[form]['season']]
        for key, value in actual[FORMS[form]['details']][0].items():
            if key in expected[FORMS[form]['details']][0] and key not in {'season', 'region', 'zone', 'woreda', 'kebele'}:
                assert value == expected[FORMS[form]['details']][0][key], (form, key)
        if form == 'planning':
            assert actual['cs_cropsown_location'][0]['geo_code_hierarchy_json'] == \
                expected['cs_cropsown_location'][0]['geo_code_hierarchy_json']


def test_planning_row_maps_columns_to_the_sections_of_the_form():
    result = render('planning', {**BASE, 'land_id': 'L1', 'commodity': 'CROP_TEFF', 'land_area': '1.5',
                                 'planned_labor': '4.0', 'is_plot_not_registered': 'No', 'cropping_system': 'mono_cropping',
                                 'start_gc': '2026-06-01 00:00:00', 'region': 'et04', 'zone': 'ET0404',
                                 'latitude': '9.0', 'longitude': '38.7', 'unknown_column': 'ignored'})
    assert result['crop_farmer_lookup'][0]['fayda_fan_id'] == '0000123456789012'
    assert result['crop_farmer_lookup'][0]['fayda_fin'] is None
    assert result['cs_planning_details'] == [{
        'land_id': 'L1', 'commodity': 'CROP_TEFF', 'land_area': 1.5, 'planned_labor': 4, 'is_plot_not_registered': False,
        'cropping_system': 'MONO_CROPPING', 'start_gc': '2026-06-01', 'region': 'ET04', 'zone': 'ET0404',
        'gps_coordinate': '9.0, 38.7', 'season': 'SEASON_MEHER'}]
    location = result['cs_cropsown_location'][0]
    assert location['geo_lowest_level_value_id'] == 'ET0404'
    assert [h['level_value_id'] for h in location['geo_code_hierarchy_json']['hierarchy']] == ['ET04', 'ET0404']
    assert 'cs_cluster_details' not in result


def test_cultivation_land_prep_methods_and_fin_identity():
    result = render('cultivation', {**BASE, 'fayda_id': '123456789012', 'land_id': 'L1',
                                    'land_prep_method': 'LAND_PREP_METHOD_SHILSHALO; land_prep_method_manual_digging'})
    assert result['cs_cultivation_details'][0]['land_prep_method'] == \
        'LAND_PREP_METHOD_SHILSHALO,LAND_PREP_METHOD_MANUAL_DIGGING'
    assert result['crop_farmer_lookup'][0]['fayda_fin'] == '123456789012'
    assert result['crop_farmer_lookup'][0]['fayda_fan_id'] is None


def test_sowing_and_harvest_cluster_status_are_lists_and_headers_ignore_case():
    sowing = render('sowing', {**BASE, 'Land_ID': ' L1 ', 'cluster_status': 'cluster; independent'})
    assert sowing['cs_sowing_details'][0] == {'land_id': 'L1', 'cluster_status': ['CLUSTER', 'INDEPENDENT'],
                                              'season': 'SEASON_MEHER'}
    harvest = render('harvesting', {**BASE, 'land_id': 'L1', 'qty_harvested': '12'})
    assert harvest['cs_harvest_details'][0] == {'land_id': 'L1', 'qty_harvested': 12.0}


@pytest.mark.parametrize('form,change,message', [
    ('planning', {'farmer_id': 'FR-1'}, 'column farmer_id'),
    ('planning', {'fayda_id': '12345'}, 'column fayda_id'),
    ('planning', {'crop_year': '26'}, 'column crop_year'),
    ('planning', {'production_season': ''}, 'column production_season'),
    ('planning', {'land_area': 'many'}, 'column land_area must be a number'),
    ('planning', {'planned_labor': 'x'}, 'column planned_labor must be a whole number'),
    ('planning', {'start_gc': '01/06/2026'}, 'column start_gc must be a date'),
    ('planning', {'is_plot_not_registered': 'maybe'}, 'column is_plot_not_registered must be yes or no'),
    ('planning', {'seed_class': 'wild'}, 'column seed_class must be one of LOCAL, IMPROVED'),
    ('sowing', {'cluster_status': 'FIELD'}, 'column cluster_status takes CLUSTER and INDEPENDENT'),
])
def test_a_value_the_register_cannot_take_fails_the_row_naming_the_column(form, change, message):
    with pytest.raises(UndefinedError, match=message):
        render(form, {**BASE, 'land_id': 'L1', 'commodity': 'CROP_TEFF', **change})
