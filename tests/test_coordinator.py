"""Tests for the polling coordinator's IP self-healing."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ewpe_smart.const import (
    CONF_HOST,
    CONF_KEY,
    CONF_MAC,
    CONF_NAME,
    DOMAIN,
)
from custom_components.ewpe_smart.coordinator import EwpeCoordinator
from custom_components.ewpe_smart.device import EwpeDevice, EwpeError
from custom_components.ewpe_smart.protocol import EwpeConnectionError, EwpeTimeout

MAC = "AA:BB:CC:DD:EE:FF"


def _coordinator(hass: HomeAssistant) -> EwpeCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MAC,
        data={
            CONF_HOST: "192.168.1.10",
            CONF_MAC: MAC,
            CONF_KEY: "abcdefghijklmnop",
            CONF_NAME: "Living room AC",
        },
    )
    entry.add_to_hass(hass)
    device = EwpeDevice(
        host="192.168.1.10", mac=MAC, name="Living room AC", key=b"abcdefghijklmnop"
    )
    return EwpeCoordinator(hass, entry, device, 30)


def _status_that_fails_on(host: str, error: type[EwpeError] = EwpeTimeout):
    async def get_status(self: EwpeDevice, cols=None):  # noqa: ANN001
        if self.host == host:
            raise error(f"Cannot reach {self.host}")
        return {"Pow": 1}

    return get_status


@pytest.mark.asyncio
async def test_timeout_follows_device_to_new_ip(hass: HomeAssistant) -> None:
    """A moved device is found by MAC, and the new IP is stored on the entry."""
    coordinator = _coordinator(hass)
    scan_result = [{"cid": MAC, "address": "192.168.1.55", "name": "Living room AC"}]

    with (
        patch.object(EwpeDevice, "get_status", _status_that_fails_on("192.168.1.10")),
        patch(
            "custom_components.ewpe_smart.coordinator.scan",
            new=AsyncMock(return_value=scan_result),
        ),
    ):
        data = await coordinator._async_update_data()

    assert data == {"Pow": 1}
    assert coordinator.device.host == "192.168.1.55"
    assert coordinator.config_entry.data[CONF_HOST] == "192.168.1.55"


@pytest.mark.asyncio
async def test_timeout_without_rediscovery_fails(hass: HomeAssistant) -> None:
    """A device that answers no scan leaves the stored IP untouched."""
    coordinator = _coordinator(hass)

    with (
        patch.object(EwpeDevice, "get_status", _status_that_fails_on("192.168.1.10")),
        patch(
            "custom_components.ewpe_smart.coordinator.scan",
            new=AsyncMock(
                return_value=[{"cid": "11:22:33:44:55:66", "address": "1.2.3.4"}]
            ),
        ),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()

    assert coordinator.device.host == "192.168.1.10"
    assert coordinator.config_entry.data[CONF_HOST] == "192.168.1.10"


@pytest.mark.asyncio
async def test_icmp_unreachable_also_triggers_rediscovery(hass: HomeAssistant) -> None:
    """A stale IP answering with ICMP unreachable is a move, not a dead device."""
    coordinator = _coordinator(hass)
    scan_result = [{"cid": MAC, "address": "192.168.1.55", "name": "Living room AC"}]

    with (
        patch.object(
            EwpeDevice,
            "get_status",
            _status_that_fails_on("192.168.1.10", EwpeConnectionError),
        ),
        patch(
            "custom_components.ewpe_smart.coordinator.scan",
            new=AsyncMock(return_value=scan_result),
        ),
    ):
        data = await coordinator._async_update_data()

    assert data == {"Pow": 1}
    assert coordinator.config_entry.data[CONF_HOST] == "192.168.1.55"
