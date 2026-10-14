"""Derived values, ported from the Odoo registry's computed fields.

Gen1 declares these with `compute=... store=True`, so Odoo recalculates them on
every write. There is no compute framework here, so each domain service calls
the matching helper from `validate_domain_attributes`, which runs on the records
being written — the same moment Odoo would recompute — and writes the result
back into the record dict.

Every formula below is a direct port; the comments name the Odoo method it came
from so the two can be diffed later.

Units follow Gen1: quantities are in quintal, areas in hectare, seed and
fertilizer in kg. A quintal is 100 kg, which is where the ×100 comes from.
"""

from .domain_validation_utils import as_float, as_int

QUINTAL_TO_KG = 100.0
TIMAD_TO_HECTARE = 0.25


def _ratio(numerator, denominator) -> float:
    """Gen1 returns 0.0 rather than dividing by zero."""
    n, d = as_float(numerator), as_float(denominator)
    if not d:
        return 0.0
    return (n or 0.0) / d


def compute_production_results(record: dict) -> None:
    """Odoo: `_compute_production_results` on g2p.crop.production."""
    qty_harvested = as_float(record.get("qty_harvested")) or 0.0
    total_yield_kg = qty_harvested * QUINTAL_TO_KG

    # Yield (kg/ha) = qty harvested (kg) / area harvested
    record["yield_per_ha"] = round(_ratio(total_yield_kg, record.get("area_harvested")), 4)

    # Yield performance % = actual yield / expected yield * 100
    record["yield_performance_pct"] = round(
        _ratio(record.get("actual_yield"), record.get("expected_yield")) * 100, 4
    )

    # Land utilization = area harvested / planned area
    record["land_utilization_rate"] = round(
        _ratio(record.get("area_harvested"), record.get("planned_area")), 4
    )

    # Seed productivity = total yield (kg) / seed used (kg)
    record["seed_productivity"] = round(_ratio(total_yield_kg, record.get("actual_seed_qty")), 4)

    # Fertilizer efficiency = total yield (kg) / fertilizer applied (kg)
    record["fertilizer_efficiency"] = round(
        _ratio(total_yield_kg, record.get("actual_fertilizer_qty")), 4
    )


def compute_harvest_yield(record: dict) -> None:
    """The harvest register carries the same yield_per_ha as production."""
    qty = as_float(record.get("qty_harvested")) or 0.0
    record["yield_per_ha"] = round(_ratio(qty * QUINTAL_TO_KG, record.get("area_harvested")), 4)


def compute_cluster_area(record: dict) -> None:
    """Odoo: `_compute_cluster_area_hectare` — 1 timad is a quarter hectare."""
    timad = as_float(record.get("cluster_area_timad"))
    if timad is not None:
        record["cluster_area_hectare"] = round(timad * TIMAD_TO_HECTARE, 4)


def compute_season_parts(record: dict) -> None:
    """Odoo: `_compute_start_date` / `_compute_end_date`.

    The month/day pair is stored beside the date so a planted date can be tested
    against the season window without caring which year it falls in.
    """
    from .domain_validation_utils import parse_date

    for prefix in ("start", "end"):
        value = parse_date(record.get(f"{prefix}_gc"))
        if value is not None:
            record[f"{prefix}_month"] = value.month
            record[f"{prefix}_day"] = value.day


def is_date_in_season(test_date, start_month, start_day, end_month, end_day) -> bool:
    """Odoo: module-level `is_date_in_season` in annual_crop.py.

    A season may wrap the year end (e.g. Nov -> Feb), so the wrapped case is
    tested as "after the start OR before the end" rather than a plain range.
    Missing bounds mean "no window defined", which Gen1 treats as valid.
    """
    if test_date is None:
        return True
    sm, sd = as_int(start_month), as_int(start_day)
    em, ed = as_int(end_month), as_int(end_day)
    if None in (sm, sd, em, ed) or 0 in (sm, sd, em, ed):
        return True

    tm, td = test_date.month, test_date.day
    if (sm, sd) <= (em, ed):
        return (sm, sd) <= (tm, td) <= (em, ed)
    return (tm, td) >= (sm, sd) or (tm, td) <= (em, ed)


def compute_ec_date(record: dict | object, gc_field: str, ec_field: str) -> None:
    """Computes the Ethiopian Calendar (EC) date from the Gregorian Calendar (GC) date."""
    from .calendar_utils import to_ethiopian
    from .domain_validation_utils import parse_date
    import logging

    _logger = logging.getLogger("g2p-register-domain-service")
    if isinstance(record, dict):
        gc_val = record.get(gc_field)
    else:
        gc_val = getattr(record, gc_field, None)
    
    # Only calculate if GC date exists
    if gc_val:
        gc_date = parse_date(gc_val)
        if gc_date is not None:
            try:
                eth_tuple = to_ethiopian(gc_date.year, gc_date.month, gc_date.day)
                ec_val = f"{eth_tuple[2]:04d}-{eth_tuple[1]:02d}-{eth_tuple[0]:02d}"
                if isinstance(record, dict):
                    record[ec_field] = ec_val
                else:
                    setattr(record, ec_field, ec_val)
            except Exception as e:
                _logger.warning(f"Could not convert GC date {gc_date} to EC for field {ec_field}: {e}")
