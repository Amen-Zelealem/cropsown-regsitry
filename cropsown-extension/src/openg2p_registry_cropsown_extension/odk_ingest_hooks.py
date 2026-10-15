"""ODK Ingestion Hooks for OpenG2P Crop Sown Registry.

This is a standalone, independent extension module. It intercepts validation
and ensures database engine initialization and submodule aliasing during
ingestion without requiring any changes to base platform files.
"""

import importlib
import logging
import os
import sys
from contextvars import ContextVar

_logger = logging.getLogger("openg2p.odk_ingest_hooks")
_active_session: ContextVar = ContextVar("odk_active_session", default=None)

# The docker-compose names are only the fallback: a cluster sets the AWE settings
# per service (REGISTRY_STAFF_PORTAL_API_AWE_*, REGISTRY_CELERY_WORKERS_AWE_*), and
# overriding them with http://awe:8000 broke every finalize on dev with
# "Name does not resolve".
_AWE_ENV_PREFIXES = (
    "REGISTRY_CORE_",
    "REGISTRY_CELERY_WORKERS_",
    "REGISTRY_STAFF_PORTAL_API_",
    "REGISTRY_PARTNER_API_",
)
_AWE_DEFAULTS = {
    "AWE_BASE_URL": "http://awe:8000",
    "AWE_DEFAULT_CALLBACK_URL": "http://staff-api:8000/awe/webhooks/decision",
    "AWE_CALLBACK_SECRET_ID": "00000000-0000-4000-8000-000000000001",
    "AWE_CALLBACK_HMAC_SECRET": "dev-registry-awe-callback-secret",
}


def _awe_setting(name: str) -> str:
    """An AWE setting from the first service prefix that sets it, else the compose default."""
    for prefix in _AWE_ENV_PREFIXES:
        value = os.environ.get(prefix + name, "").strip()
        if value:
            return value
    return _AWE_DEFAULTS[name]


def _get_registry_engine():
    """Construct an AsyncEngine connected to the primary registry database."""
    from sqlalchemy.ext.asyncio import create_async_engine
    hostname = (
        os.environ.get("COMMON_DB_HOSTNAME")
        or os.environ.get("REGISTRY_CORE_DB_HOSTNAME")
        or os.environ.get("REGISTRY_PARTNER_API_DB_HOSTNAME")
        or os.environ.get("REGISTRY_CELERY_WORKERS_DB_HOSTNAME")
        or os.environ.get("REGISTRY_STAFF_PORTAL_API_DB_HOSTNAME")
        or "postgres"
    )
    port = (
        os.environ.get("COMMON_DB_PORT")
        or os.environ.get("REGISTRY_CORE_DB_PORT")
        or os.environ.get("REGISTRY_PARTNER_API_DB_PORT")
        or "5432"
    )
    dbname = (
        os.environ.get("COMMON_DB_DBNAME")
        or os.environ.get("REGISTRY_CORE_DB_DBNAME")
        or os.environ.get("REGISTRY_PARTNER_API_DB_DBNAME")
        or "cropsown"
    )
    username = (
        os.environ.get("COMMON_DB_USERNAME")
        or os.environ.get("REGISTRY_CORE_DB_USERNAME")
        or os.environ.get("REGISTRY_PARTNER_API_DB_USERNAME")
        or "cropsown_user"
    )
    password = (
        os.environ.get("COMMON_DB_PASSWORD")
        or os.environ.get("REGISTRY_CORE_DB_PASSWORD")
        or os.environ.get("REGISTRY_PARTNER_API_DB_PASSWORD")
        or "cropsown_pass"
    )
    dsn = f"postgresql+asyncpg://{username}:{password}@{hostname}:{port}/{dbname}"
    return create_async_engine(dsn)


def _ensure_dbengine_initialized():
    """Ensure dbengine GlobalVar is set to a valid AsyncEngine pointing to the registry DB."""
    try:
        from openg2p_fastapi_common.context import dbengine
        eng = dbengine.get()
        needs_fix = eng is None or (hasattr(eng, "url") and eng.url.host in ("localhost", "127.0.0.1", None))
        if needs_fix:
            try:
                from openg2p_registry_celery_worker.engine import Engine
                eng = Engine.get_async_engine()
            except Exception:
                eng = None
            if eng is None:
                eng = _get_registry_engine()
            if eng is not None:
                dbengine.set(eng)
                _logger.info("ODK Hook: dbengine initialized to %s", eng.url)
    except Exception as e:
        _logger.debug("ODK Hook: Error in _ensure_dbengine_initialized: %s", e)


def _patch_base_initializer():
    """Patch BaseInitializer.init_db to avoid binding to localhost."""
    try:
        from openg2p_fastapi_common.app import Initializer as BaseInitializer
        if not hasattr(BaseInitializer, "_orig_init_db"):
            orig_init_db = BaseInitializer.init_db
            BaseInitializer._orig_init_db = orig_init_db

            def patched_init_db(self):
                orig_init_db(self)
                _ensure_dbengine_initialized()

            BaseInitializer.init_db = patched_init_db
            _logger.info("ODK Hook: Patched BaseInitializer.init_db")
    except Exception as e:
        _logger.debug("ODK Hook: Error patching BaseInitializer.init_db: %s", e)


def _patch_document_handler():
    """Ensure DocumentHandler uses the correct MinIO endpoint inside docker."""
    try:
        from openg2p_registry_core.helpers.document import document_factory
        from openg2p_registry_core.helpers.document.minio_client import MinioClient
        from openg2p_registry_core.helpers.document.document_handlers import DocumentHandler
        from openg2p_fastapi_common.component import component_registry

        def make_minio_client():
            endpoint = (
                os.environ.get("REGISTRY_CORE_MINIO_ENDPOINT")
                or os.environ.get("REGISTRY_CELERY_WORKERS_MINIO_ENDPOINT")
                or os.environ.get("REGISTRY_PARTNER_API_MINIO_ENDPOINT")
                or os.environ.get("REGISTRY_STAFF_PORTAL_API_MINIO_ENDPOINT")
                or "minio:9000"
            )
            access_key = (
                os.environ.get("REGISTRY_CORE_MINIO_ACCESS_KEY")
                or os.environ.get("REGISTRY_CELERY_WORKERS_MINIO_ACCESS_KEY")
                or os.environ.get("REGISTRY_PARTNER_API_MINIO_ACCESS_KEY")
                or "minioadmin"
            )
            secret_key = (
                os.environ.get("REGISTRY_CORE_MINIO_SECRET_KEY")
                or os.environ.get("REGISTRY_CELERY_WORKERS_MINIO_SECRET_KEY")
                or os.environ.get("REGISTRY_PARTNER_API_MINIO_SECRET_KEY")
                or "minioadmin"
            )
            secure = (
                os.environ.get("REGISTRY_CORE_MINIO_SECURE")
                or os.environ.get("REGISTRY_CELERY_WORKERS_MINIO_SECURE")
                or "false"
            ).lower() == "true"
            return MinioClient(
                endpoint=endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure,
            )

        document_factory._create_document_handler = make_minio_client

        # Replace any existing DocumentHandler in component_registry if it pointed to localhost
        cr = component_registry.get()
        if cr:
            for i, c in enumerate(cr):
                if isinstance(c, DocumentHandler):
                    cr[i] = make_minio_client()
                    _logger.info("ODK Hook: Replaced DocumentHandler with docker minio client")
                    break
    except Exception as e:
        _logger.debug("ODK Hook: Error in _patch_document_handler: %s", e)


def _ensure_core_services():
    """Ensure Core services like G2PDocumentService are initialized."""
    try:
        from openg2p_registry_core.services import G2PDocumentService
        if G2PDocumentService.get_component() is None:
            from openg2p_registry_core.app import Initializer as CoreInitializer
            CoreInitializer().initialize()
            _logger.info("ODK Hook: CoreInitializer initialized core services")
    except Exception as e:
        _logger.debug("ODK Hook: Error initializing core services: %s", e)


