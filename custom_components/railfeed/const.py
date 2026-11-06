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

# RailFeed asks clients to poll a live board no more than every 30 seconds.
MIN_SCAN_INTERVAL = 30
DEFAULT_SCAN_INTERVAL = 60
DEFAULT_MAX_DEPARTURES = 10
DEFAULT_HOURS = 2
DEFAULT_PASSENGER_ONLY = True

ATTRIBUTION = "Data provided by RailFeed (railfeed.co.uk), built on Network Rail and Darwin feeds"
