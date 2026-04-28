"""High-level wrapper around a single EWPE Smart device."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .const import (
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    GENERIC_KEY,
    PARAM_TEMP_SENSOR,
    PHASE1_PARAMS,
    TEMP_SENSOR_OFFSET,
)
from .protocol import (
    EwpeAuthError,
    EwpeError,
    EwpeProtocolError,
    EwpeTimeout,
    scan,
    send_request,
    unicast_scan,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class EwpeDevice:
    """Encapsulates one EWPE Smart air conditioner."""

    host: str
    port: int = DEFAULT_PORT
    mac: str | None = None
    name: str | None = None
    key: bytes | None = None
    timeout: float = DEFAULT_TIMEOUT
    info: dict[str, Any] = field(default_factory=dict)

    async def bind(self) -> None:
        """Discover MAC/name (if not already known) and obtain the device key."""
        if not self.mac:
            await self._discover()

        _LOGGER.info(
            "Binding to %s (mac %s) on %s:%s", self.name, self.mac, self.host, self.port
        )
        reply = await send_request(
            self.host,
            self.port,
            GENERIC_KEY,
            {"mac": self.mac, "t": "bind", "uid": 0},
            timeout=self.timeout,
        )
        if reply.get("t") != "bindok":
            raise EwpeProtocolError(f"Unexpected bind reply: {reply!r}")
        key = reply.get("key")
        if not isinstance(key, str) or not key:
            raise EwpeProtocolError("Bind reply contains no usable key")
        self.key = key.encode("utf-8")
        _LOGGER.info("Bound device %s (%s) on %s", self.name, self.mac, self.host)

    async def _discover(self) -> None:
        """Send a unicast scan to ``self.host`` to learn MAC and name."""
        _LOGGER.info(
            "Discovering device on %s:%s via unicast scan", self.host, self.port
        )
        reply = await unicast_scan(self.host, self.port, timeout=self.timeout)
        if reply.get("t") != "dev":
            raise EwpeProtocolError(f"Unexpected scan reply: {reply!r}")
        mac = reply.get("cid") or reply.get("mac")
        if not mac:
            raise EwpeProtocolError("Scan reply contains no MAC")
        self.mac = mac
        self.name = reply.get("name") or mac
        self.info = {
            k: reply[k]
            for k in ("brand", "model", "vender", "ver", "hid")
            if k in reply
        }
        _LOGGER.info(
            "Discovered %s (mac=%s, model=%s)",
            self.name,
            self.mac,
            self.info.get("model", "unknown"),
        )

    async def get_status(self, cols: list[str] | None = None) -> dict[str, int]:
        """Read the current state of the device."""
        if not self.key:
            raise EwpeError("Device is not bound; call bind() first")
        cols = cols or PHASE1_PARAMS
        reply = await send_request(
            self.host,
            self.port,
            self.key,
            {"cols": cols, "mac": self.mac, "t": "status"},
            timeout=self.timeout,
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
        reply = await send_request(
            self.host,
            self.port,
            self.key,
            {"opt": opt, "p": values, "mac": self.mac, "t": "cmd"},
            timeout=self.timeout,
        )
        if reply.get("t") != "res":
            raise EwpeProtocolError(f"Unexpected cmd reply: {reply!r}")
        if not isinstance(reply.get("opt"), list) or not isinstance(
            reply.get("val"), list
        ):
            raise EwpeProtocolError(f"Cmd reply is malformed: {reply!r}")
        return dict(zip(reply["opt"], reply["val"], strict=False))


__all__ = [
    "EwpeAuthError",
    "EwpeDevice",
    "EwpeError",
    "EwpeProtocolError",
    "EwpeTimeout",
    "scan",
]