def _ensure_master_data_engine():
    """Ensure db_engine_master_data connects to postgres rather than defaulting to localhost."""
    try:
        from openg2p_registry_core import engine
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool

        hostname = (
            os.environ.get("REGISTRY_CORE_MASTER_DATA_DB_HOSTNAME")
            or os.environ.get("REGISTRY_PARTNER_API_MASTER_DATA_DB_HOSTNAME")
            or os.environ.get("REGISTRY_CELERY_WORKERS_MASTER_DATA_DB_HOSTNAME")
            or os.environ.get("REGISTRY_STAFF_PORTAL_API_MASTER_DATA_DB_HOSTNAME")
            or "postgres"
        )
        username = (
            os.environ.get("REGISTRY_CORE_MASTER_DATA_DB_USERNAME")
            or os.environ.get("REGISTRY_PARTNER_API_MASTER_DATA_DB_USERNAME")
            or os.environ.get("REGISTRY_CELERY_WORKERS_MASTER_DATA_DB_USERNAME")
            or "master_data_user"
        )
        password = (
            os.environ.get("REGISTRY_CORE_MASTER_DATA_DB_PASSWORD")
            or os.environ.get("REGISTRY_PARTNER_API_MASTER_DATA_DB_PASSWORD")
            or os.environ.get("REGISTRY_CELERY_WORKERS_MASTER_DATA_DB_PASSWORD")
            or "master_data_pass"
        )
        dbname = (
            os.environ.get("REGISTRY_CORE_MASTER_DATA_DB_DBNAME")
            or os.environ.get("REGISTRY_PARTNER_API_MASTER_DATA_DB_DBNAME")
            or os.environ.get("REGISTRY_CELERY_WORKERS_MASTER_DATA_DB_DBNAME")
            or "master_data"
        )
        port = (
            os.environ.get("REGISTRY_CORE_MASTER_DATA_DB_PORT")
            or os.environ.get("REGISTRY_PARTNER_API_MASTER_DATA_DB_PORT")
            or "5432"
        )
        driver = "postgresql+asyncpg"
        dsn = f"{driver}://{username}:{password}@{hostname}:{port}/{dbname}"
        eng = create_async_engine(dsn, poolclass=NullPool)
        if engine._engines is None:
            engine._engines = {}
        engine._engines["db_engine_master_data"] = eng
        _logger.info("ODK Hook: Initialized db_engine_master_data to %s", dsn)
    except Exception as e:
        _logger.debug("ODK Hook: Error initializing master data engine: %s", e)


_master_data_engine = None


def _get_master_data_engine():
    global _master_data_engine
    if _master_data_engine is not None:
        return _master_data_engine
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    hostname = (
        os.environ.get("REGISTRY_CORE_MASTER_DATA_DB_HOSTNAME")
        or os.environ.get("REGISTRY_PARTNER_API_MASTER_DATA_DB_HOSTNAME")
        or os.environ.get("REGISTRY_CELERY_WORKERS_MASTER_DATA_DB_HOSTNAME")
        or os.environ.get("REGISTRY_STAFF_PORTAL_API_MASTER_DATA_DB_HOSTNAME")
        or os.environ.get("MASTER_DATA_DB_HOSTNAME")
        or os.environ.get("COMMON_DB_HOSTNAME")
        or "postgres"
    )
    port = (
        os.environ.get("REGISTRY_CORE_MASTER_DATA_DB_PORT")
        or os.environ.get("REGISTRY_PARTNER_API_MASTER_DATA_DB_PORT")
        or os.environ.get("REGISTRY_CELERY_WORKERS_MASTER_DATA_DB_PORT")
        or os.environ.get("REGISTRY_STAFF_PORTAL_API_MASTER_DATA_DB_PORT")
        or os.environ.get("MASTER_DATA_DB_PORT")
        or "5432"
    )
    dbname = (
        os.environ.get("REGISTRY_CORE_MASTER_DATA_DB_DBNAME")
        or os.environ.get("REGISTRY_PARTNER_API_MASTER_DATA_DB_DBNAME")
        or os.environ.get("REGISTRY_CELERY_WORKERS_MASTER_DATA_DB_DBNAME")
        or os.environ.get("REGISTRY_STAFF_PORTAL_API_MASTER_DATA_DB_DBNAME")
        or os.environ.get("MASTER_DATA_DB_DBNAME")
        or "master_data"
    )
    username = (
        os.environ.get("REGISTRY_CORE_MASTER_DATA_DB_USERNAME")
        or os.environ.get("REGISTRY_PARTNER_API_MASTER_DATA_DB_USERNAME")
        or os.environ.get("REGISTRY_CELERY_WORKERS_MASTER_DATA_DB_USERNAME")
        or os.environ.get("REGISTRY_STAFF_PORTAL_API_MASTER_DATA_DB_USERNAME")
        or os.environ.get("MASTER_DATA_DB_USERNAME")
        or "master_data_user"
    )
    password = (
        os.environ.get("REGISTRY_CORE_MASTER_DATA_DB_PASSWORD")
        or os.environ.get("REGISTRY_PARTNER_API_MASTER_DATA_DB_PASSWORD")
        or os.environ.get("REGISTRY_CELERY_WORKERS_MASTER_DATA_DB_PASSWORD")
        or os.environ.get("REGISTRY_STAFF_PORTAL_API_MASTER_DATA_DB_PASSWORD")
        or os.environ.get("MASTER_DATA_DB_PASSWORD")
        or "master_data_pass"
    )
    dsn = f"postgresql+asyncpg://{username}:{password}@{hostname}:{port}/{dbname}"
    _master_data_engine = create_async_engine(dsn, poolclass=NullPool)
    return _master_data_engine


_GEO_LABEL_CACHE: dict[str, str] = {
    "central_ethiopia": "Central Ethiopia",
    "amhara": "Amhara",
    "dire": "Dire Dawa",
    "dire_dawa": "Dire Dawa",
    "oromia": "Oromia",
    "benishangul": "Benishangul-Gumuz",
    "ethiopia_somali": "Somali",
    "somali": "Somali",
    "tigray": "Tigray",
    "afar": "Afar",
    "sidama": "Sidama",
    "south_ethiopian": "South Ethiopian",
    "south_west_ethiopia": "South West Ethiopia",
    "gambela": "Gambela",
    "harari": "Harari",
    "addis_ababa": "Addis Ababa",
    "ET01": "Tigray",
    "ET02": "Afar",
    "ET03": "Amhara",
    "ET04": "Oromia",
    "ET05": "Somali",
    "ET06": "Benishangul-Gumuz",
    "ET07": "Central Ethiopia",
    "ET08": "South Ethiopian",
    "ET11": "South West Ethiopia",
    "ET12": "Gambela",
    "ET13": "Harari",
    "ET14": "Addis Ababa",
    "ET15": "Dire Dawa",
    "ET16": "Sidama",
}


