-- Pre-configured File Import configurations for CropSown Registry intake forms
-- Maps each of the 4 intake forms to the CSR_DATA_MODEL for spreadsheet/CSV uploads

INSERT INTO g2p_registry_import_file_configurations (
    import_file_configuration_id,
    register_id,
    form_id,
    data_model_id,
    import_file_template_mnemonic,
    import_file_template_description
) VALUES
(
    '9ad583e8-b792-48f2-aeab-749156903a1f',
    '6b06a95a-9a6c-5a33-a33d-c1625716c59c',
    '5bf0068c-ce19-46f8-874c-7147997f793b',
    'e442ca96-ac35-4014-9d13-4ef327f6b79c',
    'Planning intake form',
    'Planning intake form'
),
(
    'c0755be4-bcea-4d8e-9bdf-f91f41bf1e42',
    '6b06a95a-9a6c-5a33-a33d-c1625716c59c',
    '6be15ab9-0f1b-4c38-995f-395d52a1b17a',
    'e442ca96-ac35-4014-9d13-4ef327f6b79c',
    'Cultivation Intake form',
    'Cultivation Intake form'
),
(
    'be46f3fd-b78d-4308-bf86-91f8d665a9ab',
    '6b06a95a-9a6c-5a33-a33d-c1625716c59c',
    '4a7c2c98-0ffb-41d8-8fea-f22349823675',
    'e442ca96-ac35-4014-9d13-4ef327f6b79c',
    'Sowing Intake form',
    'Sowing Intake form'
),
(
    '8fb0d6f0-8c6d-42df-99c3-6147390d6413',
    '6b06a95a-9a6c-5a33-a33d-c1625716c59c',
    '52150a37-153d-496d-9cd9-2a3815d6e13b',
    'e442ca96-ac35-4014-9d13-4ef327f6b79c',
    'Harvesting Intake form',
    'Harvesting Intake form'
)
ON CONFLICT (import_file_configuration_id) DO UPDATE SET
    register_id = EXCLUDED.register_id,
    form_id = EXCLUDED.form_id,
    data_model_id = EXCLUDED.data_model_id,
    import_file_template_mnemonic = EXCLUDED.import_file_template_mnemonic,
    import_file_template_description = EXCLUDED.import_file_template_description;
