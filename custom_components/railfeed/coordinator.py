"""DataUpdateCoordinator for RailFeed."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
import time
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import RailFeedAuthError, RailFeedClient, RailFeedError
from .board import (
    BoardData,
    CallingInfo,
    base_date_of,
    parse_board,
    parse_calling_services,
    service_dates,
)
from .const import (
    CALLING_CACHE_SECONDS,
    CONF_CALLING_AT,
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
    entry_key,
)

_LOGGER = logging.getLogger(__name__)

type RailFeedConfigEntry = ConfigEntry[RailFeedCoordinator]


def parse_crs(value: str | None) -> str | None:
    """Return a single normalised CRS code, '' for blank, or None if invalid."""
    if not value or not value.strip():
        return ""
    token = value.strip().upper()
    return token if len(token) == 3 and token.isalpha() else None


def parse_crs_list(value: str | None) -> frozenset[str] | None:
    """Parse 'LDS, YRK' into {'LDS','YRK'}. Returns None if any token is invalid."""
    if not value or not value.strip():
        return frozenset()
    tokens = [t.strip().upper() for t in value.replace(";", ",").split(",") if t.strip()]
    if any(len(t) != 3 or not t.isalpha() for t in tokens):
        return None
    return frozenset(tokens)


def entry_calling_at(entry: ConfigEntry) -> str | None:
    """The 'calling at' station of a setup, or None.

    Chosen when the setup is created (it is part of the setup's identity). Setups
    made before that was possible kept it in their options, so fall back to those.
    """
    if CONF_CALLING_AT in entry.data:
        return parse_crs(entry.data[CONF_CALLING_AT]) or None
    return parse_crs(entry.options.get(CONF_CALLING_AT)) or None


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
            name=f"{DOMAIN} {entry.unique_id or entry.data[CONF_STATION]}",
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.tz = tz
        self.crs: str = entry.data[CONF_STATION]
        self.calling_at: str | None = entry_calling_at(entry)
        self.entry_key: str = entry.unique_id or entry_key(self.crs, self.calling_at)
        # schedule date -> (monotonic fetch time, {uid: CallingInfo})
        self._calling_cache: dict[date, tuple[float, dict[str, CallingInfo]]] = {}

    async def _async_update_data(self) -> BoardData:
        opts = self.config_entry.options
        hours = int(opts.get(CONF_HOURS, DEFAULT_HOURS))
        try:
            raw = await self.client.async_get_live_board(self.crs, hours)
        except RailFeedAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except RailFeedError as err:
            raise UpdateFailed(f"Error fetching RailFeed data: {err}") from err

        now = dt_util.utcnow()
        calling_at = self.calling_at
        calling = None
        if calling_at:
            calling = await self._async_get_calling(raw, now, hours, calling_at)

        return parse_board(
            raw,
            tz=self.tz,
            now=now,
            max_departures=int(opts.get(CONF_MAX_DEPARTURES, DEFAULT_MAX_DEPARTURES)),
            passenger_only=bool(opts.get(CONF_PASSENGER_ONLY, DEFAULT_PASSENGER_ONLY)),
            destinations=parse_crs_list(opts.get(CONF_DESTINATIONS)) or frozenset(),
            calling=calling,
            calling_at=calling_at,
        )

    async def _async_get_calling(
        self, raw: dict, now: datetime, hours: int, calling_at: str
    ) -> dict[str, CallingInfo]:
        """Schedule uids of trains that call at ``calling_at`` after this station."""
        needed = service_dates(base_date_of(raw, now, self.tz), now, self.tz, hours)
        mono = time.monotonic()
        merged: dict[str, CallingInfo] = {}
        for day in needed:
            cached = self._calling_cache.get(day)
            if cached is None or mono - cached[0] > CALLING_CACHE_SECONDS:
                try:
                    services = await self.client.async_get_services(
                        self.crs, calling_at, day.isoformat()
                    )
                except RailFeedAuthError as err:
                    raise ConfigEntryAuthFailed(str(err)) from err
                except RailFeedError as err:
                    if cached is None:
                        raise UpdateFailed(
                            f"Error fetching RailFeed services to {calling_at}: {err}"
                        ) from err
                    _LOGGER.warning("Using cached services to %s: %s", calling_at, err)
                else:
                    cached = (mono, parse_calling_services(services))
                    self._calling_cache[day] = cached
            merged.update(cached[1])
        for day in [d for d in self._calling_cache if d not in needed]:
            del self._calling_cache[day]
        return merged