async def resolve_geo_label(code: str | None, level_prefix: str = "") -> str | None:
    """Resolve an administrative code or mnemonic to a human-readable display label."""
    if not code:
        return None
    code_str = str(code).strip()
    if not code_str:
        return None
    if code_str in _GEO_LABEL_CACHE:
        return _GEO_LABEL_CACHE[code_str]

    clean_code = code_str
    for pfx in ("KEBELE_", "WOREDA_", "ZONE_", "REGION_"):
        if clean_code.startswith(pfx):
            clean_code = clean_code[len(pfx):]
            break

    if clean_code in _GEO_LABEL_CACHE:
        return _GEO_LABEL_CACHE[clean_code]

    try:
        engine = _get_master_data_engine()
        from sqlalchemy.ext.asyncio import async_sessionmaker
        from sqlalchemy import text

        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        async with session_maker() as session:
            candidates = [
                code_str,
                clean_code,
                f"{level_prefix}-{code_str}" if level_prefix else code_str,
                f"{level_prefix}-{clean_code}" if level_prefix else clean_code,
                f"zone-{code_str}",
                f"woreda-{code_str}",
                f"kebele-{code_str}",
                f"region-{code_str}",
            ]
            q = text(
                "SELECT level_value_mnemonic FROM g2p_geo_level_values "
                "WHERE level_value_id = :c1 OR level_value_id = :c2 OR level_value_id = :c3 "
                "OR level_value_id = :c4 OR level_value_id = :c5 OR level_value_id = :c6 "
                "OR level_value_id = :c7 OR level_value_id = :c8 "
                "OR level_value_id ILIKE :c_like "
                "LIMIT 1"
            )
            res = await session.execute(
                q,
                {
                    "c1": candidates[0],
                    "c2": candidates[1],
                    "c3": candidates[2],
                    "c4": candidates[3],
                    "c5": candidates[4],
                    "c6": candidates[5],
                    "c7": candidates[6],
                    "c8": candidates[7],
                    "c_like": f"%{clean_code}",
                },
            )
            row = res.fetchone()
            if row and row[0]:
                _GEO_LABEL_CACHE[code_str] = row[0]
                return row[0]
    except Exception as e:
        _logger.warning("ODK Hook: Geo resolution error for %s: %s", code_str, e)

    cleaned = code_str.replace("_", " ").title() if "_" in code_str else code_str
    _GEO_LABEL_CACHE[code_str] = cleaned
    return cleaned


async def build_geo_hierarchy_from_db(val: str | None) -> dict | None:
    """Build full geo hierarchy JSON and canonical level_value_id from master-data."""
    if not val:
        return None
    val_str = str(val).strip()
    if not val_str:
        return None

    clean_val = val_str
    for pfx in ("KEBELE_", "WOREDA_", "ZONE_", "REGION_"):
        if clean_val.startswith(pfx):
            clean_val = clean_val[len(pfx):]
            break

    try:
        engine = _get_master_data_engine()
        from sqlalchemy.ext.asyncio import async_sessionmaker
        from sqlalchemy import text

        session_maker = async_sessionmaker(engine, expire_on_commit=False)
        async with session_maker() as session:
            candidates = [
                val_str,
                clean_val,
                f"kebele-{clean_val}",
                f"woreda-{clean_val}",
                f"zone-{clean_val}",
                f"region-{clean_val}",
            ]
            q = text(
                "SELECT level_value_id FROM g2p_geo_level_values "
                "WHERE level_value_id = :c1 OR level_value_id = :c2 OR level_value_id = :c3 "
                "OR level_value_id = :c4 OR level_value_id = :c5 OR level_value_id = :c6 "
                "OR level_value_id ILIKE :c_like LIMIT 1"
            )
            res = await session.execute(
                q,
                {
                    "c1": candidates[0],
                    "c2": candidates[1],
                    "c3": candidates[2],
                    "c4": candidates[3],
                    "c5": candidates[4],
                    "c6": candidates[5],
                    "c_like": f"%{clean_val}",
                },
            )
            row = res.fetchone()
            if not row:
                return None
            lowest_id = row[0]

            hierarchy = []
            curr = lowest_id
            while curr:
                r = await session.execute(
                    text(
                        "SELECT lv.level_value_id, lv.level_value_mnemonic, lv.parent_level_value_id, l.level_mnemonic "
                        "FROM g2p_geo_level_values lv "
                        "JOIN g2p_geo_levels l ON lv.level_id = l.level_id "
                        "WHERE lv.level_value_id = :val_id"
                    ),
                    {"val_id": curr},
                )
                node = r.fetchone()
                if not node:
                    break
                hierarchy.append(
                    {
                        "level": node.level_mnemonic,
                        "level_mnemonic": node.level_mnemonic,
                        "level_value_id": node.level_value_id,
                        "level_value_mnemonic": node.level_value_mnemonic,
                    }
                )
                curr = node.parent_level_value_id
            hierarchy.reverse()
            return {"hierarchy": hierarchy, "lowest_level_value_id": lowest_id}
    except Exception as e:
        _logger.debug("ODK Hook: build_geo_hierarchy_from_db error: %s", e)
        return None


def _alias_extension_modules():
    """Ensure openg2p_registry_extensions and all its subpackages alias to cropsown extension."""
    ext = os.environ.get("REGISTRY_EXTENSION_MODULE", "openg2p_registry_cropsown_extension")
    if "openg2p_registry_extensions" not in sys.modules:
        try:
            sys.modules["openg2p_registry_extensions"] = sys.modules.get(ext) or importlib.import_module(ext)
            for sub in (
                "config",
                "ingestion_pipeline",
                "ingestion_pipeline.enricher_services",
                "register_domain",
                "register_domain.models",
                "register_domain.schemas",
                "register_domain.services",
                "register_domain.controllers",
                "register_domain.factory",
            ):
                try:
                    sys.modules[f"openg2p_registry_extensions.{sub}"] = importlib.import_module(f"{ext}.{sub}")
                except Exception:
                    pass
            _logger.info("ODK Hook: Aliased openg2p_registry_extensions -> %s", ext)
        except Exception as e:
            _logger.debug("ODK Hook: Error aliasing extension modules: %s", e)


def _patch_request_response_helper():
    """Patch RequestResponseHelper._construct_data_model_response for Pydantic v2 JSON serialization."""
    try:
        from openg2p_registry_partner_api.ingestion.helpers.request_response_helper import RequestResponseHelper
        from fastapi.responses import JSONResponse
        from openg2p_registry_core.helpers import TemplateHelper

        if not hasattr(RequestResponseHelper, "_orig_construct_data_model_response"):
            RequestResponseHelper._orig_construct_data_model_response = RequestResponseHelper._construct_data_model_response

            def patched_construct_data_model_response(self, response_template_store_id, response):
                if not response_template_store_id:
                    return JSONResponse(content=response.model_dump(mode="json"))

                template_helper = TemplateHelper.get_component()
                response_data = response.model_dump(mode="json")
                response_data = template_helper.render_with_template(
                    document_store_id=response_template_store_id,
                    data=response_data,
                    expand_data=False,
                )
                return JSONResponse(content=response_data)

            RequestResponseHelper._construct_data_model_response = patched_construct_data_model_response
            _logger.info("ODK Hook: Patched RequestResponseHelper._construct_data_model_response")
    except Exception as e:
        _logger.debug("Could not patch RequestResponseHelper: %s", e)


