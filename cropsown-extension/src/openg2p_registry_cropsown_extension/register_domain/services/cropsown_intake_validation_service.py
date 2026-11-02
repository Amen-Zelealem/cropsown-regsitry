import logging
import re
from datetime import date, datetime
from sqlalchemy import text, select
from openg2p_registry_core.errors import G2PRegistryErrorCodes, G2PRegistryException
from openg2p_registry_core.models import RegisterPurposeEnum

_logger = logging.getLogger("cropsown-intake-validation")


def validation_error(message: str) -> None:
    raise G2PRegistryException(
        code=G2PRegistryErrorCodes.REQUEST_VALIDATION_ERROR.value[1],
        message=message,
    )


def clean_season(season_val: str | None) -> str:
    if not season_val:
        return ""
    return str(season_val).replace("CROP_SEASON_", "").strip().upper()


def clean_commodity(comm_val: str | None) -> str:
    if not comm_val:
        return ""
    return str(comm_val).replace("CROP_COMMODITY_", "").strip().upper()


def commodity_matches(comm1: str | None, comm2: str | None) -> bool:
    if not comm1 or not comm2:
        return False
    c1 = clean_commodity(comm1)
    c2 = clean_commodity(comm2)
    if c1 == c2:
        return True
    # In case one is a name and other is code, or prefix variants
    c1_raw = str(comm1).strip().upper()
    c2_raw = str(comm2).strip().upper()
    return c1_raw == c2_raw


def season_matches(season1: str | None, season2: str | None) -> bool:
    if not season1 or not season2:
        return True
    s1 = clean_season(season1)
    s2 = clean_season(season2)
    return s1 == s2


def parse_date_flexible(val) -> date | None:
    if not val:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()

    val_str = str(val).strip()
    if not val_str:
        return None

    # Handle ISO formats
    if "T" in val_str:
        val_str = val_str.split("T")[0]

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(val_str, fmt).date()
        except ValueError:
            pass

    match_slash = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", val_str)
    if match_slash:
        try:
            return date(int(match_slash.group(3)), int(match_slash.group(2)), int(match_slash.group(1)))
        except ValueError:
            pass

    match_dash = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", val_str)
    if match_dash:
        try:
            return date(int(match_dash.group(1)), int(match_dash.group(2)), int(match_dash.group(3)))
        except ValueError:
            pass

    return None


def is_record_deleted(record: dict) -> bool:
    if not isinstance(record, dict):
        return False
    if record.get("_delete") or record.get("is_deleted") or record.get("_deleted") or record.get("deleted"):
        return True
    edit_action = str(record.get("edit_action") or "").strip().upper()
    if edit_action in ("DELETE", "REMOVE", "DELETED", "REMOVED"):
        return True
    action = str(record.get("_action") or record.get("action") or "").strip().upper()
    if action in ("DELETE", "REMOVE", "DELETED", "REMOVED"):
        return True
    status = str(record.get("record_status") or record.get("status") or record.get("_status") or "").strip().upper()
    if status in ("DELETED", "REMOVED", "DELETE", "REMOVE"):
        return True
    return False


def is_clustered_row(row: dict) -> bool:
    cs = row.get("cluster_status")
    if isinstance(cs, (list, tuple, set)):
        items = []
        for x in cs:
            if isinstance(x, dict):
                items.append(str(x.get("value") or x.get("label") or ""))
            else:
                items.append(str(x))
        cs_str = " ".join(items).upper()
    elif isinstance(cs, dict):
        cs_str = str(cs.get("value") or cs.get("label") or "").upper()
    else:
        cs_str = str(cs or "").upper()

    if "INDEPENDENT" in cs_str or "NON_CLUSTER" in cs_str or "NON-CLUSTER" in cs_str:
        return False
    if "CLUSTERED" in cs_str or "CLUSTER_STATUS_CLUSTERED" in cs_str or cs_str == "CLUSTER":
        return True
    if "CLUSTER" in cs_str:
        return True
    if row.get("cluster_name") and not row.get("commodity") and not row.get("crop_type_affected"):
        return True
    return False


async def get_form_type(form_id: str | None, session) -> str:
    """
    Returns 'planning', 'cultivation', 'sowing', 'harvesting', or 'other'.
    """
    if not form_id:
        return "other"
    if form_id == "5bf0068c-ce19-46f8-874c-7147997f793b":
        return "planning"
    if form_id == "6be15ab9-0f1b-4c38-995f-395d52a1b17a":
        return "cultivation"
    if form_id == "4a7c2c98-0ffb-41d8-8fea-f22349823675":
        return "sowing"
    if form_id == "52150a37-153d-496d-9cd9-2a3815d6e13b":
        return "harvesting"

    try:
        res = await session.execute(
            text("SELECT form_mnemonic FROM g2p_intake_form_definitions WHERE form_id = :fid"),
            {"fid": form_id}
        )
        row = res.fetchone()
        if row and row[0]:
            mnemonic = str(row[0]).lower()
            if "planning" in mnemonic:
                return "planning"
            if "cultivation" in mnemonic:
                return "cultivation"
            if "sowing" in mnemonic:
                return "sowing"
            if "harvest" in mnemonic:
                return "harvesting"
    except Exception as e:
        _logger.warning("Error checking form type: %s", e)
    return "other"


