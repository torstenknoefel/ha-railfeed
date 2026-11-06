"""Tests for the pure-Python board parser (no Home Assistant needed)."""
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

_path = Path(__file__).parent.parent / "custom_components" / "railfeed" / "board.py"
_spec = importlib.util.spec_from_file_location("railfeed_board", _path)
board = importlib.util.module_from_spec(_spec)
sys.modules["railfeed_board"] = board
_spec.loader.exec_module(board)

_cpath = _path.parent / "const.py"
_cspec = importlib.util.spec_from_file_location("railfeed_const", _cpath)
const = importlib.util.module_from_spec(_cspec)
sys.modules["railfeed_const"] = const
_cspec.loader.exec_module(const)

TZ = ZoneInfo("Europe/London")
NOW = datetime(2026, 11, 6, 17, 50, tzinfo=timezone.utc)  # 17:50 UK (GMT)

RAW = {
    "station": "LEEDS",
    "date": "2026-11-06",
    "services": [
        {"uid": "A1", "headcode": "1D20", "toc_type": "PASSENGER", "toc_name": "LNER",
         "destination": "LONDON KINGS CROSS", "destination_crs": "KGX", "origin": "LEEDS",
         "public_departure": "17:55:00", "scheduled_departure": "17:54:30", "platform": "3",
         "live_platform": "6", "live_platform_confirmed": True,
         "projected_departure": "18:03:00", "projected_delay_mins": 8,
         "late_reason": "Delayed by a signalling fault", "status": "expected",
         "formation": {"total_coaches": 9}},
        {"uid": "A2", "headcode": "1P05", "toc_type": "PASSENGER", "toc_name": "Northern",
         "destination": "YORK", "destination_crs": "YRK", "public_departure": "18:00:00",
         "platform": "8", "status": "cancelled", "cancel_type": "EN ROUTE",
         "cancel_reason": "A train fault"},
        {"uid": "F1", "headcode": "6E11", "toc_type": "FREIGHT", "destination": "DRAX",
         "scheduled_departure": "18:01:00", "status": "expected"},
        {"uid": "E1", "headcode": "5Z88", "toc_type": "PASSENGER", "destination": "NEVILLE HILL",
         "scheduled_departure": "18:05:00", "status": "expected"},
        {"uid": "P1", "headcode": "1A00", "toc_type": "PASSENGER", "destination": "X",
         "public_departure": "17:45:00", "status": "passed"},
        {"uid": "A3", "headcode": "1S33", "toc_type": "PASSENGER", "toc_name": "LNER",
         "destination": "EDINBURGH", "destination_crs": "EDB", "public_departure": "18:10:00",
         "platform": "4", "live_platform": "4", "live_platform_suppressed": True,
         "delay_mins": 0, "status": "expected"},
        {"uid": "A4", "headcode": "1K10", "toc_type": "PASSENGER",
         "destination": "LONDON KINGS CROSS", "destination_crs": "KGX",
         "public_departure": "23:58:00", "projected_departure": "00:03:00",
         "projected_delay_mins": 5, "platform": "2", "status": "expected"},
        {"uid": "A5", "headcode": "1K11", "toc_type": "PASSENGER",
         "destination": "LONDON KINGS CROSS", "destination_crs": "KGX",
         "public_departure": "00:20:00", "platform": "2", "status": "expected"},
    ],
}


def parse(**kw):
    args = dict(tz=TZ, now=NOW, max_departures=10, passenger_only=True,
                destinations=frozenset())
    args.update(kw)
    return board.parse_board(RAW, **args)


def test_filters_freight_stock_and_departed():
    assert [s.uid for s in parse().services] == ["A1", "A2", "A3", "A4", "A5"]


def test_station_name_tidied():
    assert parse().station == "Leeds"
    assert parse().services[0].destination == "London Kings Cross"


def test_delayed_service_uses_projection_and_platform_change():
    s = parse().services[0]
    assert s.status == "delayed" and s.delay_minutes == 8
    assert s.expected.strftime("%H:%M") == "18:03"
    assert s.platform == "6" and s.platform_changed
    assert s.late_reason and s.coaches == 9


def test_cancelled_and_next_service():
    data = parse()
    assert data.services[1].status == "cancelled"
    assert data.services[1].cancel_reason == "A train fault"
    assert data.next_service.uid == "A1"
    assert (data.delayed_count, data.cancelled_count) == (2, 1)


