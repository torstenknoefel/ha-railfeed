"""Tests for the station list helpers (pure Python, no Home Assistant needed)."""
import importlib
from pathlib import Path
import sys
import types

# Load the package's pure modules without running its __init__ (which needs Home Assistant).
_dir = Path(__file__).parent.parent / "custom_components" / "railfeed"
_pkg = types.ModuleType("railfeed_pkg")
_pkg.__path__ = [str(_dir)]
sys.modules["railfeed_pkg"] = _pkg
stations_mod = importlib.import_module("railfeed_pkg.stations")

Station = stations_mod.Station
parse_stations = stations_mod.parse_stations
split_codes = stations_mod.split_codes
resolve_station = stations_mod.resolve_station


def test_parse_stations_sorts_dedupes_and_skips_bad_rows():
    raw = {
        "results": [
            {"crs": "LDS", "name": "LEEDS"},
            {"crs": "BVD", "name": "BELVEDERE"},
            {"crs": None, "name": "SOME JUNCTION"},
            {"crs": "ABCD", "name": "TOO LONG"},
            {"crs": "bvd", "name": "BELVEDERE DUPLICATE"},
            {"crs": "XYZ"},
            {"crs": "ABW", "name": "Abbey Wood", "is_passenger_station": True},
            {"crs": "DEP", "name": "DEPOT", "is_passenger_station": False},
            "junk",
        ]
    }
    stations = parse_stations(raw)
    assert [s.crs for s in stations] == ["ABW", "BVD", "LDS"]
    assert stations[1] == Station("BVD", "Belvedere")
    assert stations[1].label == "Belvedere (BVD)"


def test_parse_stations_tidies_capitals_and_accepts_bare_list():
    stations = parse_stations([{"crs": "CST", "name": "LONDON CANNON STREET"}])
    assert stations == [Station("CST", "London Cannon Street")]


def test_parse_stations_tolerates_unexpected_shapes():
    assert parse_stations(None) == []
    assert parse_stations({"results": "nope"}) == []
    assert parse_stations({}) == []


def test_split_codes():
    assert split_codes("gnw, LEW ; ") == ["GNW", "LEW"]
    assert split_codes(["abw", " "]) == ["ABW"]
    assert split_codes(None) == []
    assert split_codes("") == []


def test_resolve_station():
    stations = [Station("BVD", "Belvedere"), Station("ABW", "Abbey Wood")]
    assert resolve_station("bvd", stations) == "BVD"
    assert resolve_station("Belvedere (BVD)", stations) == "BVD"
    assert resolve_station("  abbey wood ", stations) == "ABW"
    assert resolve_station("Nowhere", stations) == "Nowhere"
    assert resolve_station(None, stations) == ""
