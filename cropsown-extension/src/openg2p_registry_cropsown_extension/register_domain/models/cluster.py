"""Cluster Information lines — a child of CROP_SOWN_RECORDS.

The ERD links every crop line straight to the crop sown record, so this register
sits directly under CropSown with no intermediate land/sowing level; the land it
applies to is named by `land_uuid`.
"""

from datetime import date

from openg2p_registry_core.models.g2p_intake_form import G2PIntakeForm
from openg2p_registry_core.models import G2PRegister, G2PRegisterHistory, G2PGeo, G2PGeoHistory
from sqlalchemy import Boolean, Date, Integer, Numeric, String, select, event, func
import datetime
from sqlalchemy.orm import Mapped, mapped_column

from ..services import G2PRegisterDomainServiceCluster
from .enums import AgroEcologicalZoneEnum


class G2PCluster:

    # ── Plot: each line records the land it was worked on (Gen1 puts
    # land_info_id and its attributes on the line, not the header) ───────────
    land_id: Mapped[str] = mapped_column(String, nullable=True)
    cluster_name: Mapped[str] = mapped_column(String, nullable=True)
    agro_ecological_zone: Mapped[AgroEcologicalZoneEnum] = mapped_column(String, nullable=True) # AgroEcologicalZoneEnum
    season: Mapped[str] = mapped_column(String, nullable=True)                # Attribute lookup (CROP_SEASON)
    cluster_area_hectare: Mapped[float] = mapped_column(Numeric, nullable=True)
    number_of_smallholders: Mapped[int] = mapped_column(Integer, nullable=True)
    collected_land: Mapped[float] = mapped_column(Numeric, nullable=True)
    collected_quintal: Mapped[float] = mapped_column(Numeric, nullable=True)
    water_source: Mapped[str] = mapped_column(String, nullable=True)          # Attribute lookup (WATER_SOURCE)
    water_source_method: Mapped[str] = mapped_column(String, nullable=True)   # Attribute lookup (WATER_SOURCE_METHOD)
    water_source_frequency: Mapped[str] = mapped_column(String, nullable=True) # Attribute lookup (WATER_SOURCE_FREQUENCY)
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
    cluster_id: Mapped[str] = mapped_column(String, nullable=True)
    cluster_area_timad: Mapped[float] = mapped_column(Numeric, nullable=True)
    region: Mapped[str] = mapped_column(String, nullable=True)
    zone: Mapped[str] = mapped_column(String, nullable=True)
    woreda: Mapped[str] = mapped_column(String, nullable=True)
    kebele: Mapped[str] = mapped_column(String, nullable=True)
    sub_kebele: Mapped[str] = mapped_column(String, nullable=True)

    # Planned figures, and the actuals Gen1 rolls up from the actual lines.
    cluster_plan: Mapped[float] = mapped_column(Numeric, nullable=True)

    collected_by_combiner: Mapped[float] = mapped_column(Numeric, nullable=True)

    # ── Establishing Date ────────────────────────────────────────────────────────
    establishing_date: Mapped[date] = mapped_column(Date, nullable=True)
    establishing_date_ec: Mapped[str] = mapped_column(String, nullable=True)

    # ── Reference & Commodity ──────────────────────────────────────────────────
    reference: Mapped[str] = mapped_column(String, nullable=True)
    primary_commodity: Mapped[str] = mapped_column(String, nullable=True)
    secondary_commodity: Mapped[str] = mapped_column(String, nullable=True)

    # ── FPC Type & Leadership ──────────────────────────────────────────────────
    fpc_type: Mapped[str] = mapped_column(String, nullable=True)
    leader: Mapped[str] = mapped_column(String, nullable=True)
    co_leader: Mapped[str] = mapped_column(String, nullable=True)
    coordinator: Mapped[str] = mapped_column(String, nullable=True)
    secretary: Mapped[str] = mapped_column(String, nullable=True)

    # ── Survey Personnel ────────────────────────────────────────────────────────
    da_name: Mapped[str] = mapped_column(String, nullable=True)
    da_mobile_number: Mapped[str] = mapped_column(String, nullable=True)
    supervisor_name: Mapped[str] = mapped_column(String, nullable=True)
    supervisor_mobile_number: Mapped[str] = mapped_column(String, nullable=True)

    latitude: Mapped[str] = mapped_column(String, nullable=True)
    longitude: Mapped[str] = mapped_column(String, nullable=True)
    altitude: Mapped[str] = mapped_column(String, nullable=True)


# All Register classes should have the prefix G2PRegister
class G2PRegisterCluster(G2PRegister, G2PCluster, G2PGeo):
    __tablename__ = "g2p_register_clusters"
    __table_args__ = {"extend_existing": True}

    latitude: Mapped[str] = mapped_column(String, nullable=True)
    longitude: Mapped[str] = mapped_column(String, nullable=True)
    altitude: Mapped[str] = mapped_column(String, nullable=True)

    def get_search_text_fields(self) -> str:
        """Return cluster information fields used to build search_text."""
        return G2PRegisterDomainServiceCluster().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return cluster information record_name from domain service implementation."""
        return G2PRegisterDomainServiceCluster().construct_record_name(self.to_dict())


# All Register History classes should have the prefix G2PRegisterHistory
class G2PRegisterHistoryCluster(G2PRegisterHistory, G2PCluster, G2PGeoHistory):
    __tablename__ = "g2p_register_history_clusters"
    __table_args__ = {"extend_existing": True}

    latitude: Mapped[str] = mapped_column(String, nullable=True)
    longitude: Mapped[str] = mapped_column(String, nullable=True)
    altitude: Mapped[str] = mapped_column(String, nullable=True)


# All Intake Form classes should have the prefix G2PIntakeForm
class G2PIntakeFormCluster(G2PIntakeForm, G2PRegister, G2PCluster, G2PGeo):
    __tablename__ = "g2p_intake_form_clusters"
    __table_args__ = {"extend_existing": True}

    latitude: Mapped[str] = mapped_column(String, nullable=True)
    longitude: Mapped[str] = mapped_column(String, nullable=True)
    altitude: Mapped[str] = mapped_column(String, nullable=True)

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
        """Return cluster information fields used to build search_text."""
        return G2PRegisterDomainServiceCluster().construct_search_text(self.to_dict())

    def get_record_name_fields(self) -> str:
        """Return cluster information record_name from domain service implementation."""
        return G2PRegisterDomainServiceCluster().construct_record_name(self.to_dict())

# def generate_cluster_id(mapper, connection, target):
#     if not getattr(target, 'cluster_id', None):
#         current_year = datetime.date.today().year
#         prefix = f"CL/{current_year}/"
# 
#         table = target.__table__
#         stmt = select(func.max(table.c.cluster_id)).where(table.c.cluster_id.like(f"{prefix}%"))
# 
#         result = connection.execute(stmt).scalar()
#         if result:
#             try:
#                 last_seq = int(result.split("/")[-1])
#                 new_seq = last_seq + 1
#             except ValueError:
#                 new_seq = 1
#         else:
#             new_seq = 1
# 
#         target.cluster_id = f"{prefix}{new_seq:05d}"
# 
# event.listen(G2PRegisterCluster, 'before_insert', generate_cluster_id)
# event.listen(G2PIntakeFormCluster, 'before_insert', generate_cluster_id)

