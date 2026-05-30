"""EWPE Smart integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_HOST,
    CONF_KEY,
    CONF_MAC,
    CONF_NAME,
    CONF_PORT,
    CONF_SILENT_COMMANDS,
    CONF_UPDATE_INTERVAL,
    CONF_VERSION,
    DEFAULT_PORT,
    DEFAULT_SILENT_COMMANDS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    PLATFORMS,
    PROTO_V1,
)
from .coordinator import EwpeCoordinator
from .device import EwpeDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an EWPE Smart device from a config entry."""
    data = entry.data
    device = EwpeDevice(
        host=data[CONF_HOST],
        port=data.get(CONF_PORT, DEFAULT_PORT),
        mac=data[CONF_MAC],
        name=data.get(CONF_NAME) or data[CONF_MAC],
        key=data[CONF_KEY].encode("utf-8"),
        version=data.get(CONF_VERSION, PROTO_V1),
        silent_commands=entry.options.get(
            CONF_SILENT_COMMANDS, DEFAULT_SILENT_COMMANDS
        ),
    )

    update_interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    coordinator = EwpeCoordinator(hass, entry, device, update_interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an EWPE Smart config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when the user changes options (e.g. polling interval)."""
    await hass.config_entries.async_reload(entry.entry_id)
