# Copyright (c) 2026 Adrien40
# This file is part of Flipr Local.

from types import SimpleNamespace

import pytest

from custom_components.flipr_local import FliprDataCoordinator
from custom_components.flipr_local.const import (
    CONF_SYNC_MODE,
    CONF_USE_GATEWAY,
    FLIPR_ANALYZE_UUID,
    SYNC_CHAR_UUID,
    get_flipr_model,
)


@pytest.fixture
def coordinator():
    """A bare coordinator instance.

    `_parse_raw_frame` and `_compute_ph_calibrated` are pure (they never touch
    instance state), so we skip __init__ to avoid pulling in a full Home
    Assistant runtime just to exercise the math.
    """
    return object.__new__(FliprDataCoordinator)


def _frame(temp_int=417, ph_mv=1600, orp_int=1300, sync=2, bat_mv=3600):
    """Build a 13-byte Flipr BLE frame from field values (little-endian)."""
    return bytes(
        [
            *temp_int.to_bytes(2, "little"),  # 0-1: temp, *0.06
            *ph_mv.to_bytes(2, "little"),  # 2-3: pH raw mV
            *orp_int.to_bytes(2, "little"),  # 4-5: ORP, /2
            0x00,
            0x00,  # 6-7: unused
            sync,  # 8: sync mode
            0x00,
            0x00,  # 9-10: unused
            *bat_mv.to_bytes(2, "little"),  # 11-12: battery mV
        ]
    )


# ==========================================
# _parse_raw_frame
# ==========================================


def test_parses_a_valid_frame(coordinator):
    raw_temp, ph_raw_mv, raw_orp, sync_mode, bat_raw = coordinator._parse_raw_frame(
        _frame()
    )
    assert ph_raw_mv == 1600
    assert raw_orp == 650.0
    assert sync_mode == "2"
    assert bat_raw == 3600
    assert raw_temp == pytest.approx(25.02, abs=0.01)


def test_short_frame_returns_none(coordinator):
    assert coordinator._parse_raw_frame(b"\x00" * 12) is None


def test_implausible_ph_rejected(coordinator):
    # 100 mV is below the 500 mV plausibility floor.
    assert coordinator._parse_raw_frame(_frame(ph_mv=100)) is None


def test_implausible_temperature_rejected(coordinator):
    # 60000 * 0.06 = 3600 C, far above the 50 C ceiling.
    assert coordinator._parse_raw_frame(_frame(temp_int=60000)) is None


def test_implausible_battery_rejected(coordinator):
    # 5000 mV is above the battery plausibility ceiling (~4100 mV).
    assert coordinator._parse_raw_frame(_frame(bat_mv=5000)) is None


# ==========================================
# _compute_ph_calibrated
# ==========================================


def test_calibration_returns_reference_at_its_own_mv(coordinator):
    # Feeding the pH 7 calibration mV must return the pH 7 reference, and the
    # pH 4 mV must return the pH 4 reference.
    c7_mv, c4_mv, ref7, ref4 = 1634.0, 1916.0, 7.02, 4.00
    at_7 = coordinator._compute_ph_calibrated(c7_mv, c4_mv, c7_mv, ref4, ref7)
    at_4 = coordinator._compute_ph_calibrated(c4_mv, c4_mv, c7_mv, ref4, ref7)
    assert at_7 == pytest.approx(7.02, abs=0.001)
    assert at_4 == pytest.approx(4.00, abs=0.001)


def test_equal_references_fall_back_to_seven(coordinator):
    assert coordinator._compute_ph_calibrated(1600, 1916, 1634, 7.0, 7.0) == 7.0


def test_zero_slope_falls_back_to_seven(coordinator):
    # Identical calibration mV -> zero slope -> safe fallback.
    assert coordinator._compute_ph_calibrated(1600, 1700, 1700, 4.0, 7.0) == 7.0


# ==========================================
# get_flipr_model
# ==========================================


@pytest.mark.parametrize(
    "name,expected",
    [
        ("F3A123", "Flipr AnalysR 3"),
        ("F2B456", "Flipr AnalysR"),
        ("FLIPR 01-XX", "Flipr Start Max"),
        ("FLIPR 00-XX", "Flipr Start Max"),
        ("something-else", "Flipr"),
        (None, "Flipr"),
    ],
)
def test_get_flipr_model(name, expected):
    assert get_flipr_model(name) == expected


# ==========================================
# _select_command
# ==========================================


def _coord(init_done, pending_type="analyze", pending_val=0x01):
    coord = object.__new__(FliprDataCoordinator)
    coord._init_done = init_done
    coord._pending_cmd_type = pending_type
    coord._pending_cmd_val = pending_val
    return coord


def _entry(options=None, data=None):
    return SimpleNamespace(options=options or {}, data=data or {})


def test_select_command_first_cycle_with_gateway_uses_sync_mode():
    coord = _coord(init_done=False)
    assert coord._select_command(_entry(options={CONF_SYNC_MODE: "3"})) == (
        "mode",
        3,
        SYNC_CHAR_UUID,
    )


def test_select_command_first_cycle_defaults_to_eco_mode():
    coord = _coord(init_done=False)
    assert coord._select_command(_entry()) == ("mode", 2, SYNC_CHAR_UUID)


def test_select_command_first_cycle_without_gateway_analyzes():
    coord = _coord(init_done=False)
    assert coord._select_command(_entry(options={CONF_USE_GATEWAY: False})) == (
        "analyze",
        0x01,
        FLIPR_ANALYZE_UUID,
    )


def test_select_command_after_init_uses_pending():
    coord = _coord(init_done=True, pending_type="mode", pending_val=3)
    assert coord._select_command(_entry()) == ("mode", 3, SYNC_CHAR_UUID)
    coord_analyze = _coord(init_done=True, pending_type="analyze", pending_val=0x01)
    assert coord_analyze._select_command(_entry()) == (
        "analyze",
        1,
        FLIPR_ANALYZE_UUID,
    )
