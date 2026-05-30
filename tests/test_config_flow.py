"""Tests for the user-facing config flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.ewpe_smart.const import (
    CONF_HOST,
    CONF_KEY,
    CONF_MAC,
    CONF_NAME,
    CONF_SILENT_COMMANDS,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_user_to_manual_to_create_entry(
    hass: HomeAssistant, patch_bind_success: None
) -> None:
    """Pick 'manual' from the menu, enter an IP, end up with a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.MENU

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "manual"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.168.1.10", CONF_NAME: "Living room AC"},
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living room AC"
    assert result["data"][CONF_HOST] == "192.168.1.10"
    assert result["data"][CONF_MAC] == "AA:BB:CC:DD:EE:FF"
    assert result["data"][CONF_KEY] == "abcdefghijklmnop"


@pytest.mark.asyncio
async def test_manual_timeout_shows_error(
    hass: HomeAssistant, patch_bind_timeout: None
) -> None:
    """A connection timeout on bind keeps the user on the form with an error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "10.0.0.99"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_duplicate_device_aborts(
    hass: HomeAssistant, patch_bind_success: None
) -> None:
    """Adding the same MAC twice aborts the second flow."""
    # First entry
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.10"}
    )

    # Second entry — same device, different IP
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.20"}
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_options_flow_persists_polling_interval(
    hass: HomeAssistant, patch_bind_success: None
) -> None:
    """The options flow round-trips the polling interval."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.10"}
    )
    entry_id = result["result"].entry_id

    with patch(
        "custom_components.ewpe_smart.coordinator.EwpeCoordinator._async_update_data",
        return_value={},
    ):
        result = await hass.config_entries.options.async_init(entry_id)
        assert result["type"] == data_entry_flow.FlowResultType.FORM

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"update_interval": 60, CONF_SILENT_COMMANDS: False},
        )
        assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
        assert result["data"]["update_interval"] == 60
        assert result["data"][CONF_SILENT_COMMANDS] is False
