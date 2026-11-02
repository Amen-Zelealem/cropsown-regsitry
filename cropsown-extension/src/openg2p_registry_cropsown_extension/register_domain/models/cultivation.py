"""Cultivation / Land Preparation lines — a child of CROP_SOWN_RECORDS.

The ERD links every crop line straight to the crop sown record, so this register
sits directly under CropSown with no intermediate land/sowing level; the plot it
applies to is named by `land_uuid` (the stable generated key, not shown in
the UI) and carries the operator-facing `land_id` alongside it.
"""

from datetime import date

from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from openg2p_registry_core.models import G2PRegister, G2PRegisterHistory
from sqlalchemy import Boolean, Date, Integer, Numeric, String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..services import G2PRegisterDomainServiceCultivation
from .enums import CroppingSystemEnum, SeedClassEnum, SeedSourceEnum


class G2PCultivation:
    # ── Plot: each line records the land it was worked on (Gen1 puts
    # land_info_id and its attributes on the line, not the header) ───────────
    land_id: Mapped[str] = mapped_column(String, nullable=True)
    ownership_type: Mapped[str] = mapped_column(String, nullable=True)        # Attribute lookup (OWNERSHIP_TYPE)
    soil_fertility_type: Mapped[str] = mapped_column(String, nullable=True)   # Attribute lookup (SOIL_FERTILITY)
    plot_category: Mapped[str] = mapped_column(String, nullable=True)         # Attribute lookup (PLOT_CATEGORY)
    land_area: Mapped[float] = mapped_column(Numeric, nullable=True)
    season: Mapped[str] = mapped_column(String, nullable=True)                # Attribute lookup (CROP_SEASON)
    commodity: Mapped[str] = mapped_column(String, nullable=True)             # Attribute lookup (CROP_COMMODITY)
    crop_variety: Mapped[str] = mapped_column(String, nullable=True)          # Attribute lookup (CROP_VARIETY)
    crop_category: Mapped[str] = mapped_column(String, nullable=True)         # Attribute lookup (CROP_CATEGORY)
    local_name: Mapped[str] = mapped_column(String, nullable=True)
    scientific_name: Mapped[str] = mapped_column(String, nullable=True)
    actual_yield: Mapped[float] = mapped_column(Numeric, nullable=True)
    land_prep_method: Mapped[list[str]] = mapped_column(JSONB, nullable=True)      # Attribute lookup (LAND_PREP_METHOD)
    cultivation_type: Mapped[str] = mapped_column(String, nullable=True)      # Attribute lookup (MACHINERY)
    cropping_system: Mapped[CroppingSystemEnum] = mapped_column(String, nullable=True) # CroppingSystemEnum
    actual_cultivation_date: Mapped[date] = mapped_column(Date, nullable=True)
    actual_crop_area: Mapped[float] = mapped_column(Numeric, nullable=True)
    actual_growth_duration_days: Mapped[int] = mapped_column(Integer, nullable=True)
    actual_seed_class: Mapped[SeedClassEnum] = mapped_column(String, nullable=True) # SeedClassEnum
    actual_seed_source: Mapped[SeedSourceEnum] = mapped_column(String, nullable=True) # SeedSourceEnum
    seed_variety: Mapped[str] = mapped_column(String, nullable=True)
    actual_seed_qty: Mapped[float] = mapped_column(Numeric, nullable=True)
    actual_fertilizer_type: Mapped[str] = mapped_column(String, nullable=True) # Attribute lookup (FERTILIZER_TYPE)
    actual_fertilizer_qty: Mapped[float] = mapped_column(Numeric, nullable=True)
    water_source: Mapped[str] = mapped_column(String, nullable=True)          # Attribute lookup (WATER_SOURCE)
    water_source_method: Mapped[str] = mapped_column(String, nullable=True)   # Attribute lookup (WATER_SOURCE_METHOD)
    water_source_frequency: Mapped[str] = mapped_column(String, nullable=True) # Attribute lookup (WATER_SOURCE_FREQUENCY)

    is_plot_not_registered: Mapped[bool] = mapped_column(Boolean, nullable=True)
    temporary_land_id: Mapped[str] = mapped_column(String, nullable=True)
    sync_id: Mapped[str] = mapped_column(String, nullable=True, index=True)
    # Season window. Gen1 stores the month/day pair alongside the date so a
    # planted date can be checked against the season regardless of year.
    start_gc: Mapped[date] = mapped_column(Date, nullable=True)
    start_month: Mapped[int] = mapped_column(Integer, nullable=True)
    start_day: Mapped[int] = mapped_column(Integer, nullable=True)
    end_gc: Mapped[date] = mapped_column(Date, nullable=True)
    end_month: Mapped[int] = mapped_column(Integer, nullable=True)
    end_day: Mapped[int] = mapped_column(Integer, nullable=True)
    actual_cultivation_date_ec: Mapped[str] = mapped_column(String, nullable=True)
    is_crop_changed: Mapped[bool] = mapped_column(Boolean, nullable=True)



    da_name: Mapped[str] = mapped_column(String, nullable=True)
    da_mobile_number: Mapped[str] = mapped_column(String, nullable=True)
    supervisor_name: Mapped[str] = mapped_column(String, nullable=True)
    supervisor_mobile_number: Mapped[str] = mapped_column(String, nullable=True)

# All Register classes should have the prefix G2PRegister
class G2PRegisterCultivation(G2PRegister, G2PCultivation):
    __tablename__ = "g2p_register_cultivations"
    __table_args__ = {"extend_existing": True}

    def get_search_text_fields(self) -> str:
        """Return cultivation / land preparation fields used to build search_text."""
        return G2PRegisterDomainServiceCultivation().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return cultivation / land preparation record_name from domain service implementation."""
        return G2PRegisterDomainServiceCultivation().construct_record_name(self.to_dict())


# All Register History classes should have the prefix G2PRegisterHistory
class G2PRegisterHistoryCultivation(G2PRegisterHistory, G2PCultivation):
    __tablename__ = "g2p_register_history_cultivations"
    __table_args__ = {"extend_existing": True}


# All Intake Form classes should have the prefix G2PIntakeForm
class G2PIntakeFormCultivation(G2PIntakeForm, G2PRegister, G2PCultivation):
    __tablename__ = "g2p_intake_form_cultivations"
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
        """Return cultivation / land preparation fields used to build search_text."""
        return G2PRegisterDomainServiceCultivation().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return cultivation / land preparation record_name from domain service implementation."""
        return G2PRegisterDomainServiceCultivation().construct_record_name(self.to_dict())