async def get_master_records_for_submission(session, submission_id: str | None) -> tuple[list[str], str, str, str]:
    """
    Returns (matched_master_ids, fayda_id, crop_year, prod_season).
    """
    if not submission_id:
        return [], "", "", ""

    res_hdr = await session.execute(
        text("SELECT fayda_fan_id, crop_year, production_season, farmer_id FROM g2p_intake_form_crop_sowns WHERE submission_id = :sid AND fayda_fan_id IS NOT NULL LIMIT 1"),
        {"sid": submission_id}
    )
    hdr_row = res_hdr.fetchone()
    if not hdr_row or not hdr_row[0]:
        return [], "", "", ""

    fayda = str(hdr_row[0]).strip()
    fayda_nospaces = fayda.replace(" ", "")
    crop_year = str(hdr_row[1] or "").strip()
    prod_season = str(hdr_row[2] or "").strip()
    farmer_id = str(hdr_row[3] or "").strip()
    season_clean = clean_season(prod_season)

    # Parent key = 4 values (Farmer ID + Fayda ID + Crop Year + Production Season).
    # A record is the same parent only when ALL four match; any one mismatch means
    # a different parent (so a new one may be created downstream).
    query_master = text("""
        SELECT internal_record_id, crop_year, production_season, farmer_id
        FROM g2p_register_crop_sowns
        WHERE (TRIM(fayda_fan_id) = :fayda OR REPLACE(fayda_fan_id, ' ', '') = :fayda_nospaces)
          AND record_status = 'ACTIVE'
    """)
    res_m = await session.execute(query_master, {"fayda": fayda, "fayda_nospaces": fayda_nospaces})
    master_rows = res_m.fetchall()

    matched_master_ids = []
    for r_id, r_year, r_season, r_farmer in master_rows:
        farmer_matches = not farmer_id or str(r_farmer or "").strip() == farmer_id
        year_matches = not crop_year or str(r_year or "").strip() == crop_year
        season_matches = not season_clean or clean_season(r_season) == season_clean
        if farmer_matches and year_matches and season_matches:
            matched_master_ids.append(str(r_id))

    return matched_master_ids, fayda, crop_year, prod_season


_FARMER_ID_PATTERN = re.compile(r"^FR-[0-9]{12}$")


def validate_farmer_identity_required_fields(section_id: str, section_payload: list[dict]):
    if section_id not in (
        "cropsown_intake_record_section_01",
        "cropsown_common_intake_record_section_01",
        "cropsown_cropsown_record_section_01",
    ):
        return

    from .domain_validation_utils import get_row_field, validate_alphabetical_name, as_int

    active_rows = [r for r in (section_payload or []) if isinstance(r, dict) and not is_record_deleted(r)]
    is_common_intake = (section_id == "cropsown_common_intake_record_section_01")

    if not active_rows:
        if is_common_intake:
            validation_error("Fayda ID (FAN) is required in Farmer Identity.")
        else:
            validation_error("Farmer ID is required in Farmer Identity.")

    for row in active_rows:
        farmer_id = get_row_field(row, "farmer_id")
        fayda_fan_id = get_row_field(row, "fayda_fan_id") or get_row_field(row, "fayda_id")
        crop_year = get_row_field(row, "crop_year")
        prod_season = get_row_field(row, "production_season") or get_row_field(row, "season")

        # 1. Farmer ID
        if not is_common_intake:
            if not farmer_id:
                validation_error("Farmer ID is required in Farmer Identity.")
            if not _FARMER_ID_PATTERN.match(str(farmer_id).strip()):
                validation_error(f"Farmer ID must be FR- followed by 12 digits (got '{farmer_id}')")

        # 2. Fayda ID (FAN)
        if not fayda_fan_id:
            validation_error("Fayda ID (FAN) is required in Farmer Identity.")
        fyda_pattern = r"^\d{4} \d{4} \d{4} \d{4}$"
        if not re.match(fyda_pattern, str(fayda_fan_id).strip()):
            validation_error(
                "Fayda ID must be 16 digits formatted as 4 groups of 4 digits (e.g. 1234 5678 9000 3456) with no letters, special characters, or extra spaces within groups"
            )

        # 3. Crop Year
        if not crop_year:
            validation_error("Crop Year is required in Farmer Identity.")
        val_str = str(crop_year).strip()
        if not val_str.isdigit():
            validation_error("Crop Year must contain only numeric digits (no letters, spaces, or special characters)")
        year = as_int(crop_year)
        current_year = date.today().year
        if year is not None and year < current_year:
            validation_error("Crop Year must not be in the past")
        if year is not None and year > current_year:
            validation_error("Crop Year must not be in the future")

        # 4. Production Season
        if not prod_season:
            validation_error("Production Season is required in Farmer Identity.")

        # 5. Farmer Name (optional)
        farmer_name = get_row_field(row, "farmer_name")
        if farmer_name:
            validate_alphabetical_name(farmer_name, "Farmer Name")


