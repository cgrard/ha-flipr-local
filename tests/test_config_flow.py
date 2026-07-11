# Copyright (c) 2026 Adrien40
# Copyright (c) 2026 cgrard
# This file is part of Flipr Local.

from custom_components.flipr_local.flow_schema import (
    _flatten_sections,
    validate_calibration,
)
from custom_components.flipr_local.const import (
    CONF_ORP_MAX,
    CONF_ORP_MIN,
    CONF_PH_CALIB_4,
    CONF_PH_CALIB_7,
    CONF_PH_MAX,
    CONF_PH_MIN,
    CONF_PH_REF_4,
    CONF_PH_REF_7,
    CONF_TEMP_MAX,
    CONF_TEMP_MIN,
)

# A calibration payload that passes every check (negative-slope probe: the pH 7
# buffer reads a lower mV than the pH 4 buffer).
VALID = {
    CONF_PH_CALIB_7: 8.40,
    CONF_PH_REF_7: 7.02,
    CONF_PH_CALIB_4: 6.02,
    CONF_PH_REF_4: 4.00,
}


# ==========================================
# _flatten_sections
# ==========================================


def test_flatten_merges_sections_and_top_level():
    flat = _flatten_sections(
        {"mac_address": "AA:BB", "general": {"cya": 40, "use_gateway": True}}
    )
    assert flat == {"mac_address": "AA:BB", "cya": 40, "use_gateway": True}


def test_flatten_section_value_wins_over_top_level_scalar():
    # On a key collision, the section (dict) value takes priority.
    flat = _flatten_sections({"x": 1, "section": {"x": 2}})
    assert flat["x"] == 2


# ==========================================
# validate_calibration - happy path
# ==========================================


def test_valid_calibration_returns_normalized_dict():
    result = validate_calibration(dict(VALID))
    assert isinstance(result, dict)
    assert result[CONF_PH_REF_7] == 7.02
    assert result[CONF_PH_CALIB_4] == 6.02


def test_comma_decimals_are_accepted():
    data = dict(VALID)
    data[CONF_PH_REF_7] = "7,02"  # French-style decimal separator
    result = validate_calibration(data)
    assert isinstance(result, dict)
    assert result[CONF_PH_REF_7] == 7.02


# ==========================================
# validate_calibration - error attribution
# ==========================================


def test_parse_error_is_attributed_to_the_failing_field():
    # A non-numeric ph_ref_7 must blame ph_ref_7, not ph_calib_4.
    data = dict(VALID)
    data[CONF_PH_REF_7] = "not-a-number"
    assert validate_calibration(data) == (CONF_PH_REF_7, "unknown")


def test_ph_threshold_order_error():
    data = {**VALID, CONF_PH_MIN: 7.5, CONF_PH_MAX: 6.9}
    assert validate_calibration(data) == (CONF_PH_MIN, "ph_threshold_error")


def test_temp_threshold_order_error():
    data = {**VALID, CONF_TEMP_MIN: 30, CONF_TEMP_MAX: 10}
    assert validate_calibration(data) == (CONF_TEMP_MIN, "temp_threshold_error")


def test_orp_threshold_order_error():
    data = {**VALID, CONF_ORP_MIN: 800, CONF_ORP_MAX: 650}
    assert validate_calibration(data) == (CONF_ORP_MIN, "orp_threshold_error")


def test_ph_reference_out_of_range():
    data = dict(VALID)
    data[CONF_PH_REF_4] = 6.0  # outside the pH 4 buffer window (2.5-5.5)
    assert validate_calibration(data) == (CONF_PH_REF_4, "ph_ref_out_of_range")


def test_equal_calibration_values_rejected():
    data = dict(VALID)
    data[CONF_PH_CALIB_4] = 8.40  # same as ph_calib_7 -> identical mV
    assert validate_calibration(data) == (CONF_PH_CALIB_7, "ph_calibration_equal")


def test_slope_mismatch_rejected():
    # Swap the two calibration points so pH 7 reads a higher mV than pH 4.
    data = dict(VALID)
    data[CONF_PH_CALIB_7] = 6.02
    data[CONF_PH_CALIB_4] = 8.40
    assert validate_calibration(data) == (CONF_PH_CALIB_7, "ph_slope_mismatch")


def test_mv_out_of_range_rejected():
    data = dict(VALID)
    data[CONF_PH_CALIB_7] = 4000  # neither a plausible pH nor a 500-3000 mV value
    assert validate_calibration(data) == (CONF_PH_CALIB_7, "ph_mv_out_of_range")
