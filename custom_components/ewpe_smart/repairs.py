"""Repair flows for EWPE Smart."""

from __future__ import annotations

from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


class DisableSwitchRepairFlow(ConfirmRepairFlow):
    """Disable the deprecated switch the issue is about."""

    def __init__(self, entity_id: str) -> None:
        self._entity_id = entity_id

    async def async_step_confirm(self, user_input=None):
        if user_input is None:
            return self.async_show_form(step_id="confirm")
        registry = er.async_get(self.hass)
        if registry.async_get(self._entity_id):
            registry.async_update_entity(
                self._entity_id, disabled_by=er.RegistryEntryDisabler.USER
            )
        return self.async_create_entry(data={})


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the flow that fixes a deprecated-switch issue."""
    return DisableSwitchRepairFlow(str((data or {})["entity_id"]))
