"""Config and options flow for EWPE Smart."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .const import (
    CONF_BROADCAST,
    CONF_HOST,
    CONF_KEY,
    CONF_MAC,
    CONF_NAME,
    CONF_PORT,
    CONF_SILENT_COMMANDS,
    CONF_UPDATE_INTERVAL,
    CONF_VERSION,
    DEFAULT_BROADCAST,
    DEFAULT_PORT,
    DEFAULT_SCAN_TIMEOUT,
    DEFAULT_SILENT_COMMANDS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)
from .device import (
    EwpeAuthError,
    EwpeDevice,
    EwpeError,
    EwpeProtocolError,
    EwpeTimeout,
    scan,
)

_LOGGER = logging.getLogger(__name__)


async def _bind_device(host: str) -> EwpeDevice:
    """Instantiate an :class:`EwpeDevice` and run scan+bind on one UDP session."""
    device = EwpeDevice(host=host)
    await device.bind()
    return device


class EwpeSmartConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the configuration of a single EWPE Smart device."""

    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a menu to choose between manual entry and discovery."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["manual", "discover"],
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a device by typing its IP address."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            try:
                device = await _bind_device(host)
            except EwpeTimeout:
                errors["base"] = "cannot_connect"
            except (EwpeAuthError, EwpeProtocolError):
                errors["base"] = "invalid_response"
            except EwpeError:
                _LOGGER.exception("Unexpected EWPE error during manual bind")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(device.mac)
                self._abort_if_unique_id_configured()
                title = user_input.get(CONF_NAME) or device.name or host
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_HOST: host,
                        CONF_PORT: DEFAULT_PORT,
                        CONF_MAC: device.mac,
                        CONF_KEY: device.key.decode("utf-8"),
                        CONF_NAME: title,
                        CONF_VERSION: device.version,
                    },
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_NAME): str,
                }
            ),
            errors=errors,
        )

    async def async_step_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Run a UDP broadcast scan and let the user pick a device."""
        errors: dict[str, str] = {}
        if user_input is not None:
            broadcast = user_input.get(CONF_BROADCAST, DEFAULT_BROADCAST)
            try:
                discovered = await scan(broadcast, DEFAULT_PORT, DEFAULT_SCAN_TIMEOUT)
            except EwpeError:
                _LOGGER.exception("Scan failed")
                errors["base"] = "scan_failed"
            else:
                if not discovered:
                    errors["base"] = "no_devices"
                else:
                    self._discovered = discovered
                    return await self.async_step_pick_device()

        return self.async_show_form(
            step_id="discover",
            data_schema=vol.Schema(
                {vol.Optional(CONF_BROADCAST, default=DEFAULT_BROADCAST): str}
            ),
            errors=errors,
        )

    async def async_step_pick_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """After scan, show the list of devices and let the user pick one."""
        errors: dict[str, str] = {}
        choices = {
            d["address"]: f"{d.get('name', d.get('cid', d['address']))}"
            f" ({d['address']})"
            for d in getattr(self, "_discovered", [])
        }
        if not choices:
            return await self.async_step_manual()

        if user_input is not None:
            host = user_input[CONF_HOST]
            try:
                device = await _bind_device(host)
            except EwpeTimeout:
                errors["base"] = "cannot_connect"
            except (EwpeAuthError, EwpeProtocolError):
                errors["base"] = "invalid_response"
            except EwpeError:
                _LOGGER.exception("Unexpected EWPE error during pick-device bind")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(device.mac)
                self._abort_if_unique_id_configured()
                title = device.name or host
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_HOST: host,
                        CONF_PORT: DEFAULT_PORT,
                        CONF_MAC: device.mac,
                        CONF_KEY: device.key.decode("utf-8"),
                        CONF_NAME: title,
                        CONF_VERSION: device.version,
                    },
                )

        return self.async_show_form(
            step_id="pick_device",
            data_schema=vol.Schema({vol.Required(CONF_HOST): vol.In(choices)}),
            errors=errors,
        )

    async def async_step_reauth(self, _entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Trigger reauth when the stored device key stops working."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-run the bind handshake after a key mismatch."""
        assert self._reauth_entry is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            host = self._reauth_entry.data[CONF_HOST]
            try:
                device = await _bind_device(host)
            except EwpeError:
                errors["base"] = "cannot_connect"
            else:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        **self._reauth_entry.data,
                        CONF_KEY: device.key.decode("utf-8"),
                        CONF_VERSION: device.version,
                    },
                )
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EwpeOptionsFlow(config_entry)


class EwpeOptionsFlow(OptionsFlow):
    """Allow the user to change the polling interval after setup."""

    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        current_silent = self.entry.options.get(
            CONF_SILENT_COMMANDS, DEFAULT_SILENT_COMMANDS
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SILENT_COMMANDS, default=current_silent): bool,
                    vol.Optional(CONF_UPDATE_INTERVAL, default=current_interval): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL),
                    ),
                }
            ),
        )
