"""Polling coordinator for an EWPE Smart device."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_VERSION, DOMAIN, PROTO_V1
from .device import EwpeAuthError, EwpeDevice, EwpeError

_LOGGER = logging.getLogger(__name__)


class EwpeCoordinator(DataUpdateCoordinator[dict[str, int]]):
    """Polls a single EwpeDevice and surfaces failures to HA."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device: EwpeDevice,
        update_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {device.name or device.host}",
            update_interval=timedelta(seconds=update_interval),
            config_entry=entry,
        )
        self.device = device
        device.on_version_changed = self._persist_protocol_version

    def _persist_protocol_version(self, version: int) -> None:
        """Write an auto-detected protocol version back to the config entry."""
        stored = self.config_entry.data.get(CONF_VERSION, PROTO_V1)
        if stored == version:
            return
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_VERSION: version},
        )
        _LOGGER.info(
            "Updated stored protocol version to v%d for %s",
            version,
            self.device.host,
        )

    async def _async_update_data(self) -> dict[str, int]:
        try:
            return await self.device.get_status()
        except EwpeAuthError as err:
            raise ConfigEntryAuthFailed(
                "Device key rejected; reauthentication required"
            ) from err
        except EwpeError as err:
            raise UpdateFailed(str(err)) from err
