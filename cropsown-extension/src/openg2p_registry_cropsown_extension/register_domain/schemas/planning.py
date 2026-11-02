from datetime import date
from typing import Optional, List, Dict, Any
from pydantic import root_validator

from openg2p_registry_core.schemas import (
    G2PRegisterBaseSchema,
    G2PRegisterHistorySchema,
    G2PIntakeFormSchemaBase,
)
from ..models.enums import CroppingSystemEnum, SeedClassEnum, SeedSourceEnum


class G2PSchemaPlanning:

    is_plot_not_registered: Optional[bool] = None
    planning_id: Optional[str] = None
    temporary_land_id: Optional[str] = None
    sync_id: Optional[str] = None
    start_gc: Optional[date] = None
    start_month: Optional[int] = None
    start_day: Optional[int] = None
    end_gc: Optional[date] = None
    end_month: Optional[int] = None
    end_day: Optional[int] = None
    planned_date_ec: Optional[str] = None
    land_id: Optional[str] = None
    ownership_type: Optional[str] = None
    soil_fertility_type: Optional[str] = None
    plot_category: Optional[str] = None
    land_area: Optional[float] = None
    region: Optional[str] = None
    zone: Optional[str] = None
    woreda: Optional[str] = None
    kebele: Optional[str] = None
    gps_coordinate: Optional[str] = None
    season: Optional[str] = None
    commodity: Optional[str] = None
    crop_variety: Optional[str] = None
    crop_category: Optional[str] = None
    local_name: Optional[str] = None
    scientific_name: Optional[str] = None
    plot_category: Optional[str] = None
    cropping_system: Optional[str] = None
    planned_date: Optional[date] = None
    planned_area: Optional[float] = None
    growth_duration_days: Optional[int] = None
    expected_yield: Optional[float] = None
    seed_class: Optional[str] = None
    seed_source: Optional[str] = None
    seed_variety: Optional[str] = None
    planned_seed_qty: Optional[float] = None
    planned_fertilizer_type: Optional[str] = None
    planned_fertilizer_qty: Optional[float] = None
    planned_labor: Optional[int] = None
    water_source: Optional[str] = None
    water_source_method: Optional[str] = None
    water_source_frequency: Optional[str] = None
    start_gc: Optional[date] = None
    start_month: Optional[int] = None
    start_day: Optional[int] = None
    end_gc: Optional[date] = None
    end_month: Optional[int] = None
    end_day: Optional[int] = None
    planned_date_ec: Optional[str] = None

    cluster_details: Optional[List[Dict[str, Any]]] = None





    da_name: Optional[str] = None
    da_mobile_number: Optional[str] = None
    supervisor_name: Optional[str] = None
    supervisor_mobile_number: Optional[str] = None


class G2PRegisterSchemaPlanning(G2PRegisterBaseSchema, G2PSchemaPlanning):
    """
    Schema for Crop Planning register.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaPlanning are specific to the Crop Planning domain.
    """
    @root_validator(pre=False, skip_on_failure=True)
    def validate_planned_area(cls, values):
        land_area = values.get('land_area')
        planned_area = values.get('planned_area')
        if land_area is not None and planned_area is not None:
            if planned_area > land_area:
                raise ValueError("Planned crop area cannot be greater than total land area")
        return values


class G2PRegisterHistorySchemaPlanning(G2PRegisterHistorySchema, G2PSchemaPlanning):
    """
    Schema for Crop Planning history.
    Inherits fields from G2PRegisterHistorySchema.
    """


class G2PIntakeFormSchemaPlanning(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PSchemaPlanning):
    """
    Schema for Crop Planning intake form.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaPlanning are specific to the Crop Planning domain and are included in the intake form schema for data collection.
    """
    @root_validator(pre=False, skip_on_failure=True)
    def validate_planned_area(cls, values):
        land_area = values.get('land_area')
        planned_area = values.get('planned_area')
        if land_area is not None and planned_area is not None:
            if planned_area > land_area:
                raise ValueError("Planned crop area cannot be greater than total land area")
        return values
