"""Infestation Incident lines — a child of CROP_SOWN_RECORDS.

The ERD links every crop line straight to the crop sown record, so this register
sits directly under CropSown with no intermediate land/sowing level; the plot it
applies to is named by `land_uuid` (the stable generated key, not shown in
the UI) and carries the operator-facing `land_id` alongside it.
"""

from datetime import date

from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from openg2p_registry_core.models import G2PRegister, G2PRegisterHistory
from sqlalchemy import Boolean, Date, Integer, Numeric, String, select, event, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
import datetime

from ..services import G2PRegisterDomainServiceInfestation
from .enums import GrowthStageEnum, SeverityLevelEnum


class G2PInfestation:
    infestation_id: Mapped[str] = mapped_column(String, nullable=True)
    # ── Plot: each line records the land it was worked on (Gen1 puts
    # land_info_id and its attributes on the line, not the header) ───────────
    land_id: Mapped[str] = mapped_column(String, nullable=True)
    season: Mapped[str] = mapped_column(String, nullable=True)                # Attribute lookup (CROP_SEASON)
    commodity: Mapped[str] = mapped_column(String, nullable=True)             # Attribute lookup (CROP_COMMODITY)
    growth_stage: Mapped[GrowthStageEnum] = mapped_column(String, nullable=True) # GrowthStageEnum
    cluster_status: Mapped[str] = mapped_column(String, nullable=True)
    cluster_name: Mapped[str] = mapped_column(String, nullable=True)
    infestation_type: Mapped[str] = mapped_column(String, nullable=True)      # Attribute lookup (INFESTATION_TYPE)
    pest_name: Mapped[str] = mapped_column(String, nullable=True)             # Attribute lookup (PEST)
    weed_name: Mapped[str] = mapped_column(String, nullable=True)             # Attribute lookup (WEED)
    disease_name: Mapped[str] = mapped_column(String, nullable=True)          # Attribute lookup (CROP_DISEASE)
    disease_type: Mapped[str] = mapped_column(String, nullable=True)
    disease_control_method: Mapped[str] = mapped_column(String, nullable=True)
    disease_frequency_of_application: Mapped[str] = mapped_column(String, nullable=True)

    pest_type: Mapped[str] = mapped_column(String, nullable=True)
    pesticide_name: Mapped[str] = mapped_column(String, nullable=True)
    pesticide_type: Mapped[str] = mapped_column(String, nullable=True)
    pesticide_method: Mapped[str] = mapped_column(String, nullable=True)
    pesticide_frequency: Mapped[str] = mapped_column(String, nullable=True)

    weed_type: Mapped[str] = mapped_column(String, nullable=True)
    weed_control_method: Mapped[str] = mapped_column(String, nullable=True)
    weedicide_name: Mapped[str] = mapped_column(String, nullable=True)
    weedicide_type: Mapped[str] = mapped_column(String, nullable=True)
    weedicide_frequency: Mapped[str] = mapped_column(String, nullable=True)

    fungicide_name: Mapped[str] = mapped_column(String, nullable=True)
    fungicide_type: Mapped[str] = mapped_column(String, nullable=True)

    nutrient_type: Mapped[str] = mapped_column(String, nullable=True)
    nutrient_name: Mapped[str] = mapped_column(String, nullable=True)
    nutrient_control_method: Mapped[str] = mapped_column(String, nullable=True)
    nutrient_fertilizer_type: Mapped[str] = mapped_column(String, nullable=True)
    nutrient_fertilizer_name: Mapped[str] = mapped_column(String, nullable=True)
    nutrient_frequency_of_application: Mapped[str] = mapped_column(String, nullable=True)

    shock_type: Mapped[str] = mapped_column(String, nullable=True)
    shock_event_name: Mapped[str] = mapped_column(String, nullable=True)
    climate_control_method: Mapped[str] = mapped_column(String, nullable=True)
    recovery_input_type: Mapped[str] = mapped_column(String, nullable=True)
    recovery_input_name: Mapped[str] = mapped_column(String, nullable=True)
    climate_frequency_of_application: Mapped[str] = mapped_column(String, nullable=True)

    severity_level: Mapped[SeverityLevelEnum] = mapped_column(String, nullable=True) # SeverityLevelEnum
    estimated_damage_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=True)
    observation_date: Mapped[str] = mapped_column(Date, nullable=True)
    geo_tagged_photo_document_id: Mapped[str] = mapped_column(String, nullable=True)
    action_taken: Mapped[str] = mapped_column(String, nullable=True)

    temporary_land_id: Mapped[str] = mapped_column(String, nullable=True)
    sync_id: Mapped[str] = mapped_column(String, nullable=True, index=True)
    observation_date_ec: Mapped[str] = mapped_column(String, nullable=True)





# All Register classes should have the prefix G2PRegister
class G2PRegisterInfestation(G2PRegister, G2PInfestation):
    __tablename__ = "g2p_register_infestations"
    __table_args__ = {"extend_existing": True}

    def get_search_text_fields(self) -> str:
        """Return infestation incident fields used to build search_text."""
        return G2PRegisterDomainServiceInfestation().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return infestation incident record_name from domain service implementation."""
        return G2PRegisterDomainServiceInfestation().construct_record_name(self.to_dict())


# All Register History classes should have the prefix G2PRegisterHistory
class G2PRegisterHistoryInfestation(G2PRegisterHistory, G2PInfestation):
    __tablename__ = "g2p_register_history_infestations"
    __table_args__ = {"extend_existing": True}


# All Intake Form classes should have the prefix G2PIntakeForm
class G2PIntakeFormInfestation(G2PIntakeForm, G2PRegister, G2PInfestation):
    __tablename__ = "g2p_intake_form_infestations"
    __table_args__ = {"extend_existing": True}

    async def get_link_internal_record_id(self, session):
        from .crop_sown import G2PIntakeFormCropSown
        result = await session.execute(
            select(G2PIntakeFormCropSown).where(
                G2PIntakeFormCropSown.submission_id == self.submission_id
            )
        )
        crop_sown = result.scalars().first()
        if crop_sown:
            self.link_internal_record_id = crop_sown.internal_record_id

    def get_search_text_fields(self) -> str:
        """Return infestation incident fields used to build search_text."""
        return G2PRegisterDomainServiceInfestation().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return infestation incident record_name from domain service implementation."""
        return G2PRegisterDomainServiceInfestation().construct_record_name(self.to_dict())

def generate_infestation_id(mapper, connection, target):
    if not getattr(target, 'infestation_id', None):
        current_year = datetime.date.today().year
        prefix = f"PI/{current_year}/"

        table = target.__table__
        stmt = select(func.max(table.c.infestation_id)).where(table.c.infestation_id.like(f"{prefix}%"))

        result = connection.execute(stmt).scalar()
        if result:
            try:
                last_seq = int(result.split("/")[-1])
                new_seq = last_seq + 1
            except ValueError:
                new_seq = 1
        else:
            new_seq = 1

        target.infestation_id = f"{prefix}{new_seq:05d}"

event.listen(G2PRegisterInfestation, 'before_insert', generate_infestation_id)
event.listen(G2PIntakeFormInfestation, 'before_insert', generate_infestation_id)
