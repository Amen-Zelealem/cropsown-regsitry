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
        super().initialize()
        CoreInitializer().initialize()

        try:
            from . import odk_ingest_hooks  # noqa: F401
        except ImportError:
            pass

        G2PRegisterDomainFactory()
        G2PRegisterDomainServiceCropSown()
        G2PRegisterDomainServiceSowing()

        try:
            from .register_domain.controllers import G2PApproverResolverController
            G2PApproverResolverController().post_init()
        except ImportError:
            pass

        try:
            import openg2p_registry_staff_api.main as staff_main
            if hasattr(staff_main, "REGISTRY_STAFF_CSRF_EXCLUDED_PATHS"):
                if "/cropsown/approver-resolver" not in staff_main.REGISTRY_STAFF_CSRF_EXCLUDED_PATHS:
                    staff_main.REGISTRY_STAFF_CSRF_EXCLUDED_PATHS = (
                        *staff_main.REGISTRY_STAFF_CSRF_EXCLUDED_PATHS,
                        "/cropsown/approver-resolver",
                    )
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
