"""Entered dates use OpenG2P's native date widget in the Ethiopian calendar.

The calendar is upstream's ("widget-data-format": {"calendar": "ethiopic"},
registry-widgets 1.1.9-dev.17, platform 1.2 branch); no OAN widget replaces
the date input. The metadata sets it on every editable date.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQL = Path(__file__).resolve().parents[1] / "src/openg2p_registry_cropsown_extension/meta_data/zz-oan/98_ethiopian_dates.sql"


def test_staff_ui_is_built_on_a_platform_with_the_calendar():
    assert json.loads((ROOT / "ui/staff-ui/deps.json").read_text())["ref"] in {"29d2a2397ef9fa09308561e15ae9aa444a4fcd7c"}


def test_no_overlay_replaces_the_date_widget():
    overrides = ROOT / "ui/staff-ui/overrides/src"
    assert not (overrides / "features/activity").exists()
    for path in overrides.rglob("*.ts*"):
        text = path.read_text(encoding="utf-8")
        assert "register({ widget: 'date'" not in text, path
        assert "EthiopianDateInput" not in text, path


def test_metadata_sets_the_native_calendar_and_checks_it():
    text = SQL.read_text(encoding="utf-8")
    assert "'{\"calendar\": \"ethiopic\"}'::jsonb" in text
    assert "Staff-entered dates not on the native Ethiopian calendar" in text


def test_metadata_runs_after_every_other_overlay():
    later = [p.name for p in SQL.parent.glob("*.sql") if p.name > SQL.name]
    assert later == []
