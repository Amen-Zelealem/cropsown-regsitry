"""The season window is entered once, as Start and End date on the picker.

Start/End Day and Month are not asked for as number boxes; the server works
them out from the dates on save, and the dates win when both are sent.
"""

from pathlib import Path

import pytest

ZZ_OAN = Path(__file__).resolve().parents[1] / "src/openg2p_registry_cropsown_extension/meta_data/zz-oan"
SQL = ZZ_OAN / "90_season_window_from_dates.sql"


def test_metadata_takes_the_day_and_month_boxes_off_and_checks_it():
    text = SQL.read_text(encoding="utf-8")
    for field in ("start_month", "start_day", "end_month", "end_day"):
        assert f"'{field}'" in text
    assert "RAISE EXCEPTION 'Season day/month number boxes or Gregorian date labels still on the form" in text


def test_metadata_runs_after_the_labels_are_set():
    assert SQL.name > "85_readable_text.sql"
    assert SQL.name < "98_ethiopian_dates.sql"


def test_day_and_month_come_from_the_dates():
    pytest.importorskip("openg2p_registry_core")
    from openg2p_registry_cropsown_extension.register_domain.services.domain_compute_utils import (
        compute_season_parts,
    )

    record = {"start_gc": "2025-09-11", "end_gc": "2026-01-30", "start_month": 3, "start_day": 1}
    compute_season_parts(record)
    assert (record["start_month"], record["start_day"]) == (9, 11)
    assert (record["end_month"], record["end_day"]) == (1, 30)


def test_day_and_month_sent_without_dates_are_kept():
    pytest.importorskip("openg2p_registry_core")
    from openg2p_registry_cropsown_extension.register_domain.services.domain_compute_utils import (
        compute_season_parts,
    )

    record = {"start_month": 9, "start_day": 11, "end_month": 1, "end_day": 30}
    compute_season_parts(record)
    assert record == {"start_month": 9, "start_day": 11, "end_month": 1, "end_day": 30}