async def validate_farmer_identity_prerequisite(session, section_payload: list[dict], submission_id: str | None, form_type: str):
    """
    Rule: Sowing and Harvesting are NOT allowed to create a new master Crop Sown record.
    When filling Farmer Identity and clicking 'Next' on Sowing or Harvesting forms,
    check whether there is already an ACTIVE record for this Fayda ID, Crop Year, and Season
    in entire Crop Sown records. If none exists, raise an error preventing the user from proceeding.
    """
    for row in section_payload or []:
        if is_record_deleted(row):
            continue
        fayda = str(row.get("fayda_fan_id") or row.get("fayda_id") or "").strip()
        crop_year = str(row.get("crop_year") or "").strip()
        prod_season = str(row.get("production_season") or "").strip()

        if not fayda:
            continue

        fayda_nospaces = fayda.replace(" ", "")
        season_clean = clean_season(prod_season)

        query = text("""
            SELECT internal_record_id, crop_year, production_season
            FROM g2p_register_crop_sowns
            WHERE (TRIM(fayda_fan_id) = :fayda OR REPLACE(fayda_fan_id, ' ', '') = :fayda_nospaces)
              AND record_status = 'ACTIVE'
        """)
        res = await session.execute(query, {"fayda": fayda, "fayda_nospaces": fayda_nospaces})
        rows = res.fetchall()

        matched = False
        for r_id, r_year, r_season in rows:
            year_matches = not crop_year or str(r_year or "").strip() == crop_year
            season_matches = not season_clean or clean_season(r_season) == season_clean
            if year_matches and season_matches:
                matched = True
                break

        if not matched:
            year_str = f", Crop Year '{crop_year}'" if crop_year else ""
            season_str = f", Production Season '{prod_season}'" if prod_season else ""
            stage_name = form_type.capitalize()
            prereq_msg = (
                "Please ensure a Sowing record exists before creating a Harvesting record."
                if form_type == "harvesting"
                else "Please ensure a Planning / Cultivation record exists before creating a Sowing record."
            )
            validation_error(
                f"No active Crop Sown record found under Fayda ID '{fayda}'{year_str}{season_str}. "
                f"A {stage_name} intake form can only be created for an existing Crop Sown record. "
                f"{prereq_msg}"
            )


async def validate_farmer_identity_season_change(session, section_payload: list[dict], submission_id: str | None):
    if not submission_id or not section_payload:
        return
    for row in section_payload:
        if is_record_deleted(row):
            continue
        new_prod_season = (
            row.get("production_season")
            or row.get("6b06a95a-9a6c-5a33-a33d-c1625716c59c.production_season")
            or row.get("season")
        )
        if not new_prod_season:
            continue
        new_clean = clean_season(new_prod_season)
        if not new_clean:
            continue

        intake_tables = [
            ("g2p_intake_form_plannings", "season", "Crop Planning Details"),
            ("g2p_intake_form_cultivations", "season", "Cultivation Details"),
            ("g2p_intake_form_cultivation_clusters", "season", "Cultivation Cluster Details"),
            ("g2p_intake_form_clusters", "season", "Cluster Information Details"),
            ("g2p_intake_form_sowings", "COALESCE(season, cluster_season)", "Sowing Details"),
            ("g2p_intake_form_productions", "season", "Production Details"),
        ]
        for tbl, col, sec_label in intake_tables:
            res = await session.execute(
                text(f"SELECT {col} FROM {tbl} WHERE submission_id = :sid AND {col} IS NOT NULL LIMIT 1"),
                {"sid": submission_id}
            )
            row_c = res.fetchone()
            if row_c and row_c[0]:
                c_clean = clean_season(row_c[0])
                if c_clean and c_clean != new_clean:
                    validation_error(
                        f"Production Season '{new_prod_season}' does not match Season '{row_c[0]}' in {sec_label} for this submission."
                    )


