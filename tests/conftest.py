"""Shared fixtures for the EWPE Smart test suite."""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None, None, None]:
    """Make the ``custom_components/ewpe_smart`` integration loadable in tests."""
    yield


@pytest.fixture
def patch_bind_success() -> Generator[None, None, None]:
    """Stub out ``EwpeDevice.bind`` to succeed without touching the network."""
    from custom_components.ewpe_smart.device import EwpeDevice

    async def fake_bind(self: EwpeDevice) -> None:
        self.mac = self.mac or "AA:BB:CC:DD:EE:FF"
        self.name = self.name or "MockAC"
        self.key = self.key or b"abcdefghijklmnop"
        self.version = self.version or 1

    async def fake_get_status(self: EwpeDevice, cols=None):  # noqa: ANN001
        return {
            "Pow": 1,
            "Mod": 1,
            "SetTem": 22,
            "TemUn": 0,
            "WdSpd": 0,
            "TemSen": 25,
        }

    with (
        patch.object(EwpeDevice, "bind", fake_bind),
        patch.object(EwpeDevice, "get_status", fake_get_status),
    ):
        yield


@pytest.fixture
def patch_bind_timeout() -> Generator[None, None, None]:
    """Stub out ``EwpeDevice.bind`` to raise a timeout."""
    from custom_components.ewpe_smart.device import EwpeDevice
    from custom_components.ewpe_smart.protocol import EwpeTimeout

    async def fake_bind(self: EwpeDevice) -> None:
        raise EwpeTimeout("simulated timeout")

    with patch.object(EwpeDevice, "bind", fake_bind):
        yield