def _patch_celery_worker():
    """Patch ingest_data_worker to bind dbengine and active session."""
    try:
        worker_mod = importlib.import_module("openg2p_registry_celery_worker.tasks.ingest_data_worker")
        if worker_mod and not hasattr(worker_mod, "_orig_save_sections_async"):
            orig_save_sections_async = worker_mod._save_sections_async
            worker_mod._orig_save_sections_async = orig_save_sections_async

            async def patched_save_sections_async(
                submission_id: str,
                incoming_classified_data,
                ordered_sections: list,
                transformed_data: dict,
                session,
            ) -> None:
                try:
                    from openg2p_fastapi_common.context import dbengine
                    if hasattr(session, "bind") and session.bind:
                        dbengine.set(session.bind)
                    else:
                        _ensure_dbengine_initialized()
                    _ensure_core_services()
                except Exception:
                    pass

                t_session = _active_session.set(session)
                try:
                    # Auto-enrich intake records with farmer name, location, and status
                    try:
                        from sqlalchemy import text
                        for sec_key in ("cs_common_intake_record", "cs_intake_record"):
                            rows = transformed_data.get(sec_key) or []
                            for row in rows:
                                fayda = row.get("fayda_fan_id")
                                f_name = row.get("farmer_name")
                                if not row.get("status"):
                                    row["status"] = "DRAFT"
                                if fayda and (not f_name or not str(f_name).strip() or not row.get("region")):
                                    res = await session.execute(
                                        text("""
                                            SELECT farmer_name, farmer_id, region, zone, woreda, kebele,
                                                   address_line_1, address_line_2, latitude, longitude,
                                                   latitude || ', ' || longitude as gps_coordinate
                                            FROM g2p_intake_form_crop_sowns
                                            WHERE fayda_fan_id = :fayda AND farmer_name IS NOT NULL AND farmer_name != ''
                                            ORDER BY created_at DESC LIMIT 1
                                        """),
                                        {"fayda": str(fayda).strip()}
                                    )
                                    r = res.fetchone()
                                    if not r:
                                        res_reg = await session.execute(
                                            text("""
                                                SELECT farmer_name, farmer_id, region, zone, woreda, kebele,
                                                       address_line_1, address_line_2, latitude, longitude,
                                                       latitude || ', ' || longitude as gps_coordinate
                                                FROM g2p_register_crop_sowns
                                                WHERE fayda_fan_id = :fayda AND farmer_name IS NOT NULL AND farmer_name != ''
                                                ORDER BY created_at DESC LIMIT 1
                                            """),
                                            {"fayda": str(fayda).strip()}
                                        )
                                        r = res_reg.fetchone()
                                    if r:
                                        if not row.get("farmer_name") and r[0]:
                                            row["farmer_name"] = r[0]
                                        if not row.get("farmer_id") and r[1]:
                                            row["farmer_id"] = r[1]
                                        if not row.get("region") and r[2]:
                                            row["region"] = r[2]
                                        if not row.get("zone") and r[3]:
                                            row["zone"] = r[3]
                                        if not row.get("woreda") and r[4]:
                                            row["woreda"] = r[4]
                                        if not row.get("kebele") and r[5]:
                                            row["kebele"] = r[5]
                                        if not row.get("latitude") and r[8]:
                                            row["latitude"] = r[8]
                                        if not row.get("longitude") and r[9]:
                                            row["longitude"] = r[9]
                                        if not row.get("gps_coordinate") and r[10]:
                                            row["gps_coordinate"] = r[10]

                                f_id = row.get("farmer_id")
                                if f_id:
                                    row["record_name"] = str(f_id)
                                else:
                                    row["record_name"] = None
                                for level_pfx, code_key, name_key in (
                                    ("region", "region", "region_name"),
                                    ("zone", "zone", "zone_name"),
                                    ("woreda", "woreda", "woreda_name"),
                                    ("kebele", "kebele", "kebele_name"),
                                ):
                                    val = row.get(code_key) or row.get(name_key)
                                    if val:
                                        val_str = str(val).strip()
                                        try:
                                            resolved = await resolve_geo_label(val_str, level_pfx)
                                            if resolved:
                                                row[name_key] = resolved
                                            elif not row.get(name_key):
                                                row[name_key] = val_str
                                        except Exception as err:
                                            _logger.debug("Error resolving geo label for %s: %s", val_str, err)
                                            if not row.get(name_key):
                                                row[name_key] = val_str

                        # Also resolve geo labels across child sections (e.g. planning, cluster)
                        for sec in ("cs_planning_details", "cs_cultivation_cluster_details", "cs_cluster_details"):
                            for s_row in (transformed_data.get(sec) or []):
                                for level_pfx, code_key, name_key in (
                                    ("region", "region", "region_name"),
                                    ("zone", "zone", "zone_name"),
                                    ("woreda", "woreda", "woreda_name"),
                                    ("kebele", "kebele", "kebele_name"),
                                ):
                                    val = s_row.get(code_key) or s_row.get(name_key)
                                    if val:
                                        try:
                                            resolved = await resolve_geo_label(str(val).strip(), level_pfx)
                                            if resolved:
                                                s_row[name_key] = resolved
                                        except Exception:
                                            pass

                        # Ensure cs_cropsown_location has gps_coordinate and geo_code_hierarchy_json
                        loc_rows = transformed_data.get("cs_cropsown_location") or []
                        for lr in loc_rows:
                            lat = lr.get("latitude")
                            lon = lr.get("longitude")
                            if lat and lon and not lr.get("gps_coordinate"):
                                lr["gps_coordinate"] = f"{lat}, {lon}"

                        # Enrich geo_code_hierarchy_json and canonical geo_lowest_level_value_id
                        for sec_key in ("cs_intake_record", "cs_common_intake_record", "cs_cropsown_location"):
                            for r in (transformed_data.get(sec_key) or []):
                                lowest_val = r.get("geo_lowest_level_value_id") or r.get("kebele") or r.get("woreda")
                                if lowest_val and not r.get("geo_code_hierarchy_json"):
                                    geo_res = await build_geo_hierarchy_from_db(lowest_val)
                                    if geo_res:
                                        r["geo_code_hierarchy_json"] = geo_res
                                        r["geo_lowest_level_value_id"] = geo_res["lowest_level_value_id"]
                                        # Also ensure region, zone, woreda, kebele codes match canonical attribute values
                                        for h in geo_res.get("hierarchy", []):
                                            lvl = h.get("level")
                                            val_id = h.get("level_value_id")
                                            val_mnemonic = h.get("level_value_mnemonic")
                                            if lvl in ("region", "zone", "woreda", "kebele") and val_id:
                                                code = str(val_id).upper().replace("-", "_")
                                                r[lvl] = code
                                                if val_mnemonic:
                                                    r[f"{lvl}_name"] = val_mnemonic
                    except Exception as e:
                        _logger.debug("Error in auto-enriching intake submission: %s", e)

                    return await orig_save_sections_async(
                        submission_id,
                        incoming_classified_data,
                        ordered_sections,
                        transformed_data,
                        session,
                    )
                finally:
                    _active_session.reset(t_session)

            worker_mod._save_sections_async = patched_save_sections_async
            _logger.info("ODK Hook: Patched ingest_data_worker._save_sections_async")

            orig_finalize_submission_async = getattr(worker_mod, "_finalize_submission_async", None)
            if orig_finalize_submission_async and not hasattr(worker_mod, "_odk_patched_finalize"):
                worker_mod._odk_patched_finalize = True

                async def patched_finalize_submission_async(submission_id: str, session) -> None:
                    token = await _get_awe_service_token()
                    from openg2p_registry_core.services.intake_form_data_service import G2PIntakeFormDataService
                    await G2PIntakeFormDataService.get_component().finalize_submission_with_session(
                        submission_id,
                        session,
                        bearer_token=token,
                    )

                worker_mod._finalize_submission_async = patched_finalize_submission_async
                _logger.info("ODK Hook: Patched ingest_data_worker._finalize_submission_async with AWE service token")

            try:
                from openg2p_registry_core.config import Settings as CoreSettings
                from openg2p_registry_core.helpers import AweHelper
                core_cfg = CoreSettings.get_config(strict=False)
                core_cfg.awe_enabled = True
                core_cfg.awe_base_url = _awe_setting("AWE_BASE_URL")
                core_cfg.awe_default_callback_url = _awe_setting("AWE_DEFAULT_CALLBACK_URL")
                core_cfg.awe_callback_secret_id = _awe_setting("AWE_CALLBACK_SECRET_ID")
                core_cfg.awe_callback_hmac_secret = _awe_setting("AWE_CALLBACK_HMAC_SECRET")
                awe_h = AweHelper.get_component()
                if awe_h:
                    awe_h._base_url = core_cfg.awe_base_url
            except Exception as e:
                _logger.debug("Could not patch core settings AWE config: %s", e)
    except Exception as e:
        _logger.debug("Could not patch ingest_data_worker: %s", e)


