"""The RailFeed integration: live UK departure boards."""
from __future__ import annotations

from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .api import RailFeedClient
from .coordinator import RailFeedConfigEntry, RailFeedCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: RailFeedConfigEntry) -> bool:
    """Set up RailFeed from a config entry."""
    client = RailFeedClient(async_get_clientsession(hass), entry.data[CONF_API_KEY])
    # Times from the API are UK local time, regardless of the HA server's zone.
    tz = await dt_util.async_get_time_zone("Europe/London")

    coordinator = RailFeedCoordinator(hass, entry, client, tz)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RailFeedConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: RailFeedConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
