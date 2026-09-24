"""Tests for the ewpe_smart.set_state service."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
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

from .mock_device import start_mock_device

pytestmark = pytest.mark.usefixtures("socket_enabled")

ENTITY_ID = "climate.living_room_ac"
STATUS = {
    "Pow": 0,
    "Mod": 1,
    "SetTem": 24,
    "TemUn": 0,
    "WdSpd": 3,
    "TemSen": 65,
    "Quiet": 0,
    "Tur": 0,
}


async def _setup(hass: HomeAssistant, status: dict[str, int]):
    mock, port = await start_mock_device(status=dict(status))
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
    return mock


async def _set_state(hass: HomeAssistant, **data) -> None:
    await hass.services.async_call(
        DOMAIN, "set_state", {"entity_id": ENTITY_ID, **data}, blocking=True
    )


async def test_everything_goes_out_in_one_packet(hass: HomeAssistant) -> None:
    mock = await _setup(hass, STATUS)
    await _set_state(
        hass, hvac_mode="heat", temperature=22, fan_mode="medium_low", quiet=True
    )
    assert mock.received_commands == [
        {"opt": ["Pow", "Mod", "SetTem", "WdSpd", "Quiet"], "p": [1, 4, 22, 2, 2]}
    ]
    assert hass.states.get(ENTITY_ID).state == "heat"


async def test_quiet_and_turbo_off_write_zero(hass: HomeAssistant) -> None:
    mock = await _setup(hass, {**STATUS, "Quiet": 2, "Tur": 1})
    await _set_state(hass, quiet=False, turbo=False)
    assert mock.received_commands == [{"opt": ["Quiet", "Tur"], "p": [0, 0]}]


@pytest.mark.parametrize(
    "data",
    [
        {"temperature": 31},
        {"fan_mode": "silent"},
        {"hvac_mode": "heat_cool"},
    ],
)
async def test_invalid_values_send_nothing(
    hass: HomeAssistant, data: dict[str, object]
) -> None:
    mock = await _setup(hass, STATUS)
    with pytest.raises(ServiceValidationError):
        await _set_state(hass, **data)
    assert mock.received_commands == []


async def test_quiet_on_unit_without_quiet_is_rejected(hass: HomeAssistant) -> None:
    status = {k: v for k, v in STATUS.items() if k not in ("Quiet", "Tur")}
    mock = await _setup(hass, status)
    with pytest.raises(ServiceValidationError):
        await _set_state(hass, quiet=True)
    assert mock.received_commands == []


async def test_at_least_one_setting_is_required(hass: HomeAssistant) -> None:
    await _setup(hass, STATUS)
    with pytest.raises(Exception, match="at least one"):
        await _set_state(hass)