def test_suppressed_platform_hidden():
    assert parse().services[2].platform is None


def test_midnight_rollover_of_expected_time():
    s = parse().services[3]
    assert s.scheduled.day == 6 and s.expected.day == 7
    assert s.expected.strftime("%H:%M") == "00:03"
    assert parse().services[4].scheduled.day == 7


def test_options_passenger_destination_limit():
    assert [s.uid for s in parse(passenger_only=False, destinations=frozenset({"KGX"})).services] \
        == ["A1", "A4", "A5"]
    assert len(parse(max_departures=2).services) == 2


SERVICES_RAW = {
    "services": [
        # calls at the destination
        {"uid": "A1", "from_is_pass": False, "to_is_pass": False,
         "to_public_arrival": "19:21:00", "to_arrival": "19:20:30", "journey_mins": 78},
        # passes the destination without stopping
        {"uid": "A3", "from_is_pass": False, "to_is_pass": True,
         "to_public_arrival": None, "to_arrival": None, "journey_mins": 60},
        # operational stop only: not advertised to the public
        {"uid": "A4", "from_is_pass": False, "to_is_pass": False,
         "to_public_arrival": None, "to_arrival": "01:10:00", "journey_mins": 70},
        {"uid": "A5", "from_is_pass": False, "to_is_pass": False,
         "to_public_arrival": "01:25:00", "journey_mins": 65},
        # not on the board at all
        {"uid": "ZZ9", "from_is_pass": False, "to_is_pass": False,
         "to_public_arrival": "18:30:00", "journey_mins": 30},
    ]
}


def test_parse_calling_services_only_real_calls():
    calling = board.parse_calling_services(SERVICES_RAW)
    assert set(calling) == {"A1", "A5", "ZZ9"}
    assert calling["A1"].arrival == "19:21" and calling["A1"].journey_mins == 78


def test_calling_filter_keeps_only_trains_serving_station():
    calling = board.parse_calling_services(SERVICES_RAW)
    data = parse(calling=calling, calling_at="YRK")
    assert [s.uid for s in data.services] == ["A1", "A5"]
    assert data.calling_at == "YRK"
    first = data.services[0]
    assert first.calling_at_arrival == "19:21" and first.journey_minutes == 78
    assert first.as_dict()["calling_at_arrival"] == "19:21"


def test_calling_filter_serves_non_final_destination():
    # A1's final destination is King's Cross; the filter is about the route, so a
    # station other than KGX still matches as long as the train calls there.
    calling = {"A2": board.CallingInfo("18:40", 40)}
    data = parse(calling=calling)
    assert [s.uid for s in data.services] == ["A2"]  # cancelled trains still listed


def test_empty_calling_set_lists_nothing_but_none_means_no_filter():
    assert parse(calling={}).services == []
    assert len(parse(calling=None).services) == 5


def test_calling_filter_combines_with_max_departures():
    calling = board.parse_calling_services(SERVICES_RAW)
    assert len(parse(calling=calling, max_departures=1).services) == 1


def test_service_dates_around_midnight():
    from datetime import date
    base = date(2026, 11, 6)
    assert board.service_dates(base, NOW, TZ, 2) == [base]
    # 17:50 + 7h crosses midnight, so tomorrow's schedules matter too
    assert board.service_dates(base, NOW, TZ, 7) == [base, date(2026, 11, 7)]
    # just after midnight the board still holds yesterday's late trains
    early = datetime(2026, 11, 6, 0, 30, tzinfo=timezone.utc)
    assert board.service_dates(base, early, TZ, 2) == [date(2026, 11, 5), base]


def test_entry_key_allows_same_station_with_different_destinations():
    # Without a destination the key is the bare CRS, exactly as before, so setups
    # created in earlier versions keep their entity and device ids.
    assert const.entry_key("LDS") == const.entry_key("LDS", None) == const.entry_key("LDS", "") == "LDS"
    keys = {const.entry_key("LDS"), const.entry_key("LDS", "YRK"), const.entry_key("LDS", "MAN")}
    assert len(keys) == 3
    assert const.entry_key("LDS", "YRK") != const.entry_key("YRK", "LDS")
