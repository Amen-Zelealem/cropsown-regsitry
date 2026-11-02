from datetime import date
from typing import Any, List, Optional

from pydantic import field_validator

from openg2p_registry_core.schemas import (
    G2PRegisterBaseSchema,
    G2PRegisterHistorySchema,
    G2PIntakeFormSchemaBase,
)
from ..models.enums import CroppingSystemEnum, SeedClassEnum, SeedSourceEnum


def _coerce_str_list(value: Any) -> Any:
    """Normalise a multi-select value to a list."""
    if value is None or isinstance(value, list):
        return value
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",") if part.strip()]
        return parts or None
    return value


class G2PSchemaCultivation:

    is_plot_not_registered: Optional[bool] = None
    temporary_land_id: Optional[str] = None
    sync_id: Optional[str] = None
    start_gc: Optional[date] = None
    start_month: Optional[int] = None
    start_day: Optional[int] = None
    end_gc: Optional[date] = None
    end_month: Optional[int] = None
    end_day: Optional[int] = None
    actual_cultivation_date_ec: Optional[str] = None
    is_crop_changed: Optional[bool] = None
    land_id: Optional[str] = None
    ownership_type: Optional[str] = None
    soil_fertility_type: Optional[str] = None
    plot_category: Optional[str] = None
    land_area: Optional[float] = None
    season: Optional[str] = None
    commodity: Optional[str] = None
    crop_variety: Optional[str] = None
    crop_category: Optional[str] = None
    local_name: Optional[str] = None
    scientific_name: Optional[str] = None
    actual_yield: Optional[float] = None
    land_prep_method: Optional[List[str]] = None
    cultivation_type: Optional[str] = None
    cropping_system: Optional[str] = None
    actual_cultivation_date: Optional[date] = None
    actual_crop_area: Optional[float] = None
    actual_growth_duration_days: Optional[int] = None
    actual_seed_class: Optional[str] = None
    actual_seed_source: Optional[str] = None
    seed_variety: Optional[str] = None
    actual_seed_qty: Optional[float] = None
    actual_fertilizer_type: Optional[str] = None
    actual_fertilizer_qty: Optional[float] = None
    water_source: Optional[str] = None
    water_source_method: Optional[str] = None
    water_source_frequency: Optional[str] = None





    da_name: Optional[str] = None
    da_mobile_number: Optional[str] = None
    supervisor_name: Optional[str] = None
    supervisor_mobile_number: Optional[str] = None

    _coerce_land_prep_method = field_validator("land_prep_method", mode="before")(_coerce_str_list)


class G2PRegisterSchemaCultivation(G2PRegisterBaseSchema, G2PSchemaCultivation):
    """
    Schema for Cultivation / Land Preparation register.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaCultivation are specific to the Cultivation / Land Preparation domain.
    """


class G2PRegisterHistorySchemaCultivation(G2PRegisterHistorySchema, G2PSchemaCultivation):
    """
    Schema for Cultivation / Land Preparation history.
    Inherits fields from G2PRegisterHistorySchema.
    """


class G2PIntakeFormSchemaCultivation(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PSchemaCultivation):
    """
    Schema for Cultivation / Land Preparation intake form.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaCultivation are specific to the Cultivation / Land Preparation domain and are included in the intake form schema for data collection.
    """
