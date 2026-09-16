"""Polling coordinator for an EWPE Smart device."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_HOST,
    CONF_VERSION,
    DEFAULT_BROADCAST,
    DEFAULT_PORT,
    DEFAULT_SCAN_TIMEOUT,
    DOMAIN,
    PROTO_V1,
)
from .device import (
    EwpeAuthError,
    EwpeConnectionError,
    EwpeDevice,
    EwpeError,
    EwpeTimeout,
    scan,
)

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

    async def _rediscover_host(self) -> bool:
        """Find the device by MAC after a DHCP lease moved it to a new IP."""
        try:
            found = await scan(DEFAULT_BROADCAST, DEFAULT_PORT, DEFAULT_SCAN_TIMEOUT)
        except EwpeError as err:
            _LOGGER.debug("Rediscovery scan failed: %s", err)
            return False

        for candidate in found:
            mac = candidate.get("cid") or candidate.get("mac")
            host = candidate.get("address")
            if mac != self.device.mac or not host or host == self.device.host:
                continue
            _LOGGER.info(
                "Device %s moved from %s to %s",
                self.device.mac,
                self.device.host,
                host,
            )
            self.device.host = host
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={**self.config_entry.data, CONF_HOST: host},
            )
            return True

        _LOGGER.debug("Device %s not found on the network", self.device.mac)
        return False

    async def _async_update_data(self) -> dict[str, int]:
        try:
            return await self.device.get_status()
        except EwpeAuthError as err:
            raise ConfigEntryAuthFailed(
                "Device key rejected; reauthentication required"
            ) from err
        except (EwpeTimeout, EwpeConnectionError) as err:
            if not await self._rediscover_host():
                raise UpdateFailed(str(err)) from err
            try:
                return await self.device.get_status()
            except EwpeError as retry_err:
                raise UpdateFailed(str(retry_err)) from retry_err
        except EwpeError as err:
            raise UpdateFailed(str(err)) from err
