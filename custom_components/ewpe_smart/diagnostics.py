"""Diagnostics support for EWPE Smart."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_KEY, CONF_MAC
from .coordinator import EwpeConfigEntry

TO_REDACT = {CONF_KEY, CONF_MAC, "unique_id"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EwpeConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    device = coordinator.device
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "device": {
            "protocol_version": device.version,
            "info": device.info,
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": repr(coordinator.last_exception)
            if coordinator.last_exception
            else None,
            "update_interval": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
        },
        "status": coordinator.data,
    }
