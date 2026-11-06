"""DataUpdateCoordinator for RailFeed."""
from __future__ import annotations

from datetime import timedelta
import logging
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import RailFeedAuthError, RailFeedClient, RailFeedError
from .board import BoardData, parse_board
from .const import (
    CONF_DESTINATIONS,
    CONF_HOURS,
    CONF_MAX_DEPARTURES,
    CONF_PASSENGER_ONLY,
    CONF_STATION,
    DEFAULT_HOURS,
    DEFAULT_MAX_DEPARTURES,
    DEFAULT_PASSENGER_ONLY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type RailFeedConfigEntry = ConfigEntry[RailFeedCoordinator]


def parse_crs_list(value: str | None) -> frozenset[str] | None:
    """Parse 'LDS, YRK' into {'LDS','YRK'}. Returns None if any token is invalid."""
    if not value or not value.strip():
        return frozenset()
    tokens = [t.strip().upper() for t in value.replace(";", ",").split(",") if t.strip()]
    if any(len(t) != 3 or not t.isalpha() for t in tokens):
        return None
    return frozenset(tokens)


class RailFeedCoordinator(DataUpdateCoordinator[BoardData]):
    """Fetches and processes the live departure board."""

    config_entry: RailFeedConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: RailFeedConfigEntry,
        client: RailFeedClient,
        tz: ZoneInfo,
    ) -> None:
        interval = max(
            MIN_SCAN_INTERVAL, int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_STATION]}",
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.tz = tz
        self.crs: str = entry.data[CONF_STATION]

    async def _async_update_data(self) -> BoardData:
        opts = self.config_entry.options
        hours = int(opts.get(CONF_HOURS, DEFAULT_HOURS))
        try:
            raw = await self.client.async_get_live_board(self.crs, hours)
        except RailFeedAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except RailFeedError as err:
            raise UpdateFailed(f"Error fetching RailFeed data: {err}") from err

        return parse_board(
            raw,
            tz=self.tz,
            now=dt_util.utcnow(),
            max_departures=int(opts.get(CONF_MAX_DEPARTURES, DEFAULT_MAX_DEPARTURES)),
            passenger_only=bool(opts.get(CONF_PASSENGER_ONLY, DEFAULT_PASSENGER_ONLY)),
            destinations=parse_crs_list(opts.get(CONF_DESTINATIONS)) or frozenset(),
        )
