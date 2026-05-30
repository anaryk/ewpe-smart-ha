"""End-to-end tests of EwpeDevice against the in-process mock device.

These tests open real UDP sockets bound to 127.0.0.1, so the
``pytest-socket`` block (enabled by ``pytest-homeassistant-custom-component``)
must be lifted via the ``socket_enabled`` fixture.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.ewpe_smart.const import PARAM_LIG, PARAM_QUIET, PROTO_V1, PROTO_V2
from custom_components.ewpe_smart.device import EwpeDevice
from custom_components.ewpe_smart.switch import supported_switch_descriptions
from custom_components.ewpe_smart.protocol import (
    EwpeError,
    EwpeProtocolError,
    EwpeTimeout,
    unicast_scan,
)

from .mock_device import start_mock_device

pytestmark = pytest.mark.usefixtures("socket_enabled")


@pytest.mark.asyncio
async def test_unicast_scan_returns_dev_reply_and_v1_version() -> None:
    """Unicast scan must be sent as raw JSON and return the decrypted dev info."""
    mock, port = await start_mock_device()

    reply, version = await unicast_scan("127.0.0.1", port, timeout=2.0)

    assert version == PROTO_V1
    assert reply["t"] == "dev"
    assert reply["mac"] == mock.mac
    assert reply["name"] == mock.name


@pytest.mark.asyncio
async def test_unicast_scan_detects_v2_from_reply_tag() -> None:
    """A V2-speaking device replies with a 'tag' field; scan auto-detects V2."""
    mock, port = await start_mock_device(protocol_version=PROTO_V2)

    reply, version = await unicast_scan("127.0.0.1", port, timeout=2.0)

    assert version == PROTO_V2
    assert reply["t"] == "dev"
    assert reply["mac"] == mock.mac


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
async def test_get_status_falls_back_to_alternate_protocol_version() -> None:
    """Hybrid devices may store v1 but require v2 for encrypted traffic."""
    device = EwpeDevice(
        host="127.0.0.1",
        port=7000,
        mac="AA:BB:CC:DD:EE:FF",
        key=b"abcdefghijklmnop",
        version=PROTO_V1,
        timeout=2.0,
    )
    version_updates: list[int] = []
    device.on_version_changed = version_updates.append

    dat_reply = {
        "t": "dat",
        "mac": device.mac,
        "cols": ["Pow", "Mod"],
        "dat": [1, 1],
    }

    with patch(
        "custom_components.ewpe_smart.device.send_request",
        new_callable=AsyncMock,
    ) as mock_send:
        mock_send.side_effect = [EwpeTimeout("v1 timeout"), dat_reply]
        status = await device.get_status(cols=["Pow", "Mod"])

    assert status == {"Pow": 1, "Mod": 1}
    assert device.version == PROTO_V2
    assert version_updates == [PROTO_V2]
    assert mock_send.await_args_list[0].kwargs["version"] == PROTO_V1
    assert mock_send.await_args_list[1].kwargs["version"] == PROTO_V2


@pytest.mark.asyncio
async def test_get_status_omits_unsupported_switch_params_from_mock() -> None:
    """Mock devices only echo params they know about (hide-when-missing semantics)."""
    mock, port = await start_mock_device(
        status={
            "Pow": 1,
            "Mod": 1,
            "SetTem": 22,
            "TemUn": 0,
            "WdSpd": 0,
            "TemSen": 65,
            "Quiet": 0,
            "Lig": 1,
        }
    )
    device = EwpeDevice(host="127.0.0.1", port=port, timeout=2.0)
    await device.bind()

    status = await device.get_status()
    descriptions = supported_switch_descriptions(status)

    assert PARAM_QUIET in status
    assert PARAM_LIG in status
    assert "Tur" not in status
    assert {d.param for d in descriptions} == {PARAM_QUIET, PARAM_LIG}
    assert mock.mac == device.mac


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


@pytest.mark.asyncio
async def test_v2_device_full_lifecycle() -> None:
    """A V2 mock device walks through bind → status → set_state successfully."""
    mock, port = await start_mock_device(protocol_version=PROTO_V2)
    device = EwpeDevice(host="127.0.0.1", port=port, timeout=2.0)

    await device.bind()
    assert device.version == PROTO_V2
    assert device.mac == mock.mac
    assert device.key == mock.device_key

    status = await device.get_status()
    assert status["Pow"] == 1
    assert status["TemSen"] == 25

    result = await device.set_state({"Pow": 0, "SetTem": 23})
    assert result == {"Pow": 0, "SetTem": 23}
    assert mock.status["SetTem"] == 23
    assert mock.status["Pow"] == 0


@pytest.mark.asyncio
async def test_v2_bind_uses_v2_generic_key() -> None:
    """Bind to a V2 device must use the V2 generic key, not V1."""
    mock, port = await start_mock_device(protocol_version=PROTO_V2)
    device = EwpeDevice(host="127.0.0.1", port=port, timeout=2.0)

    # If the V1 key were sent, the mock would fail to decrypt and never reply
    # with a bindok — this would surface as a timeout.
    await device.bind()

    assert device.key == mock.device_key
