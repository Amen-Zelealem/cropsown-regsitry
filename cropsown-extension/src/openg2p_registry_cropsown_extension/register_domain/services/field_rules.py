"""Field checks shared by registered domain services; no core or worker patch.

Only supplied fields are checked. Required/form/record rules remain with their
native lifecycle. Names and dates normalize before domain calculations.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import date

from ...farmer_reference.profile import (
    FarmerReferenceError,
    normalize_farmer_id,
    normalize_fin,
    normalize_uid,
)

PERSON_NAMES = frozenset(
    {
        "farmer_name",
        "first_name",
        "middle_name",
        "last_name",
        "da_name",
        "surveyor_name",
        "supervisor_name",
    }
    | {
        f"{part}_{lang}"
        for part in ("first_name", "middle_name", "last_name")
        for lang in ("amh", "other")
    }
)
DATE_FIELDS = frozenset(
    [
        "actual_cultivation_date",
        "cluster_harvest_date",
        "date_of_birth",
        "end_gc",
        "establishing_date",
        "harvest_date",
        "observation_date",
        "planned_date",
        "registration_date",
        "sowing_date",
        "start_gc",
    ]
)
PAST_ONLY = frozenset({"date_of_birth", "registration_date"})

# Numeric-value fields. Rule is keyed by field name, so one entry covers every
# section (and both intake and change-request, since clean_records runs in both).
# Measurement / quantity / yield / count fields: numeric only and >= 0.
NON_NEGATIVE_FIELDS = frozenset(
    {
        # planning
        "land_area", "planned_area", "expected_yield", "planned_seed_qty",
        "planned_fertilizer_qty", "growth_duration_days", "planned_labor",
        # cultivation
        "actual_crop_area", "actual_yield", "actual_seed_qty",
        "actual_fertilizer_qty", "actual_growth_duration_days",
        # cultivation cluster / planning cluster
        "cluster_area_timad", "cluster_area_hectare", "cluster_plan",
        "cluster_collected_land", "collected_land", "collected_by_combiner",
        "collected_quintal", "number_of_smallholders",
        # sowing
        "area_sown", "fertilizer_qty", "cluster_area_sown",
        # harvest
        "area_harvested", "qty_harvested", "qty_stored", "qty_sold",
        "cluster_area_harvested", "cluster_qty_harvested", "cluster_qty_stored",
        "cluster_qty_sold",
        # production
        "area_under_production", "yield_per_ha",
    }
)
# Percentages: numeric, 0..100.
PERCENTAGE_FIELDS = frozenset(
    {"post_harvest_loss_pct", "cluster_post_harvest_loss_pct", "estimated_damage_pct"}
)
# Date parts: whole numbers in range.
MONTH_FIELDS = frozenset({"start_month", "end_month"})
DAY_FIELDS = frozenset({"start_day", "end_day"})
# Coordinates: numeric but negatives are valid, so no >= 0.
COORDINATE_FIELDS = frozenset({"latitude", "longitude", "altitude"})
# Ethiopian mobile numbers.
MOBILE_FIELDS = frozenset({"da_mobile_number", "supervisor_mobile_number"})

# A plain decimal / integer only — rejects letters, %, kg, scientific notation,
# thousands separators, inf/nan, and any other special sign.
_DECIMAL_RE = re.compile(r"-?\d+(?:\.\d+)?")
_INTEGER_RE = re.compile(r"-?\d+")
# +251 or 0, then 7/9, then 8 digits (e.g. +251911234567 or 0911234567).
_ETH_MOBILE_RE = re.compile(r"(?:\+251|0)[79]\d{8}")

LABELS = {
    "farmer_id": "Farmer ID",
    "fayda_fin": "Fayda FIN",
    "fayda_fan_id": "Fayda FAN ID",
    "fayda_id": "Fayda ID (FAN or FIN)",
    "da_name": "Development agent name",
    "surveyor_name": "Development agent name",
    "supervisor_name": "Supervisor name",
    "date_of_birth": "Date of birth",
    "first_name_amh": "First name (Amharic)",
    "middle_name_amh": "Middle name (Amharic)",
    "last_name_amh": "Last name (Amharic)",
    "first_name_other": "First name (other language)",
    "middle_name_other": "Middle name (other language)",
    "last_name_other": "Last name (other language)",
    "da_mobile_number": "Development agent mobile number",
    "supervisor_mobile_number": "Supervisor mobile number",
}
MESSAGES = {
    "coss_field_name_format": "{label}: use 1 to 100 letters, spaces, hyphens or apostrophes. Do not use digits or other symbols.",
    "coss_field_amharic_name_format": "{label}: use 1 to 100 Ethiopic letters, spaces, hyphens or apostrophes. Do not use digits or other symbols.",
    "coss_field_farmer_id_format": "{label}: enter FR- followed by exactly 12 digits, preserving leading zeroes.",
    "coss_field_fin_format": "{label}: enter exactly 12 digits. Use the Fayda FAN ID field for a 16-digit number.",
    "coss_field_fan_format": "{label}: enter exactly 16 digits, optionally separated by spaces. Use the Fayda FIN field for a 12-digit number.",
    "coss_field_date_format": "{label}: enter a real date. In imported files, write dates as year-month-day in the Gregorian calendar, for example 2018-12-25.",
    "coss_field_date_min": "{label}: the date is too early. Enter a date in 1900 or later.",
    "coss_field_date_future": "{label}: the date is in the future. Enter today's date or an earlier date.",
    "coss_field_farmer_id_required": "{label}: enter the farmer's Farmer Registry ID (FR- followed by 12 digits).",
    "coss_field_fayda_one_of": "Fayda ID: enter the 16-digit FAN or the 12-digit FIN.",
    "coss_field_fayda_id_format": "{label}: enter the 16-digit FAN or the 12-digit FIN, digits only.",
    "coss_field_numeric": "{label}: enter a number only — no letters, spaces or other symbols.",
    "coss_field_non_negative": "{label}: enter a number that is 0 or greater. Negative values are not allowed.",
    "coss_field_percentage": "{label}: enter a number between 0 and 100.",
    "coss_field_month": "{label}: enter a whole number from 1 to 12.",
    "coss_field_day": "{label}: enter a whole number from 1 to 31.",
    "coss_field_mobile": "{label}: enter a valid Ethiopian mobile number (e.g. +251911234567 or 0911234567).",
}


@dataclass(frozen=True)
class Issue:
    field: str
    key: str
    row: int | None = None


def explain(issue, messages=None):
    messages = messages or {}
    label = (
        messages.get(issue.field)
        or LABELS.get(issue.field)
        or re.sub(r"\bid\b", "ID", issue.field.replace("_", " ").capitalize())
    )
    if issue.row is not None:
        row_label = messages.get("coss_field_row_label", "{label} (row {row})")
        label = row_label.replace("{label}", label).replace("{row}", str(issue.row))
    template = messages.get(issue.key) or MESSAGES[issue.key]
    return template.replace("{label}", label)


def name_issue(value, field):
    if not isinstance(value, str):
        return Issue(field, "coss_field_name_format")
    cleaned = unicodedata.normalize("NFC", value.strip())
    amharic = field.endswith("_amh")
    key = "coss_field_amharic_name_format" if amharic else "coss_field_name_format"

    def letter(char):
        return unicodedata.category(char).startswith(("L", "M")) and (
            not amharic or 0x1200 <= ord(char) <= 0x137F
        )

    if (
        not 1 <= len(cleaned) <= 100
        or not any(char.isalpha() for char in cleaned)
        or any(not letter(char) and char not in " '-’" for char in cleaned)
    ):
        return Issue(field, key)
    return None


def clean_records(records):
    from .domain_validation_utils import parse_date

    problems = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        if record.get("edit_action") == "DELETE":
            continue
        problems.extend(split_fayda_id(record))
        for key, value in list(record.items()):
            field = key.rsplit(".", 1)[-1] if isinstance(key, str) else None
            if value is None or isinstance(value, str) and not value.strip():
                continue
            if field in PERSON_NAMES:
                problem = name_issue(value, field)
                if problem:
                    problems.append(problem)
                else:
                    record[key] = value.strip()
            elif field in {"farmer_id", "fayda_fin", "fayda_fan_id"}:
                normalizer, error_key = {
                    "farmer_id": (normalize_farmer_id, "coss_field_farmer_id_format"),
                    "fayda_fin": (normalize_fin, "coss_field_fin_format"),
                    "fayda_fan_id": (normalize_uid, "coss_field_fan_format"),
                }[field]
                try:
                    record[key] = normalizer(value)
                except FarmerReferenceError:
                    problems.append(Issue(field, error_key))
            elif field in DATE_FIELDS:
                parsed = (
                    date.today()
                    if field == "registration_date" and value == "today"
                    else parse_date(value)
                )
                if parsed is None:
                    problems.append(Issue(field, "coss_field_date_format"))
                elif parsed < date(1900, 1, 1):
                    problems.append(Issue(field, "coss_field_date_min"))
                elif field in PAST_ONLY and parsed > date.today():
                    problems.append(Issue(field, "coss_field_date_future"))
                else:
                    record[key] = parsed.isoformat()
            elif field in COORDINATE_FIELDS:
                if not _DECIMAL_RE.fullmatch(str(value).strip()):
                    problems.append(Issue(field, "coss_field_numeric"))
            elif field in MONTH_FIELDS:
                token = str(value).strip()
                if not _INTEGER_RE.fullmatch(token) or not 1 <= int(token) <= 12:
                    problems.append(Issue(field, "coss_field_month"))
            elif field in DAY_FIELDS:
                token = str(value).strip()
                if not _INTEGER_RE.fullmatch(token) or not 1 <= int(token) <= 31:
                    problems.append(Issue(field, "coss_field_day"))
            elif field in PERCENTAGE_FIELDS:
                token = str(value).strip()
                if not _DECIMAL_RE.fullmatch(token):
                    problems.append(Issue(field, "coss_field_numeric"))
                elif not 0 <= float(token) <= 100:
                    problems.append(Issue(field, "coss_field_percentage"))
            elif field in NON_NEGATIVE_FIELDS:
                token = str(value).strip()
                if not _DECIMAL_RE.fullmatch(token):
                    problems.append(Issue(field, "coss_field_numeric"))
                elif float(token) < 0:
                    problems.append(Issue(field, "coss_field_non_negative"))
            elif field in MOBILE_FIELDS:
                if not _ETH_MOBILE_RE.fullmatch(str(value).strip()):
                    problems.append(Issue(field, "coss_field_mobile"))
        problems.extend(identity_issues(record))
    return problems


def split_fayda_id(record):
    """Store the one typed Fayda ID of the Farmer lookup section as FAN or FIN.

    The section asks for a single Fayda ID. Sixteen digits are a FAN and twelve
    digits are a FIN; the value is stored in the existing fayda_fan_id or
    fayda_fin field and the other one is cleared, so the Farmer reference lookup,
    dedup and stored data keep their two separate fields.
    """
    issues = []
    for key in [k for k in record if isinstance(k, str) and k.rsplit(".", 1)[-1] == "fayda_id"]:
        value = record.pop(key)
        prefix = key[: -len("fayda_id")]
        if value is None or isinstance(value, str) and not value.strip():
            farmer_id = next((v for k, v in record.items() if isinstance(k, str) and k.rsplit(".", 1)[-1] == "farmer_id"), "")
            if not (farmer_id.strip() if isinstance(farmer_id, str) else farmer_id):
                issues.append(Issue("farmer_id", "coss_field_farmer_id_required"))
            issues.append(Issue("fayda_id", "coss_field_fayda_one_of"))
            continue
        digits = "".join(value.split()) if isinstance(value, str) else ""
        if digits.isascii() and digits.isdigit() and len(digits) in (12, 16):
            record[prefix + "fayda_fan_id"] = digits if len(digits) == 16 else None
            record[prefix + "fayda_fin"] = digits if len(digits) == 12 else None
        else:
            issues.append(Issue("fayda_id", "coss_field_fayda_id_format"))
    return issues


def identity_issues(record):
    """A farmer is identified by its Farmer ID and one Fayda ID (FIN or FAN).

    Checked only on records that carry the identity fields (the intake's
    Farmer Identity section), so other sections and child rows are untouched.
    """
    def value(field):
        for key, item in record.items():
            if isinstance(key, str) and key.rsplit(".", 1)[-1] == field:
                return item.strip() if isinstance(item, str) else item
        return None

    fields = {key.rsplit(".", 1)[-1] for key in record if isinstance(key, str)}
    if not {"farmer_id", "fayda_fin", "fayda_fan_id"} <= fields:
        return []
    issues = []
    if not value("farmer_id"):
        issues.append(Issue("farmer_id", "coss_field_farmer_id_required"))
    if not value("fayda_fin") and not value("fayda_fan_id"):
        issues.append(Issue("fayda_fin", "coss_field_fayda_one_of"))
    return issues


async def _translations():
    """Use registry language metadata; English remains available in pure probes."""
    from openg2p_fastapi_common.context import dbengine, get_async_session_maker
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError

    try:
        if dbengine.get() is None:
            return {}
        async with get_async_session_maker()() as session:
            value = (
                await session.execute(
                    text(
                        "SELECT domain_translation FROM registry_languages WHERE is_default LIMIT 1"
                    )
                )
            ).scalar_one_or_none()
        if isinstance(value, str):
            import json

            value = json.loads(value)
        return value if isinstance(value, dict) else {}
    except (LookupError, RuntimeError, SQLAlchemyError, OSError, ValueError):
        logging.getLogger(__name__).warning(
            "Registry field translations unavailable; using explained English defaults"
        )
        return {}


async def validate_record_fields(records, *, table=False):
    problems = [
        replace(problem, row=index if table else None)
        for index, record in enumerate(records or [], 1)
        for problem in clean_records([record])
    ]
    if problems:
        from .domain_validation_utils import validation_error

        messages = await _translations()
        validation_error("; ".join(explain(problem, messages) for problem in problems))
