# ruff: noqa: E402
import asyncio
import logging

from .config import Settings

_config = Settings.get_config()

from openg2p_fastapi_common.app import Initializer as BaseInitializer
from openg2p_fastapi_common.context import dbengine
from openg2p_registry_core.app import Initializer as CoreInitializer

from .register_domain.models import (
    G2PRegisterFarmer, G2PRegisterHistoryFarmer, G2PIntakeFormFarmer,
    G2PRegisterCropSown, G2PRegisterHistoryCropSown,
    G2PRegisterPlanning, G2PRegisterHistoryPlanning,
    G2PRegisterCultivation, G2PRegisterHistoryCultivation,
    G2PRegisterSowing, G2PRegisterHistorySowing,
    G2PRegisterProduction, G2PRegisterHistoryProduction,
    G2PRegisterHarvest, G2PRegisterHistoryHarvest,
    G2PRegisterInfestation, G2PRegisterHistoryInfestation,
    G2PRegisterCluster, G2PRegisterHistoryCluster,
    G2PRegisterCultivationCluster, G2PRegisterHistoryCultivationCluster,
    G2PIntakeFormCropSown,
    G2PIntakeFormPlanning, G2PIntakeFormCultivation, G2PIntakeFormSowing,
    G2PIntakeFormProduction, G2PIntakeFormHarvest, G2PIntakeFormInfestation,
    G2PIntakeFormCluster, G2PIntakeFormCultivationCluster,
)

try:
    from .schema_sync import sync_schema
except ImportError:
    sync_schema = None

from .register_domain.factory import G2PRegisterDomainFactory
from .register_domain.services import (
    G2PRegisterDomainServiceCropSown,
    G2PRegisterDomainServiceSowing,
)

_logger = logging.getLogger(_config.logging_default_logger_name)


