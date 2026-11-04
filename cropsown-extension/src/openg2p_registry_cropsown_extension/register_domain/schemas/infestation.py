from datetime import date
from typing import Optional, List

from openg2p_registry_core.schemas import (
    G2PRegisterBaseSchema,
    G2PRegisterHistorySchema,
    G2PIntakeFormSchemaBase,
)
from ..models.enums import GrowthStageEnum, SeverityLevelEnum


class G2PSchemaInfestation:

    infestation_id: Optional[str] = None
    temporary_land_id: Optional[str] = None
    sync_id: Optional[str] = None
    observation_date_ec: Optional[str] = None
    land_id: Optional[str] = None
    season: Optional[str] = None
    commodity: Optional[str] = None
    growth_stage: Optional[GrowthStageEnum] = None
    cluster_status: Optional[str] = None
    cluster_name: Optional[str] = None
    infestation_type: Optional[str] = None
    pest_name: Optional[str] = None
    weed_name: Optional[str] = None
    disease_name: Optional[str] = None
    disease_type: Optional[str] = None
    disease_control_method: Optional[str] = None
    disease_frequency_of_application: Optional[str] = None
    pest_type: Optional[str] = None
    pesticide_name: Optional[str] = None
    pesticide_type: Optional[str] = None
    pesticide_method: Optional[str] = None
    pesticide_frequency: Optional[str] = None
    weed_type: Optional[str] = None
    weed_control_method: Optional[str] = None
    weedicide_name: Optional[str] = None
    weedicide_type: Optional[str] = None
    weedicide_frequency: Optional[str] = None
    fungicide_name: Optional[str] = None
    fungicide_type: Optional[str] = None
    nutrient_type: Optional[str] = None
    nutrient_name: Optional[str] = None
    nutrient_control_method: Optional[str] = None
    nutrient_fertilizer_type: Optional[str] = None
    nutrient_fertilizer_name: Optional[str] = None
    nutrient_frequency_of_application: Optional[str] = None
    shock_type: Optional[str] = None
    shock_event_name: Optional[str] = None
    climate_control_method: Optional[str] = None
    recovery_input_type: Optional[str] = None
    recovery_input_name: Optional[str] = None
    climate_frequency_of_application: Optional[str] = None
    severity_level: Optional[SeverityLevelEnum] = None
    estimated_damage_pct: Optional[str] = None
    observation_date: Optional[date] = None
    geo_tagged_photo_document_id: Optional[str] = None
    action_taken: Optional[str] = None



class G2PRegisterSchemaInfestation(G2PRegisterBaseSchema, G2PSchemaInfestation):
    """
    Schema for Infestation Incident register.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaInfestation are specific to the Infestation Incident domain.
    """


class G2PRegisterHistorySchemaInfestation(G2PRegisterHistorySchema, G2PSchemaInfestation):
    """
    Schema for Infestation Incident history.
    Inherits fields from G2PRegisterHistorySchema.
    """


class G2PIntakeFormSchemaInfestation(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PSchemaInfestation):
    """
    Schema for Infestation Incident intake form.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaInfestation are specific to the Infestation Incident domain and are included in the intake form schema for data collection.
    """