async def validate_section_season_matches_production_season(session, section_id: str, section_payload: list[dict], submission_id: str | None):
    if not submission_id or not section_payload:
        return
    master_ids, fayda, crop_year, prod_season = await get_master_records_for_submission(session, submission_id)
    if not prod_season and submission_id:
        res = await session.execute(
            text("SELECT production_season FROM g2p_intake_form_crop_sowns WHERE submission_id = :sid AND production_season IS NOT NULL LIMIT 1"),
            {"sid": submission_id}
        )
        row = res.fetchone()
        if row and row[0]:
            prod_season = row[0]

    if not prod_season:
        return

    prod_clean = clean_season(prod_season)
    if not prod_clean:
        return

    section_names = {
        "cropsown_planning_details_section_01": "Crop Planning Details",
        "cropsown_cluster_details_section_01": "Cluster Information Details",
        "cropsown_cultivation_details_section_01": "Cultivation / Land Preparation Details",
        "cropsown_cultivation_cluster_details_section_01": "Cultivation Cluster Details",
        "cropsown_sowing_details_section_01": "Sowing Details",
        "cropsown_harvest_details_section_01": "Harvest Details",
        "cropsown_production_details_section_01": "Production Details",
    }
    sec_name = section_names.get(section_id, "this section")

    for row in section_payload or []:
        if is_record_deleted(row):
            continue
        row_season = row.get("season") or row.get("cluster_season")
        if not row_season:
            for k, v in row.items():
                if isinstance(k, str) and (k.endswith("season") or k.endswith(".season")) and v:
                    row_season = v
                    break
        if row_season:
            r_clean = clean_season(row_season)
            if r_clean and r_clean != prod_clean:
                validation_error(
                    f"Season '{row_season}' in {sec_name} does not match the Production Season '{prod_season}' specified in Farmer Identity."
                )


def extract_row_dict(item):
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if isinstance(item, dict):
        return item
    if hasattr(item, "__dict__"):
        return item.__dict__
    return {}


def extract_season_from_item(item_dict):
    for key in ("season", "cluster_season", "production_season"):
        val = item_dict.get(key)
        if val:
            return str(val)
    for k, v in item_dict.items():
        if isinstance(k, str) and (k.endswith("production_season") or k.endswith("cluster_season") or k.endswith(".season") or k == "season") and v:
            return str(v)
    return None


def extract_year_from_item(item_dict):
    for key in ("crop_year",):
        val = item_dict.get(key)
        if val:
            return str(val)
    for k, v in item_dict.items():
        if isinstance(k, str) and k.endswith("crop_year") and v:
            return str(v)
    return None


async def find_root_crop_sown_record(internal_id, session):
    if not internal_id:
        return None
    res = await session.execute(
        text("SELECT internal_record_id, crop_year, production_season FROM g2p_register_crop_sowns WHERE internal_record_id = :id"),
        {"id": str(internal_id)}
    )
    row = res.fetchone()
    if row:
        return row[0], row[1], row[2]

    child_tables = (
        "g2p_register_plannings",
        "g2p_register_cultivations",
        "g2p_register_cultivation_clusters",
        "g2p_register_clusters",
        "g2p_register_sowings",
        "g2p_register_harvests",
        "g2p_register_productions",
    )
    for tbl in child_tables:
        res_c = await session.execute(
            text(f"SELECT link_internal_record_id FROM {tbl} WHERE internal_record_id = :id AND link_internal_record_id IS NOT NULL LIMIT 1"),
            {"id": str(internal_id)}
        )
        row_c = res_c.fetchone()
        if row_c and row_c[0]:
            res_p = await session.execute(
                text("SELECT internal_record_id, crop_year, production_season FROM g2p_register_crop_sowns WHERE internal_record_id = :pid"),
                {"pid": str(row_c[0])}
            )
            row_p = res_p.fetchone()
            if row_p:
                return row_p[0], row_p[1], row_p[2]

    return None


