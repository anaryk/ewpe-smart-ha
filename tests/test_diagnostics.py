"""Tests for the diagnostics download."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from .mock_device import start_mock_device
from .test_init import _setup_entry

pytestmark = pytest.mark.usefixtures("socket_enabled")


async def test_diagnostics_redacts_key_and_mac(
    hass: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    _mock, port = await start_mock_device()
    entry = await _setup_entry(hass, port)

    diag = await get_diagnostics_for_config_entry(hass, hass_client, entry)

    assert diag["entry"]["data"]["key"] == "**REDACTED**"
    assert diag["entry"]["data"]["mac"] == "**REDACTED**"
    assert diag["entry"]["unique_id"] == "**REDACTED**"
    assert diag["entry"]["data"]["host"] == "127.0.0.1"
    assert diag["device"] == {
        "protocol_version": 1,
        "info": {
            "brand": "Daitsu",
            "model": "MockAC-1",
            "vender": "Gree",
            "ver": "V1.0.0",
        },
    }
    assert diag["coordinator"]["last_update_success"] is True
    assert diag["coordinator"]["update_interval"] == 30
    assert diag["status"]["TemSen"] == 25
