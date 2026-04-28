"""End-to-end tests of EwpeDevice against the in-process mock device.

These tests open real UDP sockets bound to 127.0.0.1, so the
``pytest-socket`` block (enabled by ``pytest-homeassistant-custom-component``)
must be lifted via the ``socket_enabled`` fixture.
"""

from __future__ import annotations

import asyncio

import pytest

from custom_components.ewpe_smart.device import EwpeDevice
from custom_components.ewpe_smart.protocol import (
    EwpeError,
    EwpeProtocolError,
    EwpeTimeout,
    unicast_scan,
)

from .mock_device import start_mock_device

pytestmark = pytest.mark.usefixtures("socket_enabled")


@pytest.mark.asyncio
async def test_unicast_scan_returns_dev_reply() -> None:
    """Unicast scan must be sent as raw JSON and return the decrypted dev info."""
    mock, port = await start_mock_device()

    reply = await unicast_scan("127.0.0.1", port, timeout=2.0)

    assert reply["t"] == "dev"
    assert reply["mac"] == mock.mac
    assert reply["name"] == mock.name


@pytest.mark.asyncio
async def test_bind_discovers_mac_and_obtains_key() -> None:
    mock, port = await start_mock_device()
    device = EwpeDevice(host="127.0.0.1", port=port, timeout=2.0)

    await device.bind()

    assert device.mac == mock.mac
    assert device.name == mock.name
    assert device.key == mock.device_key
    assert device.info.get("model") == "MockAC-1"


@pytest.mark.asyncio
async def test_get_status_returns_decoded_dict_with_temp_offset() -> None:
    _mock, port = await start_mock_device()
    device = EwpeDevice(host="127.0.0.1", port=port, timeout=2.0)
    await device.bind()

    status = await device.get_status()

    assert status["Pow"] == 1
    assert status["Mod"] == 1
    assert status["SetTem"] == 22
    # Mock returns raw 65 for TemSen → 65 + (-40) = 25
    assert status["TemSen"] == 25


@pytest.mark.asyncio
async def test_set_state_round_trip() -> None:
    mock, port = await start_mock_device()
    device = EwpeDevice(host="127.0.0.1", port=port, timeout=2.0)
    await device.bind()

    result = await device.set_state({"Pow": 1, "SetTem": 24})

    assert result == {"Pow": 1, "SetTem": 24}
    assert mock.received_commands == [{"opt": ["Pow", "SetTem"], "p": [1, 24]}]
    assert mock.status["SetTem"] == 24


@pytest.mark.asyncio
async def test_silent_device_raises_timeout() -> None:
    _mock, port = await start_mock_device(misbehave="silent")
    device = EwpeDevice(host="127.0.0.1", port=port, timeout=0.5)

    with pytest.raises(EwpeTimeout):
        await device.bind()


@pytest.mark.asyncio
async def test_garbage_reply_raises_protocol_error() -> None:
    _mock, port = await start_mock_device(misbehave="garbage")
    device = EwpeDevice(host="127.0.0.1", port=port, timeout=1.0)

    with pytest.raises(EwpeProtocolError):
        await device.bind()


@pytest.mark.asyncio
async def test_set_state_without_bind_raises() -> None:
    device = EwpeDevice(host="127.0.0.1", port=1, timeout=0.5)
    with pytest.raises(EwpeError):
        await device.set_state({"Pow": 1})


@pytest.mark.asyncio
async def test_concurrent_calls_do_not_cross_replies() -> None:
    _mock, port = await start_mock_device()
    device = EwpeDevice(host="127.0.0.1", port=port, timeout=2.0)
    await device.bind()

    results = await asyncio.gather(
        device.get_status(),
        device.get_status(),
        device.get_status(),
    )
    for r in results:
        assert r["Pow"] == 1