async def validate_change_request_season_and_year(payload, session):
    internal_id = getattr(payload, "internal_record_id", None)
    section_id = getattr(payload, "section_id", None)
    change_items = getattr(payload, "change_payload", None) or []

    if not internal_id:
        for it in change_items:
            d = extract_row_dict(it)
            internal_id = d.get("link_internal_record_id") or d.get("internal_record_id")
            if internal_id:
                break

    if not internal_id:
        return

    root_data = await find_root_crop_sown_record(internal_id, session)
    if not root_data:
        return

    root_id, existing_year, existing_season = root_data
    if not existing_season:
        return

    clean_existing_season = clean_season(existing_season)

    is_farmer_identity = section_id in (
        "cropsown_cropsown_record_section_01",
        "crop_farmer_lookup",
        "cropsown_common_intake_record_section_01",
        "cropsown_intake_record_section_01",
    )

    section_names = {
        "cropsown_cropsown_record_section_01": "Farmer Identity",
        "crop_farmer_lookup": "Farmer lookup",
        "cropsown_common_intake_record_section_01": "Farmer Identity",
        "cropsown_intake_record_section_01": "Farmer Identity",
        "cropsown_planning_details_section_01": "Crop Planning Details",
        "cropsown_cluster_details_section_01": "Cluster Information Details",
        "cropsown_cultivation_details_section_01": "Cultivation / Land Preparation Details",
        "cropsown_cultivation_cluster_details_section_01": "Cultivation Cluster Details",
        "cropsown_sowing_details_section_01": "Sowing Details",
        "cropsown_harvest_details_section_01": "Harvest Details",
        "cropsown_production_details_section_01": "Production Details",
    }
    sec_name = section_names.get(section_id, "this section")

    for it in change_items:
        d = extract_row_dict(it)
        if is_record_deleted(d):
            continue

        item_season = extract_season_from_item(d)
        if item_season:
            clean_item_season = clean_season(item_season)
            if clean_item_season and clean_item_season != clean_existing_season:
                if is_farmer_identity:
                    validation_error(
                        f"Production Season cannot be changed once established for a Crop Sown record (Existing: '{existing_season}', Attempted: '{item_season}')."
                    )
                else:
                    validation_error(
                        f"Season '{item_season}' in {sec_name} does not match the Production Season '{existing_season}' specified in Farmer Identity."
                    )

        if is_farmer_identity:
            item_year = extract_year_from_item(d)
            if item_year and existing_year and str(item_year).strip() != str(existing_year).strip():
                validation_error(
                    f"Crop Year cannot be changed once established for a Crop Sown record (Existing: '{existing_year}', Attempted: '{item_year}')."
                )


async def validate_cultivation_against_planning(session, section_payload: list[dict], submission_id: str | None):
    """
    Rule 3: In Cultivation Intake Form, if a record is ALREADY available in Planning
    for the Land ID, Crop Name, and Season: check that Cultivation Date >= Planning Date
    (equal or future date is allowed; past date shows error on Next button).
    If it's a new record (no planning record exists for this land/crop/season), any date can be given.
    """
    master_ids, fayda, crop_year, prod_season = await get_master_records_for_submission(session, submission_id)

    # Fetch active planning records under master records and current submission
    plans = []
    if master_ids:
        res_p = await session.execute(
            text("""
                SELECT land_id, commodity, season, planned_date, start_gc
                FROM g2p_register_plannings
                WHERE link_internal_record_id = ANY(:m_ids) AND record_status = 'ACTIVE'
            """),
            {"m_ids": master_ids}
        )
        plans.extend(res_p.fetchall())

    if submission_id:
        res_ip = await session.execute(
            text("""
                SELECT land_id, commodity, season, planned_date, start_gc
                FROM g2p_intake_form_plannings
                WHERE submission_id = :sid
            """),
            {"sid": submission_id}
        )
        plans.extend(res_ip.fetchall())

    for row in section_payload or []:
        if is_record_deleted(row):
            continue

        land_id = str(row.get("land_id") or "").strip()
        commodity = str(row.get("commodity") or "").strip()
        season = str(row.get("season") or prod_season or "").strip()
        cult_date = parse_date_flexible(row.get("actual_cultivation_date") or row.get("start_gc"))

        if not land_id or not cult_date:
            continue

        matching_plan_date = None
        for p_land, p_comm, p_season, p_pdate, p_start in plans:
            if str(p_land or "").strip() == land_id:
                if commodity_matches(commodity, p_comm) and season_matches(season, p_season):
                    p_date_val = parse_date_flexible(p_pdate or p_start)
                    if p_date_val:
                        matching_plan_date = p_date_val
                        break

        # Only validate date if a planning record exists for this land_id, crop name, and season
        if matching_plan_date is not None and cult_date < matching_plan_date:
            validation_error(
                f"Cultivation Date ({cult_date.strftime('%d/%m/%Y')}) cannot be earlier than "
                f"Planned Date ({matching_plan_date.strftime('%d/%m/%Y')}) for Land ID '{land_id}' and Crop '{commodity}'. "
                f"You can only choose a date equal to or after the planned date."
            )


