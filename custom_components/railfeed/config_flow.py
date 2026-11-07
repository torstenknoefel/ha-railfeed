"""Config flow for RailFeed."""
from __future__ import annotations

from collections.abc import Mapping
import re
from time import monotonic
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import (
    RailFeedAuthError,
    RailFeedClient,
    RailFeedConnectionError,
    RailFeedError,
    RailFeedNotFoundError,
    RailFeedRateLimitError,
)
from .board import _tidy
from .const import (
    CONF_CALLING_AT,
    CONF_DESTINATIONS,
    CONF_HOURS,
    CONF_MAX_DEPARTURES,
    CONF_PASSENGER_ONLY,
    CONF_STATION,
    CONF_VIA,
    DEFAULT_HOURS,
    DEFAULT_MAX_DEPARTURES,
    DEFAULT_PASSENGER_ONLY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_VIA,
    MIN_SCAN_INTERVAL,
    STATIONS_CACHE_SECONDS,
    entry_key,
)
from .coordinator import entry_calling_at, parse_crs, parse_crs_list
from .stations import Station, parse_stations, resolve_station, split_codes

CRS_RE = re.compile(r"^[A-Za-z]{3}$")


class InvalidCallingAtError(RailFeedError):
    """RailFeed doesn't know the 'calling at' station."""


async def _async_get_stations(hass: HomeAssistant, api_key: str) -> list[Station]:
    """All passenger stations for the pickers, cached for a day.

    Raises RailFeedError if the lookup fails (including a rejected key). An empty
    list means the answer wasn't understood; the forms then fall back to plain text.
    """
    store = hass.data.setdefault(f"{DOMAIN}_stations", {})
    cached = store.get("stations")
    if cached and monotonic() - cached[0] < STATIONS_CACHE_SECONDS:
        return cached[1]
    client = RailFeedClient(async_get_clientsession(hass), api_key)
    stations = parse_stations(await client.async_get_stations())
    if stations:
        store["stations"] = (monotonic(), stations)
    return stations


def _picker(stations: list[Station], *, multiple: bool = False):
    """A dropdown that filters as you type, or plain text when no list is available.

    Typing narrows the list by station name or code. Anything typed that isn't in
    the list is still accepted, so a three-letter code always works.
    """
    if not stations:
        return str
    return SelectSelector(
        SelectSelectorConfig(
            options=[SelectOptionDict(value=s.crs, label=s.label) for s in stations],
            multiple=multiple,
            custom_value=True,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _suggest(value: Any, stations: list[Station]) -> Any:
    """Current comma-separated codes, in the shape the field shows them."""
    return split_codes(value) if stations else (value or "")


def _resolve_codes(value: Any, stations: list[Station]) -> str:
    """Comma-separated CRS codes from a picker (list) or text field, names resolved."""
    if isinstance(value, str):
        items = value.replace(";", ",").split(",")
    else:
        items = list(value or [])
    return ", ".join(r for r in (resolve_station(i, stations) for i in items) if r)


async def _validate(
    hass: HomeAssistant, api_key: str, crs: str, calling_at: str | None = None
) -> str:
    """Check the key and stations work; return a title for the setup."""
    client = RailFeedClient(async_get_clientsession(hass), api_key)
    board = await client.async_get_live_board(crs, hours=1)
    station = _tidy(board.get("station")) or crs
    if not calling_at:
        return station
    try:
        services = await client.async_get_services(crs, calling_at)
    except RailFeedNotFoundError as err:
        raise InvalidCallingAtError(str(err)) from err
    return f"{station} to {_tidy(services.get('to')) or calling_at}"


def _error_key(err: RailFeedError) -> str:
    if isinstance(err, InvalidCallingAtError):
        return "invalid_calling_at"
    if isinstance(err, RailFeedAuthError):
        return "invalid_auth"
    if isinstance(err, RailFeedNotFoundError):
        return "invalid_station"
    if isinstance(err, RailFeedRateLimitError):
        return "rate_limited"
    if isinstance(err, RailFeedConnectionError):
        return "cannot_connect"
    return "unknown"


class RailFeedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RailFeed."""

    VERSION = 1

    def __init__(self) -> None:
        self._api_key: str = ""
        self._stations: list[Station] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: the API key. The station list is fetched with it, which checks the key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            try:
                self._stations = await _async_get_stations(self.hass, api_key)
            except (
                RailFeedAuthError,
                RailFeedRateLimitError,
                RailFeedConnectionError,
            ) as err:
                errors["base"] = _error_key(err)
            except RailFeedError:
                # The station list is a convenience: without it the next page takes
                # plain codes, and the key is checked there.
                self._stations = []
                self._api_key = api_key
                return await self.async_step_station()
            else:
                self._api_key = api_key
                return await self.async_step_station()

        schema = vol.Schema({vol.Required(CONF_API_KEY): str})
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: pick the station (and optionally one it must call at) by name."""
        errors: dict[str, str] = {}
        if user_input is not None:
            crs = resolve_station(user_input.get(CONF_STATION), self._stations).upper()
            calling_at = parse_crs(
                resolve_station(user_input.get(CONF_CALLING_AT), self._stations)
            )

            if not CRS_RE.match(crs):
                errors[CONF_STATION] = "invalid_station"
            elif calling_at is None or calling_at == crs:
                errors[CONF_CALLING_AT] = "invalid_calling_at"
            else:
                # One setup per station *and* destination, so the same station can
                # be added again for a different 'calling at' station.
                await self.async_set_unique_id(entry_key(crs, calling_at))
                self._abort_if_unique_id_configured()
                try:
                    title = await _validate(self.hass, self._api_key, crs, calling_at)
                except InvalidCallingAtError:
                    errors[CONF_CALLING_AT] = "invalid_calling_at"
                except RailFeedError as err:
                    errors["base"] = _error_key(err)
                else:
                    return self.async_create_entry(
                        title=title,
                        data={
                            CONF_API_KEY: self._api_key,
                            CONF_STATION: crs,
                            CONF_CALLING_AT: calling_at,
                        },
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_STATION): _picker(self._stations),
                vol.Optional(CONF_CALLING_AT): _picker(self._stations),
            }
        )
        return self.async_show_form(
            step_id="station",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            try:
                await _validate(self.hass, api_key, entry.data[CONF_STATION])
            except RailFeedError as err:
                errors["base"] = _error_key(err)
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: api_key}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            description_placeholders={"station": entry.title},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> RailFeedOptionsFlow:
        return RailFeedOptionsFlow()


