from datetime import date
from typing import Optional

from pydantic import field_validator

from openg2p_registry_core.schemas import (
    G2PRegisterBaseSchema,
    G2PRegisterHistorySchema,
    G2PIntakeFormSchemaBase,
)
from ..models.enums import CropMaturityStatusEnum
from .sowing import _coerce_str_list


class G2PSchemaHarvest:

    harvest_id: Optional[str] = None
    temporary_land_id: Optional[str] = None
    sync_id: Optional[str] = None
    harvest_date_ec: Optional[str] = None
    land_id: Optional[str] = None
    season: Optional[str] = None
    commodity: Optional[str] = None
    land_area: Optional[float] = None
    cluster_status: Optional[list[str]] = None
    cluster_name: Optional[str] = None
    crop_maturity_status: Optional[CropMaturityStatusEnum] = None
    harvest_date: Optional[date] = None
    area_harvested: Optional[float] = None
    qty_harvested: Optional[float] = None
    post_harvest_loss_pct: Optional[float] = None
    qty_stored: Optional[float] = None
    qty_sold: Optional[float] = None

    cluster_crop_maturity_status: Optional[CropMaturityStatusEnum] = None
    cluster_harvest_date: Optional[date] = None
    cluster_area_harvested: Optional[float] = None
    cluster_qty_harvested: Optional[float] = None
    cluster_post_harvest_loss_pct: Optional[float] = None
    cluster_qty_stored: Optional[float] = None
    cluster_qty_sold: Optional[float] = None

    yield_kg_ha: Optional[float] = None
    yield_performance_pct: Optional[float] = None
    fertilizer_efficiency: Optional[float] = None
    land_utilization_rate: Optional[float] = None
    seed_productivity: Optional[float] = None





    da_name: Optional[str] = None
    da_mobile_number: Optional[str] = None
    supervisor_name: Optional[str] = None
    supervisor_mobile_number: Optional[str] = None

    _coerce_cluster_status = field_validator("cluster_status", mode="before")(_coerce_str_list)


class G2PRegisterSchemaHarvest(G2PRegisterBaseSchema, G2PSchemaHarvest):
    """
    Schema for Harvest register.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaHarvest are specific to the Harvest domain.
    """


class G2PRegisterHistorySchemaHarvest(G2PRegisterHistorySchema, G2PSchemaHarvest):
    """
    Schema for Harvest history.
    Inherits fields from G2PRegisterHistorySchema.
    """


class G2PIntakeFormSchemaHarvest(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PSchemaHarvest):
    """
    Schema for Harvest intake form.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaHarvest are specific to the Harvest domain and are included in the intake form schema for data collection.
    """