async def validate_cultivation_cluster_against_planning(session, section_payload: list[dict], submission_id: str | None):
    """
    Cluster Cultivation vs Planning date check:
    If a Planning Cluster record exists for this cluster_name and land_id,
    Cultivation Date must be >= Planning Date. If none exists, allow any date.
    """
    master_ids, fayda, crop_year, prod_season = await get_master_records_for_submission(session, submission_id)

    plan_clusters = []
    if master_ids:
        res_c = await session.execute(
            text("""
                SELECT land_id, cluster_name, start_gc, establishing_date
                FROM g2p_register_clusters
                WHERE link_internal_record_id = ANY(:m_ids) AND record_status = 'ACTIVE'
            """),
            {"m_ids": master_ids}
        )
        plan_clusters.extend(res_c.fetchall())

    if submission_id:
        res_ic = await session.execute(
            text("""
                SELECT land_id, cluster_name, start_gc, establishing_date
                FROM g2p_intake_form_clusters
                WHERE submission_id = :sid
            """),
            {"sid": submission_id}
        )
        plan_clusters.extend(res_ic.fetchall())

    for row in section_payload or []:
        if is_record_deleted(row):
            continue

        land_id = str(row.get("land_id") or "").strip()
        cluster_name = str(row.get("cluster_name") or "").strip()
        cult_date = parse_date_flexible(row.get("start_gc") or row.get("establishing_date"))

        if not land_id or not cluster_name or not cult_date:
            continue

        matching_plan_date = None
        for p_land, p_cname, p_start, p_est in plan_clusters:
            if str(p_land or "").strip() == land_id and str(p_cname or "").strip().upper() == cluster_name.upper():
                p_date_val = parse_date_flexible(p_start or p_est)
                if p_date_val:
                    matching_plan_date = p_date_val
                    break

        if matching_plan_date is not None and cult_date < matching_plan_date:
            validation_error(
                f"Cultivation Cluster Date ({cult_date.strftime('%d/%m/%Y')}) cannot be earlier than "
                f"Planning Date ({matching_plan_date.strftime('%d/%m/%Y')}) for Farmers Production Cluster Name '{cluster_name}' and Land ID '{land_id}'."
            )


async def validate_sowing_against_cultivation(session, section_payload: list[dict], submission_id: str | None):
    """
    Rule 2 & 5: In Sowing Intake Form:
    - For Independent: Cross-check against Cultivation using Land ID, Crop Name (commodity), and Season.
    - For Cluster: Cross-check against Cultivation Cluster using FPC Name (cluster_name) and Land ID.
    - Date validation: Sowing Date must be equal to or after Cultivation Date.
    """
    master_ids, fayda, crop_year, prod_season = await get_master_records_for_submission(session, submission_id)

    # Sowing may be submitted WITHOUT a prior record (parent / cultivation). When a
    # matching previous-section record exists we still validate the date; when it does
    # not, we bypass instead of blocking.
    # if not master_ids:
    #     validation_error(
    #         f"No active Crop Sown record found for Fayda ID '{fayda}'. Cannot add sowing details."
    #     )

    # 1. Independent Cultivations
    res_ind = await session.execute(
        text("""
            SELECT land_id, commodity, season, actual_cultivation_date, start_gc
            FROM g2p_register_cultivations
            WHERE link_internal_record_id = ANY(:m_ids) AND record_status = 'ACTIVE'
        """),
        {"m_ids": master_ids}
    )
    cult_ind_rows = list(res_ind.fetchall())

    if submission_id:
        res_iind = await session.execute(
            text("""
                SELECT land_id, commodity, season, actual_cultivation_date, start_gc
                FROM g2p_intake_form_cultivations
                WHERE submission_id = :sid
            """),
            {"sid": submission_id}
        )
        cult_ind_rows.extend(res_iind.fetchall())

    # 2. Clustered Cultivations
    res_cls = await session.execute(
        text("""
            SELECT land_id, cluster_name, start_gc, establishing_date
            FROM g2p_register_cultivation_clusters
            WHERE link_internal_record_id = ANY(:m_ids) AND record_status = 'ACTIVE'
        """),
        {"m_ids": master_ids}
    )
    cult_cls_rows = list(res_cls.fetchall())

    if submission_id:
        res_icls = await session.execute(
            text("""
                SELECT land_id, cluster_name, start_gc, establishing_date
                FROM g2p_intake_form_cultivation_clusters
                WHERE submission_id = :sid
            """),
            {"sid": submission_id}
        )
        cult_cls_rows.extend(res_icls.fetchall())

    for row in section_payload or []:
        if is_record_deleted(row):
            continue

        land_id = str(row.get("land_id") or "").strip()
        if not land_id:
            continue

        sow_date = parse_date_flexible(row.get("sowing_date"))
        is_cluster = is_clustered_row(row)

        if is_cluster:
            cluster_name = str(row.get("cluster_name") or "").strip()
            if not cluster_name:
                validation_error("Farmers Production Cluster Name is required for clustered Sowing.")

            matched_cluster = None
            for c_land, c_cname, c_start, c_est in cult_cls_rows:
                if str(c_land or "").strip() == land_id and str(c_cname or "").strip().upper() == cluster_name.upper():
                    matched_cluster = (c_start, c_est)
                    break

            # Validate date only when a matching Cultivation Cluster exists; otherwise bypass.
            if matched_cluster:
                cult_date = parse_date_flexible(matched_cluster[0] or matched_cluster[1])
                if sow_date and cult_date and sow_date < cult_date:
                    validation_error(
                        f"Sowing Date ({sow_date.strftime('%d/%m/%Y')}) cannot be earlier than "
                        f"Cultivation Cluster Date ({cult_date.strftime('%d/%m/%Y')}) for Farmers Production Cluster Name '{cluster_name}' and Land ID '{land_id}'."
                    )
        else:
            commodity = str(row.get("commodity") or "").strip()
            season = str(row.get("season") or row.get("cluster_season") or prod_season or "").strip()

            land_matched = False
            full_matched_row = None

            for c_land, c_comm, c_season, c_act_date, c_start in cult_ind_rows:
                if str(c_land or "").strip() == land_id:
                    land_matched = True
                    if commodity_matches(commodity, c_comm) and season_matches(season, c_season):
                        full_matched_row = (c_act_date, c_start)
                        break

            # Validate date only when a matching Cultivation exists (Land ID + Crop +
            # Season); otherwise bypass — Sowing may be submitted without a prior record.
            if full_matched_row:
                cult_date = parse_date_flexible(full_matched_row[0] or full_matched_row[1])
                if sow_date and cult_date and sow_date < cult_date:
                    validation_error(
                        f"Sowing Date ({sow_date.strftime('%d/%m/%Y')}) cannot be earlier than "
                        f"Cultivation Date ({cult_date.strftime('%d/%m/%Y')}) for Land ID '{land_id}' and Crop '{commodity}'."
                    )


