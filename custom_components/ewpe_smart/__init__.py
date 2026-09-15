"""EWPE Smart integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .const import (
    CONF_HOST,
    CONF_KEY,
    CONF_MAC,
    CONF_NAME,
    CONF_PORT,
    CONF_UPDATE_INTERVAL,
    CONF_VERSION,
    DEFAULT_PORT,
    DEFAULT_UPDATE_INTERVAL,
    PLATFORMS,
    PROTO_V1,
)
from .coordinator import EwpeConfigEntry, EwpeCoordinator
from .device import EwpeDevice, EwpeError

_LOGGER = logging.getLogger(__name__)

INFO_TIMEOUT = 2.0


async def async_setup_entry(hass: HomeAssistant, entry: EwpeConfigEntry) -> bool:
    """Set up an EWPE Smart device from a config entry."""
    data = entry.data
    device = EwpeDevice(
        host=data[CONF_HOST],
        port=data.get(CONF_PORT, DEFAULT_PORT),
        mac=data[CONF_MAC],
        name=data.get(CONF_NAME) or data[CONF_MAC],
        key=data[CONF_KEY].encode("utf-8"),
        version=data.get(CONF_VERSION, PROTO_V1),
    )

    update_interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    coordinator = EwpeCoordinator(hass, entry, device, update_interval)
    await coordinator.async_config_entry_first_refresh()

    # Model and firmware only show up in the scan reply and aren't stored
    # in the entry, so fetch them here. Not worth failing setup over.
    try:
        await device.fetch_info(timeout=INFO_TIMEOUT)
    except EwpeError as err:
        _LOGGER.debug("Could not read model info from %s: %s", device.host, err)

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EwpeConfigEntry) -> bool:
    """Unload an EWPE Smart config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass: HomeAssistant, entry: EwpeConfigEntry) -> None:
    """Reload the entry when the user changes options (e.g. polling interval)."""
    await hass.config_entries.async_reload(entry.entry_id)
