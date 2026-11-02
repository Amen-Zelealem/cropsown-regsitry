import logging

from openg2p_registry_core.services import G2PRegisterDomainService

from .domain_compute_utils import compute_cluster_area, compute_season_parts

from .domain_validation_utils import as_float, as_int, validation_error, field_label

_logger = logging.getLogger("g2p-register-domain-service")


class G2PRegisterDomainServiceCultivationCluster(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict], session=None, **kwargs):
        from .field_rules import validate_record_fields
        await validate_record_fields(records, table=True)
        from .domain_validation_utils import is_record_deleted
        active_records = [r for r in records if not is_record_deleted(r)]
        for record in active_records:

            from .domain_validation_utils import validate_alphabetical_name, validate_mobile_number
            validate_alphabetical_name(record.get("farmer_name"), "Farmer name")
            validate_alphabetical_name(record.get("da_name"), "Development agent name")
            validate_alphabetical_name(record.get("supervisor_name"), "Supervisor name")
            validate_mobile_number(record.get("da_mobile_number"), "Development agent mobile number")
            validate_mobile_number(record.get("supervisor_mobile_number"), "Supervisor mobile number")
            from .domain_validation_utils import resolve_production_season
            prod_season = await resolve_production_season(record, session)
            if prod_season and not record.get("production_season"):
                record["production_season"] = prod_season

            season = record.get("season")
            if prod_season and season:
                p_clean = str(prod_season).replace("CROP_SEASON_", "").strip().upper()
                s_clean = str(season).replace("CROP_SEASON_", "").strip().upper()
                if p_clean != s_clean:
                    validation_error(
                        f"Season '{season}' in Cultivation cluster details does not match the Production season '{prod_season}' specified in Farmer identity."
                    )


            from .domain_compute_utils import compute_cluster_area, compute_season_parts, compute_ec_date
            compute_ec_date(record, "establishing_date", "establishing_date_ec")

            compute_season_parts(record)
            compute_cluster_area(record)
            self._validate_cluster_area(record)
            self._validate_smallholders(record)
            self._validate_collected_land(record)
            self._validate_cluster_plan(record)
            self._validate_collected_by_combiner(record)
            if session:
                await self._validate_land_id_matches_planning(record, session=session)
        self._validate_no_duplicate_cluster(active_records)
        # Cross-section (on Next): Cultivation Cluster date >= matching Planning date.
        from .domain_validation_utils import run_previous_section_validation
        from .cropsown_intake_validation_service import validate_cultivation_cluster_against_planning
        await run_previous_section_validation(validate_cultivation_cluster_against_planning, active_records, session)

    def _validate_no_duplicate_cluster(self, records: list[dict]) -> None:
        seen: set[tuple[str, str, str]] = set()
        for record in records:
            cluster_name = str(
                record.get("cluster_name")
                or record.get("cluster_id")
                or record.get("primary_commodity")
                or record.get("commodity")
                or ""
            ).strip()
            season = str(record.get("season") or record.get("production_season") or "").strip()
            land_id = str(record.get("land_id") or "").strip()
            if not cluster_name and not land_id:
                continue
            key = (cluster_name, season, land_id)
            if key in seen:
                validation_error(
                    "Duplicate cluster entries for the same season and land are not allowed"
                )
            seen.add(key)

    _validate_no_duplicate_commodity_season = _validate_no_duplicate_cluster

    def _validate_cluster_area(self, record: dict) -> None:
        area = as_float(record.get("cluster_area_hectare"))
        if area is not None and area < 0:
            validation_error("Total cultivated area must not be negative")

    def _validate_smallholders(self, record: dict) -> None:
        for field in ("number_of_smallholders",):
            value = as_int(record.get(field))
            if value is not None and value < 0:
                validation_error(f"{field_label(field)} must not be negative")

    def _validate_collected_land(self, record: dict) -> None:
        area = as_float(record.get("cluster_area_hectare"))
        collected = as_float(record.get("collected_land"))
        if area is not None and collected is not None and collected > area:
            validation_error("Collected land must not be more than the total cultivated area")

    def _validate_cluster_plan(self, record: dict) -> None:
        timad = as_float(record.get("cluster_area_timad"))
        area = as_float(record.get("cluster_area_hectare"))
        plan = as_float(record.get("cluster_plan"))
        if area is not None and plan is not None and plan > area:
            validation_error(f"Actual planned area ({plan} hectares) must not be more than the total cultivated area ({area} hectares, calculated from {timad} timad)")

    def _validate_collected_by_combiner(self, record: dict) -> None:
        plan = as_float(record.get("cluster_plan"))
        combiner = as_float(record.get("collected_by_combiner"))
        if plan is not None and combiner is not None and combiner > plan:
            validation_error(f"Actual area collected by combine harvester ({combiner} hectares) must not be more than the actual planned area ({plan} hectares)")

    async def _validate_land_id_matches_planning(self, record: dict, session) -> None:
        cluster_land_id = record.get("land_id")
        if not cluster_land_id or not str(cluster_land_id).strip():
            return

        submission_id = record.get("submission_id")
        link_internal_record_id = record.get("link_internal_record_id")

        if not submission_id and not link_internal_record_id:
            return

        from sqlalchemy import text

        cultivation_land_ids = set()
        total_cultivated_area = 0.0
        max_land_area = 0.0

        # 1. Fetch Land IDs saved in intake form cultivations for this submission
        if submission_id:
            res = await session.execute(
                text("SELECT land_id, land_area, actual_crop_area FROM g2p_intake_form_cultivations WHERE submission_id = :sub_id"),
                {"sub_id": submission_id}
            )
            for row in res.fetchall():
                l_id = str(row[0]).strip() if row[0] else ""
                if l_id:
                    cultivation_land_ids.add(l_id)
                    if l_id == str(cluster_land_id).strip():
                        if len(row) > 1 and row[1] is not None:
                            max_land_area = max(max_land_area, as_float(row[1]) or 0.0)
                        if len(row) > 2 and row[2] is not None:
                            total_cultivated_area += (as_float(row[2]) or 0.0)

        # 2. Fetch Land IDs from active registered cultivation records (if existing record)
        if link_internal_record_id:
            res = await session.execute(
                text("SELECT land_id, land_area, actual_crop_area FROM g2p_register_cultivations WHERE link_internal_record_id = :link_id AND record_status = 'ACTIVE'"),
                {"link_id": link_internal_record_id}
            )
            for row in res.fetchall():
                l_id = str(row[0]).strip() if row[0] else ""
                if l_id:
                    cultivation_land_ids.add(l_id)
                    if l_id == str(cluster_land_id).strip():
                        if len(row) > 1 and row[1] is not None:
                            max_land_area = max(max_land_area, as_float(row[1]) or 0.0)
                        if len(row) > 2 and row[2] is not None:
                            total_cultivated_area += (as_float(row[2]) or 0.0)

        # 3. Validate match (if cultivation records exist)
        if cultivation_land_ids and str(cluster_land_id).strip() not in cultivation_land_ids:
            validation_error(
                f"Land ID '{cluster_land_id}' in Cultivation cluster does not match any Land ID specified in Cultivation / land preparation details."
            )

        # If max_land_area was not provided in cultivation, fall back to land_area on cluster record
        if max_land_area == 0.0:
            max_land_area = as_float(record.get("land_area")) or 0.0

        # Calculate remaining available land area for cluster (Option A)
        remaining_land = max(0.0, max_land_area - total_cultivated_area) if max_land_area > 0 else 0.0

        # 4. Validate Cultivation Cluster Area / Plan does not exceed remaining land area
        cluster_area = as_float(record.get("cluster_area_hectare")) or as_float(record.get("cluster_plan"))
        if cluster_area is not None and max_land_area > 0:
            if cluster_area > remaining_land + 1e-6:
                if total_cultivated_area > 0:
                    validation_error(
                        f"Cultivation cluster area ({cluster_area:g} hectares) for Land ID '{cluster_land_id}' exceeds the remaining available land area ({remaining_land:g} hectares). "
                        f"Total land area is {max_land_area:g} hectares and {total_cultivated_area:g} hectares is already cultivated."
                    )
                else:
                    validation_error(
                        f"Cultivation cluster area ({cluster_area:g} hectares) for Land ID '{cluster_land_id}' exceeds Total land area ({max_land_area:g} hectares)."
                    )

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for cluster")

        keys = [
            "functional_record_id",
            "cluster_name",
            "reference",
            "primary_commodity",
            "secondary_commodity",
            "fpc_type",
            "leader",
            "co_leader",
            "coordinator",
            "secretary",
            "agro_ecological_zone",
            "season",
            "cluster_area_hectare",
            "water_source",
            "water_source_method",
            "water_source_frequency",
            "latitude",
            "longitude",
            "region",
            "zone",
            "woreda",
            "kebele",
            "sub_kebele",
            "address_line_1",
            "address_line_2",
            "country_code",
            "da_name",
            "da_mobile_number",
            "supervisor_name",
            "supervisor_mobile_number",
        ]
        search_text = []
        if extra:
            search_text.extend(str(item).strip() for item in extra if str(item).strip())
        search_text.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(search_text).strip()

    def construct_record_name(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing record name for cluster")

        keys = ["cluster_name", "season"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip()