class RailFeedOptionsFlow(OptionsFlow):
    """Options: polling interval, board size, filters, route labels."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        # Setups made before the destination became part of a setup's identity keep
        # their 'calling at' station in the options; newer ones fix it at creation.
        legacy = CONF_CALLING_AT not in self.config_entry.data
        station = self.config_entry.data[CONF_STATION]
        try:
            stations = await _async_get_stations(
                self.hass, self.config_entry.data[CONF_API_KEY]
            )
        except RailFeedError:
            stations = []  # fall back to typing CRS codes
        if user_input is not None:
            destinations = parse_crs_list(
                _resolve_codes(user_input.get(CONF_DESTINATIONS), stations)
            )
            via = parse_crs_list(_resolve_codes(user_input.get(CONF_VIA), stations))
            if legacy:
                calling_at = parse_crs(
                    resolve_station(user_input.get(CONF_CALLING_AT), stations)
                )
            else:
                calling_at = entry_calling_at(self.config_entry) or ""
            if destinations is None:
                errors[CONF_DESTINATIONS] = "invalid_destinations"
            elif calling_at is None or calling_at == station:
                errors[CONF_CALLING_AT] = "invalid_calling_at"
            elif (
                via is None
                or len(via) > MAX_VIA
                or station in via
                or (calling_at and calling_at in via)
            ):
                errors[CONF_VIA] = "invalid_via"
            else:
                if legacy and calling_at:
                    errors.update(
                        await self._check_station(
                            station, calling_at, CONF_CALLING_AT, "invalid_calling_at"
                        )
                    )
                for via_crs in sorted(via):
                    if errors:
                        break
                    errors.update(
                        await self._check_station(
                            station, via_crs, CONF_VIA, "invalid_via"
                        )
                    )
                if not errors:
                    data = {
                        **user_input,
                        CONF_DESTINATIONS: ", ".join(sorted(destinations)),
                        CONF_VIA: ", ".join(sorted(via)),
                    }
                    if legacy:
                        data[CONF_CALLING_AT] = calling_at
                    return self.async_create_entry(data=data)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=3600)),
                vol.Required(
                    CONF_MAX_DEPARTURES,
                    default=opts.get(CONF_MAX_DEPARTURES, DEFAULT_MAX_DEPARTURES),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=25)),
                vol.Required(
                    CONF_HOURS, default=opts.get(CONF_HOURS, DEFAULT_HOURS)
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=24)),
                vol.Required(
                    CONF_PASSENGER_ONLY,
                    default=opts.get(CONF_PASSENGER_ONLY, DEFAULT_PASSENGER_ONLY),
                ): bool,
                **(
                    {
                        vol.Optional(
                            CONF_CALLING_AT,
                            description={
                                "suggested_value": opts.get(CONF_CALLING_AT, "")
                            },
                        ): _picker(stations)
                    }
                    if legacy
                    else {}
                ),
                vol.Optional(
                    CONF_VIA,
                    description={"suggested_value": _suggest(opts.get(CONF_VIA), stations)},
                ): _picker(stations, multiple=True),
                vol.Optional(
                    CONF_DESTINATIONS,
                    description={
                        "suggested_value": _suggest(opts.get(CONF_DESTINATIONS), stations)
                    },
                ): _picker(stations, multiple=True),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    async def _check_station(
        self, station: str, target: str, field: str, error_key: str
    ) -> dict[str, str]:
        """Make sure RailFeed knows ``target``; return form errors, if any."""
        client = RailFeedClient(
            async_get_clientsession(self.hass), self.config_entry.data[CONF_API_KEY]
        )
        try:
            await client.async_get_services(station, target)
        except RailFeedNotFoundError:
            return {field: error_key}
        except RailFeedError as err:
            return {"base": _error_key(err)}
        return {}
