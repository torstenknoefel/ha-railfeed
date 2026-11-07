"""Constants for the RailFeed integration."""
from __future__ import annotations

DOMAIN = "railfeed"

API_BASE = "https://railfeed.co.uk/api"
REQUEST_TIMEOUT = 15

CONF_STATION = "station"
CONF_MAX_DEPARTURES = "max_departures"
CONF_HOURS = "hours"
CONF_DESTINATIONS = "destinations"
CONF_PASSENGER_ONLY = "passenger_only"
CONF_CALLING_AT = "calling_at"
CONF_VIA = "via"

# Each via station costs one cached /api/services lookup per schedule day.
MAX_VIA = 5

# RailFeed asks clients to poll a live board no more than every 30 seconds.
MIN_SCAN_INTERVAL = 30
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_MAX_DEPARTURES = 10
DEFAULT_HOURS = 2
DEFAULT_PASSENGER_ONLY = True

# Which trains call at a station changes only with the timetable, so the
# /api/services lookup is cached (RailFeed itself caches schedules for 15 min).
CALLING_CACHE_SECONDS = 900

# The list of stations behind the station pickers barely ever changes.
STATIONS_CACHE_SECONDS = 86400


def entry_key(crs: str, calling_at: str | None = None) -> str:
    """Identity of one setup: a station, optionally with a 'calling at' station.

    A setup without a destination keeps the bare CRS code, which is what it
    used before destinations were part of the identity, so existing entities
    and devices are unaffected.
    """
    return f"{crs}_{calling_at}" if calling_at else crs


ATTRIBUTION = "Data provided by RailFeed (railfeed.co.uk), built on Network Rail and Darwin feeds"
