"""Tests for parameter catalog helpers."""

from __future__ import annotations

from custom_components.ewpe_smart.params_catalog import (
    ALL_KNOWN_PARAMS,
    EXPECTED_DEVICE_PARAM_COUNT,
    diagnostic_params,
)


def test_diagnostic_params_exclude_mapped_params() -> None:
    data = {
        "Pow": 1,
        "TemRec": 1,
        "SwhSlp": 0,
        "SlpMod": 0,
        "NewTimer": 3,
    }
    raw = diagnostic_params(data)
    assert "NewTimer" not in raw
    assert "Pow" not in raw
    assert "SwhSlp" not in raw
    assert "SlpMod" not in raw


def test_full_catalog_has_no_generic_diagnostic_fallback() -> None:
    data = dict.fromkeys(ALL_KNOWN_PARAMS, 0)
    assert diagnostic_params(data) == ()


def test_wire_catalog_is_complete_against_device_payload() -> None:
    """Guardrail: custom_components/ewpe_smart/data/wire_params.json must list all reference device wire keys."""
    assert len(ALL_KNOWN_PARAMS) == EXPECTED_DEVICE_PARAM_COUNT, (
        f"wire_params.json has {len(ALL_KNOWN_PARAMS)} keys; "
        f"expected {EXPECTED_DEVICE_PARAM_COUNT} from device payload"
    )
