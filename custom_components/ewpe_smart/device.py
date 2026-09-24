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
    PROTO_V1,
    PROTO_V2,
    TEMP_SENSOR_OFFSET,
)
from .params_catalog import (
    ALL_KNOWN_PARAMS,
    TEMP_OFFSET_PARAMS,
    param_batches,
    poll_params,
)
from .protocol import (
    EwpeAuthError,
    EwpeConnectionError,
    EwpeError,
    EwpeProtocolError,
    EwpeRefusedError,
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


def _info_from_scan(reply: dict[str, Any]) -> dict[str, Any]:
    return {
        k: reply[k] for k in ("brand", "model", "vender", "ver", "hid") if k in reply
    }


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
    supported_params: list[str] | None = None
    on_version_changed: Callable[[int], None] | None = field(
        default=None, repr=False, compare=False
    )

    def _alternate_version(self, version: int) -> int:
        return PROTO_V2 if version == PROTO_V1 else PROTO_V1

    async def _send_with_version_fallback(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
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

    async def fetch_info(self, timeout: float | None = None) -> None:
        """Refresh model/firmware details from a unicast scan."""
        reply, _version = await unicast_scan(
            self.host, self.port, timeout=timeout or self.timeout
        )
        if reply.get("t") != "dev":
            raise EwpeProtocolError(f"Unexpected scan reply: {reply!r}")
        self.info = _info_from_scan(reply)

    def _decode_status_reply(
        self, reply: dict[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        if reply.get("t") != "dat":
            raise EwpeProtocolError(f"Unexpected status reply: {reply!r}")
        if not isinstance(reply.get("dat"), list) or not isinstance(
            reply.get("cols"), list
        ):
            raise EwpeProtocolError(f"Status reply is malformed: {reply!r}")
        reply_cols: list[str] = reply["cols"]
        status = dict(zip(reply_cols, reply["dat"], strict=False))
        for param in TEMP_OFFSET_PARAMS:
            if param in status:
                raw = status[param]
                if isinstance(raw, (int, float)):
                    status[param] = int(raw) + TEMP_SENSOR_OFFSET
                elif isinstance(raw, str) and raw.lstrip("-").isdigit():
                    status[param] = int(raw) + TEMP_SENSOR_OFFSET
        return status, reply_cols

    async def get_status(self, cols: list[str] | None = None) -> dict[str, Any]:
        """Read the current state of the device."""
        if not self.key:
            raise EwpeError("Device is not bound; call bind() first")
        if cols is None:
            cols = poll_params(self.supported_params)
        batches = param_batches(cols) or ((),)
        merged_status: dict[str, Any] = {}
        merged_cols: list[str] = []
        for batch in batches:
            reply = await self._send_with_version_fallback(
                {"t": "status", "mac": self.mac, "cols": list(batch)},
            )
            status, reply_cols = self._decode_status_reply(reply)
            merged_status.update(status)
            merged_cols.extend(reply_cols)
        if cols == list(ALL_KNOWN_PARAMS):
            self.supported_params = list(dict.fromkeys(merged_cols))
            _LOGGER.info(
                "Device %s supports %d of %d known parameters",
                self.host,
                len(self.supported_params),
                len(ALL_KNOWN_PARAMS),
            )
        return merged_status

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
    "EwpeConnectionError",
    "EwpeDevice",
    "EwpeError",
    "EwpeProtocolError",
    "EwpeRefusedError",
    "EwpeTimeout",
    "scan",
]