class Initializer(BaseInitializer):
    def initialize(self, **kwargs):
        try:
            import os
            from openg2p_fastapi_common.config import Settings as CommonSettings
            common_conf = CommonSettings.get_config(strict=False)
            if getattr(common_conf, "db_hostname", None) in (None, "localhost", "127.0.0.1"):
                common_conf.db_hostname = os.environ.get("COMMON_DB_HOSTNAME", os.environ.get("REGISTRY_STAFF_PORTAL_API_DB_HOSTNAME", "postgres"))
                common_conf.db_port = int(os.environ.get("COMMON_DB_PORT", os.environ.get("REGISTRY_STAFF_PORTAL_API_DB_PORT", 5432)))
                common_conf.db_dbname = os.environ.get("COMMON_DB_DBNAME", os.environ.get("REGISTRY_STAFF_PORTAL_API_DB_DBNAME", "cropsown"))
                common_conf.db_username = os.environ.get("COMMON_DB_USERNAME", os.environ.get("REGISTRY_STAFF_PORTAL_API_DB_USERNAME", "postgres"))
                common_conf.db_password = os.environ.get("COMMON_DB_PASSWORD", os.environ.get("REGISTRY_STAFF_PORTAL_API_DB_PASSWORD", "postgres"))
                common_conf.db_driver = "postgresql+asyncpg"
                common_conf.db_datasource = f"{common_conf.db_driver}://{common_conf.db_username}:{common_conf.db_password}@{common_conf.db_hostname}:{common_conf.db_port}/{common_conf.db_dbname}"
        except Exception as exc:
            _logger.warning("Could not set common db config: %s", exc)

        super().initialize()
        CoreInitializer().initialize()

        try:
            import os
            from openg2p_registry_core.config import Settings as CoreSettings
            core_conf = CoreSettings.get_config(strict=False)
            if not getattr(core_conf, "awe_callback_hmac_secret", None):
                core_conf.awe_callback_hmac_secret = os.environ.get(
                    "REGISTRY_CORE_AWE_CALLBACK_HMAC_SECRET",
                    os.environ.get("REGISTRY_STAFF_PORTAL_API_AWE_CALLBACK_HMAC_SECRET", "dev-registry-awe-callback-secret")
                )
            if not getattr(core_conf, "awe_callback_secret_id", None):
                core_conf.awe_callback_secret_id = os.environ.get(
                    "REGISTRY_CORE_AWE_CALLBACK_SECRET_ID",
                    os.environ.get("REGISTRY_STAFF_PORTAL_API_AWE_CALLBACK_SECRET_ID", "00000000-0000-4000-8000-000000000001")
                )
            if not getattr(core_conf, "awe_default_callback_url", None):
                core_conf.awe_default_callback_url = os.environ.get(
                    "REGISTRY_CORE_AWE_DEFAULT_CALLBACK_URL",
                    os.environ.get("REGISTRY_STAFF_PORTAL_API_AWE_DEFAULT_CALLBACK_URL", "http://staff-api:8000/awe/webhooks/decision")
                )
            if not getattr(core_conf, "awe_base_url", None) or core_conf.awe_base_url == "http://localhost:8000":
                core_conf.awe_base_url = os.environ.get(
                    "REGISTRY_CORE_AWE_BASE_URL",
                    os.environ.get("REGISTRY_STAFF_PORTAL_API_AWE_BASE_URL", "http://awe:8000")
                )
            if not getattr(core_conf, "awe_enabled", False):
                core_conf.awe_enabled = True
        except Exception as exc:
            _logger.warning("Could not set core AWE config: %s", exc)

        try:
            import os
            from iam_core.user_auth.config import Settings as IamSettings
            iam_conf = IamSettings.get_config(strict=False)
            if getattr(iam_conf, "auth_redis_url", None) in (None, "redis://localhost:6379/0"):
                iam_conf.auth_redis_url = os.environ.get("REGISTRY_STAFF_PORTAL_API_AUTH_REDIS_URL", "redis://redis:6379/0")
            if not getattr(iam_conf, "auth_provider_api_url", None):
                iam_conf.auth_provider_api_url = os.environ.get("REGISTRY_STAFF_PORTAL_API_AUTH_PROVIDER_API_URL", "http://iam:8000")
        except Exception as exc:
            _logger.warning("Could not set iam_core auth_redis_url: %s", exc)

        try:
            from . import odk_ingest_hooks  # noqa: F401
        except ImportError:
            pass

        G2PRegisterDomainFactory()
        G2PRegisterDomainServiceCropSown()
        G2PRegisterDomainServiceSowing()

        try:
            from .register_domain.services.cropsown_intake_validation_service import setup_intake_hooks
            setup_intake_hooks()
        except Exception as exc:
            _logger.warning("Could not initialize cropsown intake hooks: %s", exc)

        try:
            from .register_domain.controllers import (
                G2PApproverResolverController,
                G2PAweTasksStatsController,
            )
            G2PApproverResolverController().post_init()
            G2PAweTasksStatsController().post_init()
        except Exception as exc:
            _logger.warning("Could not initialize cropsown controllers: %s", exc)

        try:
            import openg2p_registry_staff_api.main as staff_main
            if hasattr(staff_main, "REGISTRY_STAFF_CSRF_EXCLUDED_PATHS"):
                excluded = set(staff_main.REGISTRY_STAFF_CSRF_EXCLUDED_PATHS)
                excluded.update([
                    "/cropsown/approver-resolver",
                    "/v1/awe/tasks/stats",
                    "/awe/tasks/stats",
                    "/v1/awe/requests",
                    "/awe/requests",
                ])
                staff_main.REGISTRY_STAFF_CSRF_EXCLUDED_PATHS = tuple(excluded)
        except Exception as exc:
            _logger.debug("Could not add CSRF exemption to staff-api: %s", exc)


    def migrate_database(self, args):

        async def migrate():
            _logger.info("Migrating extensions database")

            # create_migrate() creates tables that do not exist yet but never
            # alters one that does, so a column added to a model would never
            # reach an existing database. sync_schema() then adds those columns
            # (and reports renames/removals/type changes, which it leaves alone).
            for model in MIGRATED_MODELS:
                await model.create_migrate()

            if sync_schema:
                await sync_schema(dbengine.get(), MIGRATED_MODELS)

        asyncio.run(migrate())


# Every table this extension owns, in creation order. The crop sown record is
# the root: it carries the land attributes flat (land is not a register of its
# own) and every crop line hangs off it. A new model must be added here, or
# neither its table nor its later columns reach the database.
MIGRATED_MODELS = (
    # The Farmer identity register (its own tables); the two-CR flow and the
    # Farmer section of the intake form write here.
    G2PRegisterFarmer, G2PRegisterHistoryFarmer, G2PIntakeFormFarmer,
    G2PRegisterCropSown, G2PRegisterHistoryCropSown, G2PIntakeFormCropSown,
    # The seven crop lines, all children of the crop sown record.
    G2PRegisterPlanning, G2PRegisterHistoryPlanning, G2PIntakeFormPlanning,
    G2PRegisterCultivation, G2PRegisterHistoryCultivation, G2PIntakeFormCultivation,
    G2PRegisterSowing, G2PRegisterHistorySowing, G2PIntakeFormSowing,
    G2PRegisterProduction, G2PRegisterHistoryProduction, G2PIntakeFormProduction,
    G2PRegisterHarvest, G2PRegisterHistoryHarvest, G2PIntakeFormHarvest,
    G2PRegisterInfestation, G2PRegisterHistoryInfestation, G2PIntakeFormInfestation,
    G2PRegisterCluster, G2PRegisterHistoryCluster, G2PIntakeFormCluster,
    G2PRegisterCultivationCluster, G2PRegisterHistoryCultivationCluster,
    G2PIntakeFormCultivationCluster,
)
