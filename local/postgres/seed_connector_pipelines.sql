-- Pre-configure Crop Sown Registry ODK Central pipelines in the connector database.
\connect connector

CREATE TABLE IF NOT EXISTS connector_definitions (
    connector_id character varying NOT NULL PRIMARY KEY,
    name character varying(255) NOT NULL UNIQUE,
    platform character varying(64) NOT NULL,
    transport_type character varying(64) NOT NULL,
    enabled boolean DEFAULT true,
    paused boolean DEFAULT false,
    data_model_mnemonic character varying(128),
    mapper_expression text,
    mapper_version character varying(64),
    g2p_sender_id character varying(128),
    g2p_register_mnemonic character varying(128),
    source_config_json text,
    auth_type character varying(64) DEFAULT 'none' NOT NULL,
    auth_secret_json text,
    webhook_secret character varying(512),
    webhook_path_slug character varying(128),
    webhook_verifier character varying(64) DEFAULT 'hmac_sha256' NOT NULL,
    last_poll_at timestamp without time zone,
    last_poll_status character varying(32),
    last_poll_error text,
    last_poll_fetched integer,
    last_poll_duration_ms integer,
    max_in_flight integer,
    validation_schema_json text,
    poll_config_json text,
    poll_state_json text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);

INSERT INTO connector_definitions (
    connector_id, name, platform, transport_type, enabled, paused,
    data_model_mnemonic, g2p_sender_id, g2p_register_mnemonic,
    source_config_json, auth_type, auth_secret_json, webhook_verifier
) VALUES
(
    '533b074b13544a8eb0a8fbd10c6f52ed',
    'Crop Sown 1 - Planning',
    'odk_central',
    'odk_central',
    true,
    false,
    'CSR_DATA_MODEL',
    'CropSown',
    'CropSown',
    '{"base_url": "https://odk-central-development.oanstaging.com", "project_id": 15, "form_id": "crop_sown_registry_plan", "resolve_nav_links": true, "strict_incremental": false, "target_url": "http://partner-api:8000/partner/ingest_data", "target_headers": {"partner-id": "crop-partner", "Content-Type": "application/json"}}',
    'odk_session',
    '{"email": "rithikharavi@gmail.com", "password": "odkuserrithikha"}',
    'hmac_sha256'
),
(
    '24b12b2f3aac4ccdb5b876a604eb54aa',
    'Crop Sown 2 - Cultivation & Land Prep',
    'odk_central',
    'odk_central',
    true,
    false,
    'CSR_DATA_MODEL',
    'CropSown',
    'CropSown',
    '{"base_url": "https://odk-central-development.oanstaging.com", "project_id": 15, "form_id": "crop_sown_registry_prep", "resolve_nav_links": true, "strict_incremental": false, "target_url": "http://partner-api:8000/partner/ingest_data", "target_headers": {"partner-id": "crop-partner", "Content-Type": "application/json"}}',
    'odk_session',
    '{"email": "rithikharavi@gmail.com", "password": "odkuserrithikha"}',
    'hmac_sha256'
),
(
    '54e73482cf304614a1f3db4982d907c5',
    'Crop Sown 3 - Sowing',
    'odk_central',
    'odk_central',
    true,
    false,
    'CSR_DATA_MODEL',
    'CropSown',
    'CropSown',
    '{"base_url": "https://odk-central-development.oanstaging.com", "project_id": 15, "form_id": "crop_sown_registry_sown", "resolve_nav_links": true, "strict_incremental": false, "target_url": "http://partner-api:8000/partner/ingest_data", "target_headers": {"partner-id": "crop-partner", "Content-Type": "application/json"}}',
    'odk_session',
    '{"email": "rithikharavi@gmail.com", "password": "odkuserrithikha"}',
    'hmac_sha256'
),
(
    '2e6c255ec645430e8f8a8c5d3d94f707',
    'Crop Sown 4 - Harvesting',
    'odk_central',
    'odk_central',
    true,
    false,
    'CSR_DATA_MODEL',
    'CropSown',
    'CropSown',
    '{"base_url": "https://odk-central-development.oanstaging.com", "project_id": 15, "form_id": "crop_sown_registry_harvest", "resolve_nav_links": true, "strict_incremental": false, "target_url": "http://partner-api:8000/partner/ingest_data", "target_headers": {"partner-id": "crop-partner", "Content-Type": "application/json"}}',
    'odk_session',
    '{"email": "rithikharavi@gmail.com", "password": "odkuserrithikha"}',
    'hmac_sha256'
)
ON CONFLICT (name) DO NOTHING;
