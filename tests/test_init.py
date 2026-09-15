"""Tests for config entry setup and unload against the mock device."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ewpe_smart.const import (
    CONF_HOST,
    CONF_KEY,
    CONF_MAC,
    CONF_NAME,
    CONF_PORT,
    CONF_VERSION,
    DOMAIN,
    PROTO_V1,
)
from custom_components.ewpe_smart.coordinator import EwpeCoordinator
from custom_components.ewpe_smart.protocol import EwpeTimeout

from .mock_device import start_mock_device

pytestmark = pytest.mark.usefixtures("socket_enabled")


async def _setup_entry(hass: HomeAssistant, port: int) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="AA:BB:CC:DD:EE:FF",
        title="Living room AC",
        data={
            CONF_HOST: "127.0.0.1",
            CONF_PORT: port,
            CONF_MAC: "AA:BB:CC:DD:EE:FF",
            CONF_KEY: "abcdefghijklmnop",
            CONF_NAME: "Living room AC",
            CONF_VERSION: PROTO_V1,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_and_unload(hass: HomeAssistant) -> None:
    _mock, port = await start_mock_device()
    entry = await _setup_entry(hass, port)

    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, EwpeCoordinator)
    assert hass.states.get("climate.living_room_ac") is not None
    assert hass.states.get("sensor.living_room_ac_indoor_temperature").state == "25.0"

    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert device.model == "MockAC-1"
    assert device.sw_version == "V1.0.0"

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_survives_missing_scan_reply(hass: HomeAssistant) -> None:
    _mock, port = await start_mock_device()
    with patch(
        "custom_components.ewpe_smart.device.unicast_scan",
        side_effect=EwpeTimeout("no scan reply"),
    ):
        entry = await _setup_entry(hass, port)

    assert entry.state is ConfigEntryState.LOADED
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert device.model is None


async def test_setup_retries_when_device_is_offline(hass: HomeAssistant) -> None:
    _mock, port = await start_mock_device()
    with patch(
        "custom_components.ewpe_smart.device.EwpeDevice.get_status",
        side_effect=EwpeTimeout("no reply"),
    ):
        entry = await _setup_entry(hass, port)

    assert entry.state is ConfigEntryState.SETUP_RETRY