_cached_awe_token = None
_cached_awe_token_expiry = 0


async def _get_awe_service_token() -> str | None:
    """Acquire and cache a Keycloak client-credentials token for background AWE calls."""
    global _cached_awe_token, _cached_awe_token_expiry
    import time
    import urllib.request
    import urllib.parse
    import json

    now = time.time()
    if _cached_awe_token and now < _cached_awe_token_expiry - 60:
        return _cached_awe_token
    try:
        keycloak_url = (
            os.environ.get("KEYCLOAK_BASE_URL")
            or os.environ.get("KEYCLOAK_URL")
            or "http://keycloak:8080"
        ).rstrip("/")
        realm = os.environ.get("KEYCLOAK_REALM", "staff")
        client_id = os.environ.get("AUTH_CLIENT_ID", "cropsown-staff-portal")
        client_secret = os.environ.get("AUTH_CLIENT_SECRET", "cropsown-staff-portal-secret")

        token_url = f"{keycloak_url}/realms/{realm}/protocol/openid-connect/token"
        data = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }).encode("utf-8")
        req = urllib.request.Request(token_url, data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            _cached_awe_token = body.get("access_token")
            expires_in = body.get("expires_in", 300)
            _cached_awe_token_expiry = now + expires_in
            return _cached_awe_token
    except Exception as exc:
        _logger.warning("Could not obtain AWE service token from Keycloak: %s", exc)
        return None


def _connect_celery_signals():
    """Register Celery signals to ensure dbengine is set for all background tasks."""
    try:
        from celery.signals import task_prerun

        @task_prerun.connect
        def on_celery_task_prerun(*args, **kwargs):
            _ensure_dbengine_initialized()
            _ensure_core_services()
    except Exception:
        pass


def _patch_intake_form_data_service():
    """Patch G2PIntakeFormDataService to handle land_id validation and Decimal serialization."""
    try:
        from openg2p_registry_core.services.intake_form_data_service import G2PIntakeFormDataService
        from sqlalchemy import select, text
        from decimal import Decimal

        if not hasattr(G2PIntakeFormDataService, "_odk_patched_finalize_submission_with_session"):
            G2PIntakeFormDataService._odk_patched_finalize_submission_with_session = True
            orig_finalize_submission = G2PIntakeFormDataService.finalize_submission_with_session

            async def patched_finalize_submission_with_session(
                self,
                submission_id: str,
                session,
                finalized_by: str | None = None,
                bearer_token: str | None = None,
                requester_sub: str | None = None,
            ):
                if not bearer_token:
                    bearer_token = await _get_awe_service_token()
                try:
                    from openg2p_registry_core.helpers import AweHelper
                    awe_h = AweHelper.get_component()
                    if awe_h:
                        awe_h._base_url = _awe_setting("AWE_BASE_URL")
                except Exception:
                    pass
                return await orig_finalize_submission(
                    self,
                    submission_id,
                    session,
                    finalized_by=finalized_by,
                    bearer_token=bearer_token,
                    requester_sub=requester_sub,
                )

            G2PIntakeFormDataService.finalize_submission_with_session = patched_finalize_submission_with_session
            _logger.info("ODK Hook: Patched G2PIntakeFormDataService.finalize_submission_with_session with AWE service token")

        if not hasattr(G2PIntakeFormDataService, "_odk_patched_serialize_model"):
            G2PIntakeFormDataService._odk_patched_serialize_model = True
            orig_serialize = G2PIntakeFormDataService._serialize_model

            def patched_serialize_model(self, row, exclude=None):
                data = orig_serialize(self, row, exclude)
                for k, v in data.items():
                    if isinstance(v, Decimal):
                        data[k] = str(v)
                return data

            G2PIntakeFormDataService._serialize_model = patched_serialize_model
            _logger.info("ODK Hook: Patched G2PIntakeFormDataService._serialize_model for Decimal handling")

        if not hasattr(G2PIntakeFormDataService, "_odk_patched_insert_live_register_row"):
            G2PIntakeFormDataService._odk_patched_insert_live_register_row = True
            orig_insert = G2PIntakeFormDataService._insert_live_register_row

            async def patched_insert_live_register_row(
                self,
                submission,
                section,
                register_definition,
                schema_class,
                register_class,
                intake_row,
                session,
                root_record_id_mapping=None,
            ):
                res = await orig_insert(
                    self,
                    submission,
                    section,
                    register_definition,
                    schema_class,
                    register_class,
                    intake_row,
                    session,
                    root_record_id_mapping,
                )
                try:
                    if hasattr(register_class, "zone_name") and hasattr(intake_row, "internal_record_id"):
                        for attr_id, code_key, name_key in (
                            ("REGION", "region", "region_name"),
                            ("ZONE", "zone", "zone_name"),
                            ("WOREDA", "woreda", "woreda_name"),
                            ("KEBELE", "kebele", "kebele_name"),
                        ):
                            cur_name = getattr(intake_row, name_key, None)
                            cur_code = getattr(intake_row, code_key, None)
                            val = cur_name or cur_code
                            if val:
                                q = text("""
                                    SELECT value_display FROM g2p_attribute_values 
                                    WHERE attribute_id = :attr_id 
                                      AND (value_id = :val OR value_code = :val 
                                           OR value_display ILIKE :val
                                           OR value_id = (:attr_id || '_' || :val)
                                           OR value_id = (:attr_id || '_ET' || :val)
                                           OR value_code LIKE ('%' || :val)
                                           OR value_id LIKE ('%' || :val))
                                    ORDER BY 
                                      CASE WHEN value_id = :val THEN 1
                                           WHEN value_code = :val THEN 2
                                           WHEN value_id = (:attr_id || '_' || :val) THEN 3
                                           ELSE 4 END
                                    LIMIT 1
                                """)
                                disp = (await session.execute(q, {"attr_id": attr_id, "val": str(val).strip()})).scalar_one_or_none()
                                if disp:
                                    update_q = text(f"""
                                        UPDATE g2p_register_crop_sowns 
                                        SET {name_key} = :disp 
                                        WHERE internal_record_id = :rec_id
                                    """)
                                    await session.execute(update_q, {"disp": disp, "rec_id": intake_row.internal_record_id})
                except Exception as e:
                    _logger.debug("Error updating admin display names in register: %s", e)
                return res

            G2PIntakeFormDataService._insert_live_register_row = patched_insert_live_register_row
            _logger.info("ODK Hook: Patched G2PIntakeFormDataService._insert_live_register_row for admin unit display names")

        if hasattr(G2PIntakeFormDataService, "_odk_patched_validate_land_ids"):
            return
        G2PIntakeFormDataService._odk_patched_validate_land_ids = True
        orig_fn = G2PIntakeFormDataService._validate_land_ids_against_fayda_records

        async def patched_validate_land_ids(self, submission, session):
            try:
                return await orig_fn(self, submission, session)
            except Exception as exc:
                # If validation failed because land_id was not yet in active registers,
                # check if it exists in pending intake forms
                fayda_fan_id = None
                sections = await self._get_form_sections(submission.form_id, session)
                sowing_land_ids = set()
                infestation_land_ids = set()
                harvest_land_ids = set()

                for section in sections:
                    _reg_def, intake_cls, _reg_cls, _schema_cls, _hist_cls = (
                        await self._resolve_submission_models(section.section_register_id, session)
                    )
                    rows = (
                        await session.execute(
                            select(intake_cls).where(
                                *self._submission_section_filters(
                                    intake_cls,
                                    submission.submission_id,
                                    section.section_id,
                                )
                            )
                        )
                    ).scalars().all()

                    for row in rows:
                        if not fayda_fan_id and hasattr(row, "fayda_fan_id") and getattr(row, "fayda_fan_id"):
                            fayda_fan_id = getattr(row, "fayda_fan_id")
                        land_id = getattr(row, "land_id", None)
                        if land_id and str(land_id).strip():
                            clean_land = str(land_id).strip()
                            reg_mnemonic = _reg_def.register_mnemonic
                            if reg_mnemonic == "Sowing":
                                sowing_land_ids.add(clean_land)
                            elif reg_mnemonic == "Infestation":
                                infestation_land_ids.add(clean_land)
                            elif reg_mnemonic == "Harvest":
                                harvest_land_ids.add(clean_land)

                all_check_lands = sowing_land_ids | infestation_land_ids | harvest_land_ids
                if not all_check_lands:
                    raise exc

                intake_lands = set()
                if fayda_fan_id:
                    res_fayda = (
                        await session.execute(
                            text("""
                                SELECT DISTINCT p.land_id 
                                FROM g2p_intake_form_plannings p
                                JOIN g2p_intake_form_crop_sowns cs ON p.submission_id = cs.submission_id
                                WHERE cs.fayda_fan_id = :fayda AND p.land_id IS NOT NULL
                                UNION
                                SELECT DISTINCT c.land_id 
                                FROM g2p_intake_form_cultivations c
                                JOIN g2p_intake_form_crop_sowns cs ON c.submission_id = cs.submission_id
                                WHERE cs.fayda_fan_id = :fayda AND c.land_id IS NOT NULL
                                UNION
                                SELECT DISTINCT s.land_id 
                                FROM g2p_intake_form_sowings s
                                JOIN g2p_intake_form_crop_sowns cs ON s.submission_id = cs.submission_id
                                WHERE cs.fayda_fan_id = :fayda AND s.land_id IS NOT NULL
                            """),
                            {"fayda": fayda_fan_id}
                        )
                    ).scalars().all()
                    intake_lands.update([str(l).strip() for l in res_fayda if l and str(l).strip()])

                res_any = (
                    await session.execute(
                        text("""
                            SELECT DISTINCT land_id FROM g2p_intake_form_plannings WHERE land_id IS NOT NULL
                            UNION
                            SELECT DISTINCT land_id FROM g2p_intake_form_cultivations WHERE land_id IS NOT NULL
                            UNION
                            SELECT DISTINCT land_id FROM g2p_intake_form_sowings WHERE land_id IS NOT NULL
                        """)
                    )
                ).scalars().all()
                intake_lands.update([str(l).strip() for l in res_any if l and str(l).strip()])

                if all_check_lands.issubset(intake_lands):
                    return
                raise exc

        G2PIntakeFormDataService._validate_land_ids_against_fayda_records = patched_validate_land_ids
        _logger.info("ODK Hook: Patched G2PIntakeFormDataService._validate_land_ids_against_fayda_records")
    except Exception as e:
        _logger.debug("Could not patch G2PIntakeFormDataService: %s", e)


def _patch_crop_sown_service():
    """Skip only H5/H6 identity cross-record mismatches during ODK ingestion."""
    try:
        from openg2p_registry_cropsown_extension.register_domain.services.g2p_register_domain_service_crop_sown import (
            G2PRegisterDomainServiceCropSown,
        )
        from openg2p_registry_core.errors import G2PRegistryException

        if hasattr(G2PRegisterDomainServiceCropSown, "_odk_patched_fayda_checks"):
            return
        G2PRegisterDomainServiceCropSown._odk_patched_fayda_checks = True
        orig_validate_fayda_season_and_year = (
            G2PRegisterDomainServiceCropSown._validate_fayda_season_and_year
        )

        async def patched_validate_fayda_season_and_year(self, record: dict, session):
            try:
                await orig_validate_fayda_season_and_year(self, record, session)
            except G2PRegistryException as validation_exc:
                if _active_session.get() is not session:
                    raise

                reason = str(validation_exc)
                if "does not match registered Crop Season" in reason:
                    rule_id = "H5"
                elif "does not match registered Crop Year" in reason:
                    rule_id = "H6"
                else:
                    raise

                _logger.warning(
                    "ODK identity validation skipped: %s reason=%s fayda_id=%s submission_id=%s",
                    rule_id,
                    reason,
                    record.get("fayda_fan_id") or record.get("fayda_id"),
                    record.get("submission_id"),
                )

        G2PRegisterDomainServiceCropSown._validate_fayda_season_and_year = (
            patched_validate_fayda_season_and_year
        )
        _logger.info("ODK Hook: Patched G2PRegisterDomainServiceCropSown H5/H6")
    except Exception as e:
        _logger.debug("Could not patch G2PRegisterDomainServiceCropSown H5/H6: %s", e)


def _patch_cultivation_service():
    """Patch G2PRegisterDomainServiceCultivation to fall back to intake form plannings."""
    try:
        from openg2p_registry_cropsown_extension.register_domain.services.g2p_register_domain_service_cultivation import (
            G2PRegisterDomainServiceCultivation,
        )
        from openg2p_registry_cropsown_extension.register_domain.services.domain_validation_utils import parse_date
        from openg2p_registry_core.errors import G2PRegistryException
        from sqlalchemy import text

        if hasattr(G2PRegisterDomainServiceCultivation, "_odk_patched_cultivation"):
            return
        G2PRegisterDomainServiceCultivation._odk_patched_cultivation = True

        orig_resolve_planning_date = G2PRegisterDomainServiceCultivation._resolve_planning_date
        orig_resolve_season_bounds = G2PRegisterDomainServiceCultivation._resolve_season_bounds
        orig_validate_date_after_planning = G2PRegisterDomainServiceCultivation._validate_date_after_planning

        async def patched_validate_date_after_planning(self, record: dict, session):
            try:
                await orig_validate_date_after_planning(self, record, session)
            except G2PRegistryException as exc:
                if _active_session.get() is not session:
                    raise
                _logger.warning(
                    "ODK cross-stage validation skipped: C6 reason=%s land_id=%s submission_id=%s",
                    str(exc), record.get("land_id"), record.get("submission_id"),
                )

        async def patched_resolve_planning_date(self, record: dict, session):
            res = await orig_resolve_planning_date(self, record, session)
            if res is not None:
                return res
            if not session:
                return None
            land_id = str(record.get("land_id") or "").strip()
            if land_id:
                res_in = await session.execute(
                    text("SELECT planned_date FROM g2p_intake_form_plannings WHERE land_id = :land_id ORDER BY created_at DESC LIMIT 1"),
                    {"land_id": land_id}
                )
                row_in = res_in.fetchone()
                if row_in and row_in[0]:
                    return parse_date(row_in[0])
            return None

        async def patched_resolve_season_bounds(self, record: dict, session):
            s_val, e_val = await orig_resolve_season_bounds(self, record, session)
            if s_val is not None and e_val is not None:
                return s_val, e_val
            if not session:
                return s_val, e_val
            land_id = str(record.get("land_id") or "").strip()
            if land_id:
                res_in = await session.execute(
                    text("SELECT start_gc, end_gc FROM g2p_intake_form_plannings WHERE land_id = :land_id ORDER BY created_at DESC LIMIT 1"),
                    {"land_id": land_id}
                )
                row_in = res_in.fetchone()
                if row_in and (row_in[0] or row_in[1]):
                    s = parse_date(row_in[0]) if row_in[0] else s_val
                    e = parse_date(row_in[1]) if row_in[1] else e_val
                    return s, e
            return s_val, e_val

        G2PRegisterDomainServiceCultivation._resolve_planning_date = patched_resolve_planning_date
        G2PRegisterDomainServiceCultivation._resolve_season_bounds = patched_resolve_season_bounds
        G2PRegisterDomainServiceCultivation._validate_date_after_planning = patched_validate_date_after_planning
        _logger.info("ODK Hook: Patched G2PRegisterDomainServiceCultivation")
    except Exception as e:
        _logger.debug("Could not patch G2PRegisterDomainServiceCultivation: %s", e)


def _patch_sowing_service():
    """Patch G2PRegisterDomainServiceSowing with intake form fallbacks."""
    try:
        from openg2p_registry_cropsown_extension.register_domain.services.g2p_register_domain_service_sowing import (
            G2PRegisterDomainServiceSowing,
        )
        from openg2p_registry_cropsown_extension.register_domain.services.domain_validation_utils import (
            parse_date,
            validation_error,
        )
        from openg2p_registry_core.errors import G2PRegistryException
        from sqlalchemy import text

        if hasattr(G2PRegisterDomainServiceSowing, "_odk_patched_sowing"):
            return
        G2PRegisterDomainServiceSowing._odk_patched_sowing = True

        orig_validate_sowing_area = G2PRegisterDomainServiceSowing._validate_sowing_area_after_cultivation
        orig_validate_sowing_after_cult = G2PRegisterDomainServiceSowing._validate_sowing_after_cultivation
        orig_validate_land_id = G2PRegisterDomainServiceSowing._validate_land_id_matches_planning

        async def patched_validate_sowing_area(self, record: dict, session):
            try:
                try:
                    await orig_validate_sowing_area(self, record, session)
                except G2PRegistryException as validation_exc:
                    if _active_session.get() is session:
                        _logger.warning(
                            "ODK cross-stage validation skipped: SW6 reason=%s land_id=%s submission_id=%s",
                            str(validation_exc), record.get("land_id"), record.get("submission_id"),
                        )
                        return
                    raise
            except Exception as exc:
                land_id = str(record.get("land_id") or "").strip()
                area_sown = float(record.get("area_sown") or 0)
                if session and land_id:
                    res_ic = await session.execute(
                        text("SELECT actual_crop_area FROM g2p_intake_form_cultivations WHERE TRIM(land_id) = :land_id AND actual_crop_area IS NOT NULL ORDER BY created_at DESC LIMIT 1"),
                        {"land_id": land_id}
                    )
                    row_ic = res_ic.fetchone()
                    if row_ic and row_ic[0] is not None:
                        max_area = float(row_ic[0])
                        if area_sown > max_area:
                            validation_error(
                                f"Area Sown ({area_sown}) cannot exceed Cultivated Area ({max_area}) for Land ID '{land_id}'."
                            )
                        return
                raise exc

        async def patched_validate_sowing_after_cult(self, record: dict, session):
            try:
                try:
                    await orig_validate_sowing_after_cult(self, record, session)
                except G2PRegistryException as validation_exc:
                    if _active_session.get() is session:
                        _logger.warning(
                            "ODK cross-stage validation skipped: SW5 reason=%s land_id=%s submission_id=%s",
                            str(validation_exc), record.get("land_id"), record.get("submission_id"),
                        )
                        return
                    raise
            except Exception as exc:
                sowing_date = parse_date(record.get("sowing_date"))
                land_id = str(record.get("land_id") or "").strip()
                if session and land_id and sowing_date:
                    prior_date = None
                    prior_stage = None
                    res_ic = await session.execute(
                        text("SELECT actual_cultivation_date FROM g2p_intake_form_cultivations WHERE land_id = :land_id ORDER BY created_at DESC LIMIT 1"),
                        {"land_id": land_id}
                    )
                    row_ic = res_ic.fetchone()
                    if row_ic and row_ic[0]:
                        prior_date = parse_date(row_ic[0])
                        prior_stage = "Cultivation Date"
                    else:
                        res_ip = await session.execute(
                            text("SELECT planned_date FROM g2p_intake_form_plannings WHERE land_id = :land_id ORDER BY created_at DESC LIMIT 1"),
                            {"land_id": land_id}
                        )
                        row_ip = res_ip.fetchone()
                        if row_ip and row_ip[0]:
                            prior_date = parse_date(row_ip[0])
                            prior_stage = "Planned Date"

                    if prior_date:
                        if sowing_date < prior_date:
                            validation_error(
                                f"Sowing Date ({sowing_date.strftime('%Y-%m-%d')}) cannot be earlier than "
                                f"{prior_stage} ({prior_date.strftime('%Y-%m-%d')})."
                            )
                        return
                raise exc

        async def patched_validate_land_id(self, record: dict, session):
            try:
                try:
                    await orig_validate_land_id(self, record, session)
                except G2PRegistryException as validation_exc:
                    if _active_session.get() is session:
                        _logger.warning(
                            "ODK cross-stage validation skipped: SW4 reason=%s land_id=%s submission_id=%s",
                            str(validation_exc), record.get("land_id"), record.get("submission_id"),
                        )
                        return
                    raise
            except Exception as exc:
                land_id = str(record.get("land_id") or "").strip()
                if session and land_id:
                    for tbl in ("g2p_intake_form_plannings", "g2p_intake_form_cultivations"):
                        res = await session.execute(
                            text(f"SELECT land_id FROM {tbl} WHERE land_id = :land_id LIMIT 1"),
                            {"land_id": land_id}
                        )
                        if res.fetchone():
                            return
                raise exc

        G2PRegisterDomainServiceSowing._validate_sowing_area_after_cultivation = patched_validate_sowing_area
        G2PRegisterDomainServiceSowing._validate_sowing_after_cultivation = patched_validate_sowing_after_cult
        G2PRegisterDomainServiceSowing._validate_land_id_matches_planning = patched_validate_land_id
        _logger.info("ODK Hook: Patched G2PRegisterDomainServiceSowing")
    except Exception as e:
        _logger.debug("Could not patch G2PRegisterDomainServiceSowing: %s", e)


def _patch_harvest_service():
    """Patch G2PRegisterDomainServiceHarvest with intake form fallbacks and date comparison."""
    try:
        from openg2p_registry_cropsown_extension.register_domain.services.g2p_register_domain_service_harvest import (
            G2PRegisterDomainServiceHarvest,
        )
        from openg2p_registry_cropsown_extension.register_domain.services.domain_validation_utils import (
            as_float,
            get_attribute_variants,
            parse_date,
            validation_error,
        )
        from openg2p_registry_core.errors import G2PRegistryException
        from sqlalchemy import text

        if hasattr(G2PRegisterDomainServiceHarvest, "_odk_patched_harvest"):
            return
        G2PRegisterDomainServiceHarvest._odk_patched_harvest = True

        orig_validate_harvest_after_sowing = G2PRegisterDomainServiceHarvest._validate_harvest_after_sowing
        orig_validate_harvest_area = G2PRegisterDomainServiceHarvest._validate_harvest_area_after_sowing
        orig_validate_land_id = G2PRegisterDomainServiceHarvest._validate_land_id_matches_sowing
        orig_validate_harvest_season_date = G2PRegisterDomainServiceHarvest._validate_date_in_season_enhanced

        async def patched_validate_harvest_season_date(self, record: dict, field: str, session):
            try:
                await orig_validate_harvest_season_date(self, record, field, session)
            except G2PRegistryException as validation_exc:
                if _active_session.get() is not session:
                    raise
                if not str(validation_exc).startswith("Cluster Harvest Date ("):
                    raise
                _logger.warning(
                    "ODK cross-stage validation skipped: HV3 reason=%s land_id=%s submission_id=%s field=%s",
                    str(validation_exc), record.get("land_id"), record.get("submission_id"), field,
                )

        async def patched_validate_harvest_after_sowing(self, record: dict, session):
            harvest_date = parse_date(record.get("harvest_date"))
            if harvest_date is None:
                return
            try:
                try:
                    await orig_validate_harvest_after_sowing(self, record, session)
                except G2PRegistryException as validation_exc:
                    if _active_session.get() is session:
                        reason = str(validation_exc)
                        if "A sowing record is required" in reason:
                            rule_id = "HV6"
                        elif "must be after the Sowing Date" in reason:
                            rule_id = "HV5"
                        else:
                            raise
                        _logger.warning(
                            "ODK cross-stage validation skipped: %s reason=%s land_id=%s submission_id=%s",
                            rule_id, reason, record.get("land_id"), record.get("submission_id"),
                        )
                        return
                    raise
            except Exception as exc:
                land_id = str(record.get("land_id") or "").strip()
                if session and land_id:
                    prior_date = None
                    prior_stage = None
                    # 1. Check active register sowings
                    res_s_reg = await session.execute(
                        text("SELECT sowing_date FROM g2p_register_sowings WHERE land_id = :land_id AND record_status = 'ACTIVE' ORDER BY created_at DESC LIMIT 1"),
                        {"land_id": land_id}
                    )
                    row_s_reg = res_s_reg.fetchone()
                    if row_s_reg and row_s_reg[0]:
                        prior_date = parse_date(row_s_reg[0])
                        prior_stage = "Sowing Date"
                    else:
                        # 2. Check intake form sowings
                        res_s = await session.execute(
                            text("SELECT sowing_date FROM g2p_intake_form_sowings WHERE land_id = :land_id ORDER BY created_at DESC LIMIT 1"),
                            {"land_id": land_id}
                        )
                        row_s = res_s.fetchone()
                        if row_s and row_s[0]:
                            prior_date = parse_date(row_s[0])
                            prior_stage = "Sowing Date"
                        else:
                            # 3. Check intake form cultivations
                            res_c = await session.execute(
                                text("SELECT actual_cultivation_date FROM g2p_intake_form_cultivations WHERE land_id = :land_id ORDER BY created_at DESC LIMIT 1"),
                                {"land_id": land_id}
                            )
                            row_c = res_c.fetchone()
                            if row_c and row_c[0]:
                                prior_date = parse_date(row_c[0])
                                prior_stage = "Cultivation Date"

                    if prior_date:
                        if harvest_date < prior_date:
                            validation_error(
                                f"Harvest Date ({harvest_date.strftime('%Y-%m-%d')}) cannot be earlier than "
                                f"{prior_stage} ({prior_date.strftime('%Y-%m-%d')})."
                            )
                        return
                raise exc

        async def patched_validate_harvest_area(self, record: dict, session):
            try:
                try:
                    await orig_validate_harvest_area(self, record, session)
                except G2PRegistryException as validation_exc:
                    if _active_session.get() is session:
                        reason = str(validation_exc)
                        if not ("Area Harvested (" in reason and "cannot exceed" in reason):
                            raise
                        _logger.warning(
                            "ODK cross-stage validation skipped: HV7 reason=%s land_id=%s submission_id=%s",
                            reason, record.get("land_id"), record.get("submission_id"),
                        )
                        return
                    raise
            except Exception as exc:
                land_id = str(record.get("land_id") or "").strip()
                area_harvested = float(record.get("area_harvested") or 0)
                if session and land_id:
                    res_s = await session.execute(
                        text("SELECT area_sown FROM g2p_intake_form_sowings WHERE TRIM(land_id) = :land_id AND area_sown IS NOT NULL ORDER BY created_at DESC LIMIT 1"),
                        {"land_id": land_id}
                    )
                    row_s = res_s.fetchone()
                    max_area = None
                    if row_s and row_s[0] is not None:
                        max_area = float(row_s[0])
                    else:
                        res_c = await session.execute(
                            text("SELECT actual_crop_area FROM g2p_intake_form_cultivations WHERE TRIM(land_id) = :land_id AND actual_crop_area IS NOT NULL ORDER BY created_at DESC LIMIT 1"),
                            {"land_id": land_id}
                        )
                        row_c = res_c.fetchone()
                        if row_c and row_c[0] is not None:
                            max_area = float(row_c[0])

                    if max_area is not None:
                        if area_harvested > max_area:
                            validation_error(
                                f"Area Harvested ({area_harvested}) cannot exceed Allowed Area ({max_area}) for Land ID '{land_id}'."
                            )
                        return
                raise exc

            # The domain validator above compares against the active register and
            # the current submission. ODK submits each lifecycle stage as a
            # separate intake submission, so an earlier pending ODK Sowing is not
            # visible to those queries. During ODK ingestion only, use that
            # staged Sowing as the HV7 comparison source and skip just this
            # cross-stage mismatch. Manual/UI calls keep the original behavior.
            if _active_session.get() is session and session:
                land_id = str(record.get("land_id") or "").strip()
                area_harvested = as_float(
                    record.get("area_harvested")
                    if record.get("area_harvested") is not None
                    else record.get("cluster_area_harvested")
                )
                if land_id and area_harvested is not None and area_harvested > 0:
                    season_vars = get_attribute_variants(record.get("season"), "CROP_SEASON")
                    query = (
                        "SELECT area_sown FROM g2p_intake_form_sowings "
                        "WHERE TRIM(land_id) = :land_id AND area_sown IS NOT NULL"
                    )
                    params = {"land_id": land_id}
                    if season_vars:
                        query += " AND season = ANY(:season_vars)"
                        params["season_vars"] = season_vars
                    query += " ORDER BY created_at DESC LIMIT 1"
                    result = await session.execute(text(query), params)
                    row = result.fetchone()
                    if row and row[0] is not None:
                        area_sown = float(row[0])
                        if area_harvested > area_sown:
                            _logger.warning(
                                "ODK cross-stage validation skipped: HV7 reason=%s "
                                "land_id=%s submission_id=%s",
                                f"Area Harvested ({area_harvested} ha) cannot exceed "
                                f"Area Sown in Sowing ({area_sown} ha).",
                                land_id,
                                record.get("submission_id"),
                            )
                            return

        async def patched_validate_land_id(self, record: dict, session):
            try:
                try:
                    await orig_validate_land_id(self, record, session)
                except G2PRegistryException as validation_exc:
                    if _active_session.get() is session:
                        _logger.warning(
                            "ODK cross-stage validation skipped: HV4 reason=%s land_id=%s submission_id=%s",
                            str(validation_exc), record.get("land_id"), record.get("submission_id"),
                        )
                        return
                    raise
            except Exception as exc:
                land_id = str(record.get("land_id") or "").strip()
                if session and land_id:
                    for tbl in ("g2p_intake_form_sowings", "g2p_intake_form_cultivations", "g2p_intake_form_plannings"):
                        res = await session.execute(
                            text(f"SELECT land_id FROM {tbl} WHERE land_id = :land_id LIMIT 1"),
                            {"land_id": land_id}
                        )
                        if res.fetchone():
                            return
                raise exc

        G2PRegisterDomainServiceHarvest._validate_harvest_after_sowing = patched_validate_harvest_after_sowing
        G2PRegisterDomainServiceHarvest._validate_harvest_area_after_sowing = patched_validate_harvest_area
        G2PRegisterDomainServiceHarvest._validate_land_id_matches_sowing = patched_validate_land_id
        G2PRegisterDomainServiceHarvest._validate_date_in_season_enhanced = patched_validate_harvest_season_date
        _logger.info("ODK Hook: Patched G2PRegisterDomainServiceHarvest")
    except Exception as e:
        _logger.debug("Could not patch G2PRegisterDomainServiceHarvest: %s", e)


def install_hooks():
    """Run hook initialization."""
    _alias_extension_modules()
    _patch_base_initializer()
    _patch_document_handler()
    _ensure_core_services()
    _ensure_dbengine_initialized()
    _ensure_master_data_engine()
    _connect_celery_signals()
    _patch_request_response_helper()
    _patch_celery_worker()
    _patch_intake_form_data_service()
    _patch_crop_sown_service()
    _patch_cultivation_service()
    _patch_sowing_service()
    _patch_harvest_service()


install_hooks()
