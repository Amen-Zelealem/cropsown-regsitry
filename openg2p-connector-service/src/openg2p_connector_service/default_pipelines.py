"""Automatic seed of default Crop Sown Registry integration pipelines."""

import json
import logging
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from .config import get_settings

_logger = logging.getLogger("connector.pipelines.seed")

DEFAULT_CROPSOWN_PIPELINES = [
    {
        "connector_id": "533b074b13544a8eb0a8fbd10c6f52ed",
        "name": "Crop Sown 1 - Planning",
        "form_id": "crop_sown_registry_plan",
    },
    {
        "connector_id": "24b12b2f3aac4ccdb5b876a604eb54aa",
        "name": "Crop Sown 2 - Cultivation & Land Prep",
        "form_id": "crop_sown_registry_prep",
    },
    {
        "connector_id": "54e73482cf304614a1f3db4982d907c5",
        "name": "Crop Sown 3 - Sowing",
        "form_id": "crop_sown_registry_sown",
    },
    {
        "connector_id": "2e6c255ec645430e8f8a8c5d3d94f707",
        "name": "Crop Sown 4 - Harvesting",
        "form_id": "crop_sown_registry_harvest",
    },
]


async def seed_default_pipelines(conn: AsyncConnection) -> None:
    """Ensure standard Crop Sown pipelines exist in the connector database.
    
    Uses ON CONFLICT (name) DO NOTHING so existing/modified pipelines are
    never overwritten, but fresh database installations are pre-populated
    automatically without manual UI configuration.
    """
    settings = get_settings()

    odk_base_url = (
        os.environ.get("CONNECTOR_ODK_CENTRAL_BASE_URL")
        or os.environ.get("ODK_CENTRAL_BASE_URL")
        or os.environ.get("ODK_BASE_URL")
        or getattr(settings, "odk_central_base_url", "")
        or "https://odk-central-development.oanstaging.com"
    ).strip().rstrip("/")

    odk_project_id = int(
        os.environ.get("CONNECTOR_ODK_PROJECT_ID")
        or os.environ.get("ODK_PROJECT_ID")
        or 15
    )

    odk_email = (
        os.environ.get("CONNECTOR_ODK_CENTRAL_EMAIL")
        or os.environ.get("ODK_CENTRAL_EMAIL")
        or os.environ.get("ODK_EMAIL")
        or getattr(settings, "odk_central_email", "")
        or "rithikharavi@gmail.com"
    ).strip()

    odk_password = (
        os.environ.get("CONNECTOR_ODK_CENTRAL_PASSWORD")
        or os.environ.get("ODK_CENTRAL_PASSWORD")
        or os.environ.get("ODK_PASSWORD")
        or getattr(settings, "odk_central_password", "")
        or "odkuserrithikha"
    ).strip()

    partner_base = (
        getattr(settings, "partner_ingest_base_url", None)
        or os.environ.get("CONNECTOR_PARTNER_INGEST_BASE_URL")
        or "http://partner-api:8000"
    ).strip().rstrip("/")
    target_url = f"{partner_base}/partner/ingest_data"

    auth_secret_json = json.dumps({"email": odk_email, "password": odk_password})

    insert_stmt = text(
        """
        INSERT INTO connector_definitions (
            connector_id, name, platform, transport_type, enabled, paused,
            data_model_mnemonic, g2p_sender_id, g2p_register_mnemonic,
            source_config_json, auth_type, auth_secret_json, webhook_verifier
        ) VALUES (
            :connector_id, :name, 'odk_central', 'odk_central', true, false,
            'CSR_DATA_MODEL', 'CropSown', 'CropSown',
            :source_config_json, 'odk_session', :auth_secret_json, 'hmac_sha256'
        )
        ON CONFLICT (name) DO NOTHING;
        """
    )

    for item in DEFAULT_CROPSOWN_PIPELINES:
        source_config = {
            "base_url": odk_base_url,
            "project_id": odk_project_id,
            "form_id": item["form_id"],
            "resolve_nav_links": True,
            "strict_incremental": False,
            "target_url": target_url,
            "target_headers": {
                "partner-id": "crop-partner",
                "Content-Type": "application/json",
            },
        }

        try:
            await conn.execute(
                insert_stmt,
                {
                    "connector_id": item["connector_id"],
                    "name": item["name"],
                    "source_config_json": json.dumps(source_config),
                    "auth_secret_json": auth_secret_json,
                },
            )
            _logger.info("Auto-seeded connector pipeline: %s", item["name"])
        except Exception as exc:
            _logger.warning("Could not auto-seed pipeline %s: %s", item["name"], exc)