async def validate_infestation_against_sowing(session, section_payload: list[dict], submission_id: str | None):
    """
    Rule 6: Infestation incident details must check against Sowing.
    - Independent: check Land ID and Crop Name (commodity / crop_type_affected).
    - Cluster: check FPC Name (cluster_name) and Land ID.
    - Date check: Observation Date >= Sowing Date.
    """
    master_ids, fayda, crop_year, prod_season = await get_master_records_for_submission(session, submission_id)

    if not master_ids:
        validation_error(
            f"No active Crop Sown record found for Fayda ID '{fayda}'. Cannot add infestation incident details."
        )

    sowings = []
    if master_ids:
        res_s = await session.execute(
            text("""
                SELECT land_id, commodity, cluster_name, sowing_date, cluster_status
                FROM g2p_register_sowings
                WHERE link_internal_record_id = ANY(:m_ids) AND record_status = 'ACTIVE'
            """),
            {"m_ids": master_ids}
        )
        sowings.extend(res_s.fetchall())

    if submission_id:
        res_is = await session.execute(
            text("""
                SELECT land_id, commodity, cluster_name, sowing_date, cluster_status
                FROM g2p_intake_form_sowings
                WHERE submission_id = :sid
            """),
            {"sid": submission_id}
        )
        sowings.extend(res_is.fetchall())

    for row in section_payload or []:
        if is_record_deleted(row):
            continue

        land_id = str(row.get("land_id") or "").strip()
        if not land_id:
            continue

        obs_date = parse_date_flexible(row.get("observation_date"))
        is_cluster = is_clustered_row(row)

        if is_cluster:
            cluster_name = str(row.get("cluster_name") or "").strip()
            if not cluster_name:
                validation_error("Farmers Production Cluster Name is required for clustered Infestation.")

            cluster_matched = False
            matched_sowing = None
            for s_land, s_comm, s_cname, s_date, s_cstatus in sowings:
                if str(s_land or "").strip() == land_id and str(s_cname or "").strip().upper() == cluster_name.upper():
                    cluster_matched = True
                    matched_sowing = s_date
                    break

            if not cluster_matched:
                validation_error(
                    f"No active Sowing record found for Farmers Production Cluster Name '{cluster_name}' and Land ID '{land_id}' under this Crop Sown record. "
                    f"Infestation incident can only be reported for a sown cluster."
                )

            sow_date = parse_date_flexible(matched_sowing)
            if obs_date and sow_date and obs_date <= sow_date:
                validation_error(
                    f"Infestation Observation Date ({obs_date.strftime('%d/%m/%Y')}) must be after "
                    f"Sowing Date ({sow_date.strftime('%d/%m/%Y')}) for Farmers Production Cluster Name '{cluster_name}' and Land ID '{land_id}'."
                )
        else:
            commodity = str(row.get("commodity") or row.get("crop_type_affected") or "").strip()
            land_matched = False
            sowing_matched = False
            matched_sowing_date = None

            for s_land, s_comm, s_cname, s_date, s_cstatus in sowings:
                if str(s_land or "").strip() == land_id:
                    land_matched = True
                    if commodity_matches(commodity, s_comm):
                        sowing_matched = True
                        matched_sowing_date = s_date
                        break

            if not land_matched:
                validation_error(
                    f"Land ID '{land_id}' in Infestation Incident does not match any Land ID specified in Sowing for this record."
                )

            if not sowing_matched:
                validation_error(
                    f"No active Sowing record found for Land ID '{land_id}' and Crop '{commodity}' under this Crop Sown record. "
                    f"Infestation incident can only be reported for an existing Sowing record."
                )

            sow_date = parse_date_flexible(matched_sowing_date)
            if obs_date and sow_date and obs_date <= sow_date:
                validation_error(
                    f"Infestation Observation Date ({obs_date.strftime('%d/%m/%Y')}) must be after "
                    f"Sowing Date ({sow_date.strftime('%d/%m/%Y')}) for Land ID '{land_id}' and Crop '{commodity}'."
                )


