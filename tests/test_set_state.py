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
    await _set_state(hass, hvac_mode="heat", temperature=22, fan_mode="quiet")
    assert mock.received_commands == [
        {"opt": ["Pow", "Mod", "SetTem", "Quiet", "Tur"], "p": [1, 4, 22, 2, 0]}
    ]
    assert hass.states.get(ENTITY_ID).state == "heat"


async def test_fixed_step_clears_quiet_and_turbo(hass: HomeAssistant) -> None:
    mock = await _setup(hass, {**STATUS, "Quiet": 2})
    await _set_state(hass, fan_mode="high")
    assert mock.received_commands == [
        {"opt": ["WdSpd", "Quiet", "Tur"], "p": [5, 0, 0]}
    ]


async def test_turbo_replaces_quiet(hass: HomeAssistant) -> None:
    mock = await _setup(hass, {**STATUS, "Quiet": 2})
    await _set_state(hass, fan_mode="turbo")
    assert mock.received_commands == [{"opt": ["Quiet", "Tur"], "p": [0, 1]}]


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
        await _set_state(hass, fan_mode="quiet")
    assert mock.received_commands == []


async def test_at_least_one_setting_is_required(hass: HomeAssistant) -> None:
    await _setup(hass, STATUS)
    with pytest.raises(Exception, match="at least one"):
        await _set_state(hass)


async def test_deprecated_switches_start_disabled_and_enabled_ones_raise_issue(
    hass: HomeAssistant,
) -> None:
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers import issue_registry as ir

    await _setup(hass, STATUS)
    registry = er.async_get(hass)
    quiet = registry.async_get("switch.living_room_ac_quiet")
    assert quiet.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert not ir.async_get(hass).issues


async def test_enabling_a_deprecated_switch_raises_issue(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers import issue_registry as ir

    await _setup(hass, STATUS)
    registry = er.async_get(hass)
    entity = registry.async_get("switch.living_room_ac_quiet")
    registry.async_update_entity(entity.entity_id, disabled_by=None)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(ir.async_get(hass).issues) == 1

    registry.async_update_entity(
        entity.entity_id, disabled_by=er.RegistryEntryDisabler.USER
    )
    await hass.async_block_till_done()
    assert not ir.async_get(hass).issues


async def test_repair_flow_disables_the_switch(hass: HomeAssistant) -> None:
    from homeassistant.helpers import entity_registry as er

    from custom_components.ewpe_smart.repairs import async_create_fix_flow

    await _setup(hass, STATUS)
    registry = er.async_get(hass)
    flow = await async_create_fix_flow(
        hass, "x", {"entity_id": "switch.living_room_ac_quiet"}
    )
    flow.hass = hass
    registry.async_update_entity("switch.living_room_ac_quiet", disabled_by=None)
    result = await flow.async_step_confirm({})
    assert result["type"] == "create_entry"
    quiet = registry.async_get("switch.living_room_ac_quiet")
    assert quiet.disabled_by is er.RegistryEntryDisabler.USER
