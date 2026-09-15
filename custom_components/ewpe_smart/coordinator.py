"""Polling coordinator for an EWPE Smart device."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .device import EwpeAuthError, EwpeDevice, EwpeError

_LOGGER = logging.getLogger(__name__)

type EwpeConfigEntry = ConfigEntry[EwpeCoordinator]


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

    async def _async_update_data(self) -> dict[str, int]:
        try:
            return await self.device.get_status()
        except EwpeAuthError as err:
            raise ConfigEntryAuthFailed(
                "Device key rejected; reauthentication required"
            ) from err
        except EwpeError as err:
            raise UpdateFailed(str(err)) from err
