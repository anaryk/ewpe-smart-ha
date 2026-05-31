"""High-level wrapper around a single EWPE Smart device."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .const import (
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    GENERIC_KEY,
    GENERIC_KEY_V2,
    PARAM_TEMP_SENSOR,
    PHASE1_PARAMS,
    PROTO_V1,
    PROTO_V2,
    TEMP_SENSOR_OFFSET,
)
from .protocol import (
    EwpeAuthError,
    EwpeError,
    EwpeProtocolError,
    EwpeTimeout,
    parse_cmd_reply,
    scan,
    scan_then_bind,
    send_request,
    unicast_scan,
)

_LOGGER = logging.getLogger(__name__)


def _generic_key_for(version: int) -> bytes:
    return GENERIC_KEY_V2 if version == PROTO_V2 else GENERIC_KEY


@dataclass
class EwpeDevice:
    """Encapsulates one EWPE Smart air conditioner."""

    host: str
    port: int = DEFAULT_PORT
    mac: str | None = None
    name: str | None = None
    key: bytes | None = None
    version: int = PROTO_V1
    timeout: float = DEFAULT_TIMEOUT
    info: dict[str, Any] = field(default_factory=dict)
    on_version_changed: Callable[[int], None] | None = field(
        default=None, repr=False, compare=False
    )

    def _alternate_version(self, version: int) -> int:
        return PROTO_V2 if version == PROTO_V1 else PROTO_V1

    async def _send_with_version_fallback(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send an encrypted request, retrying on the other protocol version if needed."""
        try:
            return await send_request(
                self.host,
                self.port,
                self.key,
                payload,
                timeout=self.timeout,
                version=self.version,
            )
        except (EwpeTimeout, EwpeAuthError) as err:
            alternate = self._alternate_version(self.version)
            _LOGGER.info(
                "Request %s failed on proto v%d for %s, trying v%d",
                payload.get("t"),
                self.version,
                self.host,
                alternate,
            )
            try:
                reply = await send_request(
                    self.host,
                    self.port,
                    self.key,
                    payload,
                    timeout=self.timeout,
                    version=alternate,
                )
            except EwpeError:
                raise err from None
            self._set_version(alternate)
            return reply

    def _set_version(self, version: int) -> None:
        if self.version == version:
            return
        _LOGGER.info(
            "Device %s now using proto v%d (was v%d)",
            self.host,
            version,
            self.version,
        )
        self.version = version
        if self.on_version_changed is not None:
            self.on_version_changed(version)

    async def bind(self, *, protocol_version: int | None = None) -> None:
        """Discover MAC/name (if not already known) and obtain the device key."""
        _LOGGER.info(
            "Binding to %s on %s:%s",
            self.name or self.host,
            self.host,
            self.port,
        )
        if self.mac and self.key:
            return

        dev_reply, version, reply = await scan_then_bind(
            self.host,
            self.port,
            timeout=self.timeout,
            version=protocol_version,
        )
        if not self.mac:
            mac = dev_reply.get("cid") or dev_reply.get("mac")
            if not mac:
                raise EwpeProtocolError("Scan reply contains no MAC")
            self.mac = mac
            self.name = dev_reply.get("name") or mac
            self.version = version
            self.info = {
                k: dev_reply[k]
                for k in ("brand", "model", "vender", "ver", "hid")
                if k in dev_reply
            }
            _LOGGER.info(
                "Discovered %s (mac=%s, model=%s, proto=v%d)",
                self.name,
                self.mac,
                self.info.get("model", "unknown"),
                self.version,
            )

        if reply.get("t") != "bindok":
            raise EwpeProtocolError(f"Unexpected bind reply: {reply!r}")
        key = reply.get("key")
        if not isinstance(key, str) or not key:
            raise EwpeProtocolError("Bind reply contains no usable key")
        self.key = key.encode("utf-8")
        _LOGGER.info(
            "Bound device %s (%s, proto v%d) on %s",
            self.name,
            self.mac,
            self.version,
            self.host,
        )

    async def _discover(self) -> None:
        """Send a unicast scan to learn MAC, name, and protocol version."""
        _LOGGER.info(
            "Discovering device on %s:%s via unicast scan", self.host, self.port
        )
        reply, version = await unicast_scan(self.host, self.port, timeout=self.timeout)
        if reply.get("t") != "dev":
            raise EwpeProtocolError(f"Unexpected scan reply: {reply!r}")
        mac = reply.get("cid") or reply.get("mac")
        if not mac:
            raise EwpeProtocolError("Scan reply contains no MAC")
        self.mac = mac
        self.name = reply.get("name") or mac
        self.version = version
        self.info = {
            k: reply[k]
            for k in ("brand", "model", "vender", "ver", "hid")
            if k in reply
        }
        _LOGGER.info(
            "Discovered %s (mac=%s, model=%s, proto=v%d)",
            self.name,
            self.mac,
            self.info.get("model", "unknown"),
            self.version,
        )

    async def get_status(self, cols: list[str] | None = None) -> dict[str, int]:
        """Read the current state of the device."""
        if not self.key:
            raise EwpeError("Device is not bound; call bind() first")
        cols = cols or PHASE1_PARAMS
        reply = await self._send_with_version_fallback(
            {"t": "status", "mac": self.mac, "cols": cols},
        )
        if reply.get("t") != "dat":
            raise EwpeProtocolError(f"Unexpected status reply: {reply!r}")
        if not isinstance(reply.get("dat"), list) or not isinstance(
            reply.get("cols"), list
        ):
            raise EwpeProtocolError(f"Status reply is malformed: {reply!r}")
        status = dict(zip(reply["cols"], reply["dat"], strict=False))
        if PARAM_TEMP_SENSOR in status:
            status[PARAM_TEMP_SENSOR] = (
                int(status[PARAM_TEMP_SENSOR]) + TEMP_SENSOR_OFFSET
            )
        return status

    async def set_state(self, params: dict[str, int]) -> dict[str, int]:
        """Apply ``params`` (key → numeric value) to the device."""
        if not self.key:
            raise EwpeError("Device is not bound; call bind() first")
        if not params:
            return {}
        opt = list(params.keys())
        values = list(params.values())
        reply = await self._send_with_version_fallback(
            {"t": "cmd", "mac": self.mac, "opt": opt, "p": values},
        )
        return parse_cmd_reply(reply)


__all__ = [
    "EwpeAuthError",
    "EwpeDevice",
    "EwpeError",
    "EwpeProtocolError",
    "EwpeTimeout",
    "scan",
]
