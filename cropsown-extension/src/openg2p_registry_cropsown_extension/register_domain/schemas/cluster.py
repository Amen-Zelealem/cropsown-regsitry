from datetime import date
from typing import Optional

from openg2p_registry_core.schemas import (
    G2PRegisterBaseSchema,
    G2PGeoSchema,
    G2PRegisterHistorySchema,
    G2PGeoHistorySchema,
    G2PIntakeFormSchemaBase,
)
from ..models.enums import AgroEcologicalZoneEnum


class G2PSchemaCluster:
    temporary_land_id: Optional[str] = None
    sync_id: Optional[str] = None
    start_gc: Optional[date] = None
    start_month: Optional[int] = None
    start_day: Optional[int] = None
    end_gc: Optional[date] = None
    end_month: Optional[int] = None
    end_day: Optional[int] = None
    cluster_id: Optional[str] = None
    cluster_area_timad: Optional[float] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    altitude: Optional[str] = None
    cluster_plan: Optional[float] = None
    cluster_collected_land: Optional[float] = None

    collected_by_combiner: Optional[float] = None
    land_id: Optional[str] = None
    region: Optional[str] = None
    zone: Optional[str] = None
    woreda: Optional[str] = None
    kebele: Optional[str] = None
    sub_kebele: Optional[str] = None
    cluster_name: Optional[str] = None
    agro_ecological_zone: Optional[AgroEcologicalZoneEnum] = None
    season: Optional[str] = None
    cluster_area_hectare: Optional[float] = None
    number_of_smallholders: Optional[int] = None
    collected_land: Optional[float] = None
    collected_quintal: Optional[float] = None
    water_source: Optional[str] = None
    water_source_method: Optional[str] = None
    water_source_frequency: Optional[str] = None
    establishing_date: Optional[date] = None
    establishing_date_ec: Optional[str] = None
    reference: Optional[str] = None
    primary_commodity: Optional[str] = None
    secondary_commodity: Optional[str] = None
    fpc_type: Optional[str] = None
    leader: Optional[str] = None
    co_leader: Optional[str] = None
    coordinator: Optional[str] = None
    secretary: Optional[str] = None
    da_name: Optional[str] = None
    da_mobile_number: Optional[str] = None
    supervisor_name: Optional[str] = None
    supervisor_mobile_number: Optional[str] = None


class G2PRegisterSchemaCluster(G2PRegisterBaseSchema, G2PGeoSchema, G2PSchemaCluster):
    """
    Schema for Cluster Information register.
    Inherits fields from G2PRegisterBaseSchema, G2PGeoSchema.
    Attributes inherited from G2PSchemaCluster are specific to the Cluster Information domain.
    """


class G2PRegisterHistorySchemaCluster(G2PRegisterHistorySchema, G2PGeoHistorySchema, G2PSchemaCluster):
    """
    Schema for Cluster Information history.
    Inherits fields from G2PRegisterHistorySchema, G2PGeoHistorySchema.
    """


class G2PIntakeFormSchemaCluster(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PGeoSchema, G2PSchemaCluster):
    """
    Schema for Cluster Information intake form.
    Inherits fields from G2PRegisterBaseSchema, G2PGeoSchema.
    Attributes inherited from G2PSchemaCluster are specific to the Cluster Information domain and are included in the intake form schema for data collection.
    """