async def validate_harvest_against_sowing(session, section_payload: list[dict], submission_id: str | None):
    """
    Rule 1, 2, 5: Harvest Details validation against Sowing:
    - For Independent: Cross-check against Sowing using Land ID, Crop Name (commodity), and Season.
    - For Cluster: Cross-check against Sowing using FPC Name (cluster_name) and Land ID.
    - Date validation: Harvest Date must be equal to or after Sowing Date.
    """
    master_ids, fayda, crop_year, prod_season = await get_master_records_for_submission(session, submission_id)

    # Harvest may be submitted WITHOUT a prior record (parent / sowing). When a matching
    # Sowing exists we still validate the date; when it does not, we bypass.
    # if not master_ids:
    #     validation_error(
    #         f"No active Crop Sown record found for Fayda ID '{fayda}'. Cannot add harvest details."
    #     )

    sowings = []
    if master_ids:
        res_s = await session.execute(
            text("""
                SELECT land_id, commodity, cluster_name, season, cluster_season, sowing_date, cluster_status
                FROM g2p_register_sowings
                WHERE link_internal_record_id = ANY(:m_ids) AND record_status = 'ACTIVE'
            """),
            {"m_ids": master_ids}
        )
        sowings.extend(res_s.fetchall())

    if submission_id:
        res_is = await session.execute(
            text("""
                SELECT land_id, commodity, cluster_name, season, cluster_season, sowing_date, cluster_status
                FROM g2p_intake_form_sowings
                WHERE submission_id = :sid
            """),
            {"sid": submission_id}
        )
        sowings.extend(res_is.fetchall())

    for row in section_payload or []:
        if is_record_deleted(row):
            continue

        land_id = str(row.get("land_id") or "").strip()
        if not land_id:
            continue

        is_cluster = is_clustered_row(row)

        if is_cluster:
            cluster_name = str(row.get("cluster_name") or "").strip()
            harvest_date = parse_date_flexible(row.get("cluster_harvest_date") or row.get("harvest_date"))

            if not cluster_name:
                validation_error("Farmers Production Cluster Name is required for clustered Harvest.")

            cluster_matched = False
            matched_sowing_date = None
            for s_land, s_comm, s_cname, s_season, s_cseason, s_date, s_cstatus in sowings:
                if str(s_land or "").strip() == land_id and str(s_cname or "").strip().upper() == cluster_name.upper():
                    cluster_matched = True
                    matched_sowing_date = s_date
                    break

            # Validate date only when a matching Sowing cluster exists; otherwise bypass.
            if cluster_matched:
                sow_date = parse_date_flexible(matched_sowing_date)
                if harvest_date and sow_date and harvest_date <= sow_date:
                    validation_error(
                        f"Harvest Date ({harvest_date.strftime('%d/%m/%Y')}) must be after "
                        f"Sowing Date ({sow_date.strftime('%d/%m/%Y')}) for Farmers Production Cluster Name '{cluster_name}' and Land ID '{land_id}'."
                    )
        else:
            commodity = str(row.get("commodity") or "").strip()
            harvest_date = parse_date_flexible(row.get("harvest_date"))
            season = str(row.get("season") or prod_season or "").strip()

            land_matched = False
            sowing_matched = False
            matched_sowing_date = None

            for s_land, s_comm, s_cname, s_season, s_cseason, s_date, s_cstatus in sowings:
                if str(s_land or "").strip() == land_id:
                    land_matched = True
                    s_sn = s_season or s_cseason
                    if commodity_matches(commodity, s_comm) and season_matches(season, s_sn):
                        sowing_matched = True
                        matched_sowing_date = s_date
                        break

            # Validate date only when a matching Sowing exists (Land ID + Crop + Season);
            # otherwise bypass — Harvest may be submitted without a prior Sowing record.
            if sowing_matched:
                sow_date = parse_date_flexible(matched_sowing_date)
                if harvest_date and sow_date and harvest_date <= sow_date:
                    validation_error(
                        f"Harvest Date ({harvest_date.strftime('%d/%m/%Y')}) must be after "
                        f"Sowing Date ({sow_date.strftime('%d/%m/%Y')}) for Land ID '{land_id}' and Crop '{commodity}'."
                    )
