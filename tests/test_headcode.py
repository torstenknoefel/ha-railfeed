"""The passenger-only filter must keep real passenger trains whose headcode starts with 9."""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

_path = Path(__file__).parent.parent / "custom_components" / "railfeed" / "board.py"
_spec = importlib.util.spec_from_file_location("railfeed_board_headcode", _path)
board = importlib.util.module_from_spec(_spec)
sys.modules["railfeed_board_headcode"] = board
_spec.loader.exec_module(board)

TZ = ZoneInfo("Europe/London")
NOW = datetime(2026, 11, 6, 17, 50, tzinfo=timezone.utc)


def _item(uid, headcode, toc_type="PASSENGER"):
    return {
        "uid": uid, "headcode": headcode, "toc_type": toc_type,
        "destination": "BEDFORD", "destination_crs": "BDM",
        "public_departure": "18:00:00", "status": "expected",
    }


def _uids(headcodes, passenger_only=True):
    raw = {
        "station": "LONDON BLACKFRIARS",
        "date": "2026-11-06",
        "services": [_item(f"U{i}", hc) for i, hc in enumerate(headcodes)],
    }
    data = board.parse_board(
        raw, tz=TZ, now=NOW, max_departures=20, passenger_only=passenger_only,
        destinations=frozenset(),
    )
    return {s.uid for s in data.services}


def test_thameslink_style_9_headcodes_are_kept():
    assert _uids(["9A12", "1S33", "2C04"]) == {"U0", "U1", "U2"}


def test_non_passenger_classes_are_dropped():
    # light engine, parcels, freight, empty stock, departmental
    assert _uids(["0Z00", "3Q10", "4M20", "5Z88", "6E11", "7A01", "8X00"]) == set()


def test_everything_is_kept_when_passenger_only_is_off():
    assert _uids(["6E11", "9A12"], passenger_only=False) == {"U0", "U1"}
