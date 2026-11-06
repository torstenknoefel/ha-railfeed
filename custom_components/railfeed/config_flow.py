"""Config flow for RailFeed."""
from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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
    DEFAULT_HOURS,
    DEFAULT_MAX_DEPARTURES,
    DEFAULT_PASSENGER_ONLY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .coordinator import parse_crs, parse_crs_list

CRS_RE = re.compile(r"^[A-Za-z]{3}$")


async def _validate(hass: HomeAssistant, api_key: str, crs: str) -> str:
    """Check the key and station work; return the station's display name."""
    client = RailFeedClient(async_get_clientsession(hass), api_key)
    board = await client.async_get_live_board(crs, hours=1)
    return _tidy(board.get("station")) or crs


def _error_key(err: RailFeedError) -> str:
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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            crs = user_input[CONF_STATION].strip().upper()

            if not CRS_RE.match(crs):
                errors[CONF_STATION] = "invalid_station"
            else:
                await self.async_set_unique_id(crs)
                self._abort_if_unique_id_configured()
                try:
                    title = await _validate(self.hass, api_key, crs)
                except RailFeedError as err:
                    errors["base"] = _error_key(err)
                else:
                    return self.async_create_entry(
                        title=title,
                        data={CONF_API_KEY: api_key, CONF_STATION: crs},
                    )

        schema = vol.Schema(
            {vol.Required(CONF_API_KEY): str, vol.Required(CONF_STATION): str}
        )
        return self.async_show_form(
            step_id="user",
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
    """Options: polling interval, board size, filters."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            destinations = parse_crs_list(user_input.get(CONF_DESTINATIONS))
            calling_at = parse_crs(user_input.get(CONF_CALLING_AT))
            station = self.config_entry.data[CONF_STATION]
            if destinations is None:
                errors[CONF_DESTINATIONS] = "invalid_destinations"
            elif calling_at is None or calling_at == station:
                errors[CONF_CALLING_AT] = "invalid_calling_at"
            else:
                if calling_at:
                    errors.update(await self._check_calling_at(station, calling_at))
                if not errors:
                    return self.async_create_entry(
                        data={
                            **user_input,
                            CONF_DESTINATIONS: ", ".join(sorted(destinations)),
                            CONF_CALLING_AT: calling_at,
                        }
                    )

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
                vol.Optional(
                    CONF_CALLING_AT,
                    description={"suggested_value": opts.get(CONF_CALLING_AT, "")},
                ): str,
                vol.Optional(
                    CONF_DESTINATIONS,
                    description={"suggested_value": opts.get(CONF_DESTINATIONS, "")},
                ): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

    async def _check_calling_at(self, station: str, calling_at: str) -> dict[str, str]:
        """Make sure RailFeed knows the station; return form errors, if any."""
        client = RailFeedClient(
            async_get_clientsession(self.hass), self.config_entry.data[CONF_API_KEY]
        )
        try:
            await client.async_get_services(station, calling_at)
        except RailFeedNotFoundError:
            return {CONF_CALLING_AT: "invalid_calling_at"}
        except RailFeedError as err:
            return {"base": _error_key(err)}
        return {}
