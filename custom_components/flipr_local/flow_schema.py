# Copyright (c) 2026 Adrien40
# Copyright (c) 2026 cgrard
# This file is part of Flipr Local.

"""Schema builders (number/dropdown selectors, sections) and input validation
shared by the Flipr Local config and options flows."""

import math
import voluptuous as vol

from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .chemistry import get_mv_from_input
from .const import (
    CONF_CYA,
    CONF_ORP_CALIB,
    CONF_ORP_MAX,
    CONF_ORP_MIN,
    CONF_ORP_REF,
    CONF_PH_CALIB_4,
    CONF_PH_CALIB_7,
    CONF_PH_MAX,
    CONF_PH_MIN,
    CONF_PH_REF_4,
    CONF_PH_REF_7,
    CONF_TEMP_MAX,
    CONF_TEMP_MIN,
    CONF_TEMP_OFFSET,
    DEFAULT_PH_CALIB_4,
    DEFAULT_PH_CALIB_7,
    DEFAULT_PH_REF_4,
    DEFAULT_PH_REF_7,
)


# Bounds (min, max, step) for every BOX number field, shared by the config and
# options flows so the two cannot drift apart.
NUM_FIELDS: dict[str, tuple[float, float, float]] = {
    CONF_CYA: (0, 150, 1),
    CONF_PH_CALIB_7: (0, 3000, 0.01),
    CONF_PH_REF_7: (0, 14, 0.01),
    CONF_PH_CALIB_4: (0, 3000, 0.01),
    CONF_PH_REF_4: (0, 14, 0.01),
    CONF_ORP_CALIB: (0, 1000, 1),
    CONF_ORP_REF: (0, 1000, 1),
    CONF_TEMP_OFFSET: (-5.0, 5.0, 0.1),
    CONF_PH_MIN: (0, 14, 0.01),
    CONF_PH_MAX: (0, 14, 0.01),
    CONF_ORP_MIN: (0, 1200, 1),
    CONF_ORP_MAX: (0, 1200, 1),
    CONF_TEMP_MIN: (0, 50, 0.5),
    CONF_TEMP_MAX: (0, 50, 0.5),
}

# The numeric sections, in display order.
PROBE_FIELDS = (
    CONF_PH_CALIB_7,
    CONF_PH_REF_7,
    CONF_PH_CALIB_4,
    CONF_PH_REF_4,
    CONF_ORP_CALIB,
    CONF_ORP_REF,
    CONF_TEMP_OFFSET,
)
THRESHOLD_FIELDS = (
    CONF_PH_MIN,
    CONF_PH_MAX,
    CONF_ORP_MIN,
    CONF_ORP_MAX,
    CONF_TEMP_MIN,
    CONF_TEMP_MAX,
)


def _number(field: str) -> selector.NumberSelector:
    """A BOX number selector for `field`, using the shared NUM_FIELDS bounds."""
    min_val, max_val, step = NUM_FIELDS[field]
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=min_val,
            max=max_val,
            step=step,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _dropdown(options: list[str], translation_key: str) -> selector.SelectSelector:
    """A DROPDOWN select selector with the given options and translation key."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key=translation_key,
            sort=False,
        )
    )


def _num_section(fields, defaults: dict, *, collapsed: bool):
    """Build a collapsible section of BOX number fields from a defaults dict."""
    return section(
        vol.Schema({vol.Required(f, default=defaults[f]): _number(f) for f in fields}),
        {"collapsed": collapsed},
    )


def _to_float(val: object) -> float:
    if isinstance(val, str):
        val = val.replace(",", ".")
    result = float(val)
    if math.isnan(result) or math.isinf(result):
        raise ValueError("NaN/Inf is not a valid calibration value")
    return result


def _flatten_sections(user_input: dict) -> dict:
    """Merge section (dict) values into a flat dict.

    FIX: Unified helper used by both async_step_user and async_step_init.
    Section (dict) values take priority over any same-named top-level keys,
    since section values are more specific. This was previously inconsistent:
    - async_step_user: top-level keys written first, dicts could overwrite them.
    - async_step_init: dicts written first, top-level keys used setdefault (no override).
    Both forms now follow the same rule: dict/section values win.
    """
    flat: dict = {}
    # Pass 1: collect all section (dict) values.
    for value in user_input.values():
        if isinstance(value, dict):
            flat.update(value)
    # Pass 2: add top-level scalars only if the key wasn't already set by a section.
    for k, v in user_input.items():
        if not isinstance(v, dict):
            flat.setdefault(k, v)
    return flat


def _check_min_max(
    data: dict, key_min: str, key_max: str, error_key: str, cast=float
) -> tuple[str, str] | None:
    """Validate that data[key_min] < data[key_max] when both are present."""
    if key_min not in data or key_max not in data:
        return None
    try:
        lo = cast(_to_float(data[key_min]))
        hi = cast(_to_float(data[key_max]))
    except (ValueError, TypeError):
        return (key_min, "unknown")
    if lo >= hi:
        return (key_min, error_key)
    return None


def _validate_ph_relationship(
    raw_c4: float, raw_c7: float, ref4: float, ref7: float
) -> tuple[str, str] | None:
    """Check the pH calibration mV conversion, reference ranges and slope."""
    try:
        c4_mv = get_mv_from_input(raw_c4)
    except ValueError:
        return (CONF_PH_CALIB_4, "ph_mv_out_of_range")

    try:
        c7_mv = get_mv_from_input(raw_c7)
    except ValueError:
        return (CONF_PH_CALIB_7, "ph_mv_out_of_range")

    if ref4 < 2.5 or ref4 > 5.5 or ref7 < 6.5 or ref7 > 7.5:
        return (CONF_PH_REF_4, "ph_ref_out_of_range")
    if abs(c7_mv - c4_mv) < 1.0:
        return (CONF_PH_CALIB_7, "ph_calibration_equal")
    if abs(ref7 - ref4) < 0.01:
        return (CONF_PH_REF_7, "ph_reference_equal")
    if c7_mv > c4_mv:
        return (CONF_PH_CALIB_7, "ph_slope_mismatch")
    return None


def _normalize_calibration(
    data: dict, raw_c4: float, raw_c7: float, ref4: float, ref7: float
) -> dict:
    """Return a copy of `data` with the calibration values coerced to numbers."""
    normalized = dict(data)
    normalized[CONF_PH_CALIB_4] = raw_c4
    normalized[CONF_PH_CALIB_7] = raw_c7
    normalized[CONF_PH_REF_4] = ref4
    normalized[CONF_PH_REF_7] = ref7

    if CONF_ORP_REF in data:
        normalized[CONF_ORP_REF] = int(_to_float(data[CONF_ORP_REF]))
    if CONF_ORP_CALIB in data:
        normalized[CONF_ORP_CALIB] = int(_to_float(data[CONF_ORP_CALIB]))
    if CONF_TEMP_OFFSET in data:
        normalized[CONF_TEMP_OFFSET] = float(_to_float(data[CONF_TEMP_OFFSET]))
    if CONF_CYA in data:
        normalized[CONF_CYA] = int(_to_float(data[CONF_CYA]))

    return normalized


def validate_calibration(data: dict) -> dict | tuple[str, str]:
    # Parse each pH field individually so a parsing error is attributed to the
    # field that actually failed, instead of always blaming ph_calib_4.
    ph_field_defaults = (
        (CONF_PH_CALIB_4, DEFAULT_PH_CALIB_4),
        (CONF_PH_CALIB_7, DEFAULT_PH_CALIB_7),
        (CONF_PH_REF_4, DEFAULT_PH_REF_4),
        (CONF_PH_REF_7, DEFAULT_PH_REF_7),
    )
    parsed_ph: dict[str, float] = {}
    for field, default in ph_field_defaults:
        try:
            parsed_ph[field] = _to_float(data.get(field, default))
        except (ValueError, TypeError):
            return (field, "unknown")
    raw_c4 = parsed_ph[CONF_PH_CALIB_4]
    raw_c7 = parsed_ph[CONF_PH_CALIB_7]
    ref4 = parsed_ph[CONF_PH_REF_4]
    ref7 = parsed_ph[CONF_PH_REF_7]

    for key_min, key_max, error_key, cast in (
        (CONF_PH_MIN, CONF_PH_MAX, "ph_threshold_error", float),
        (CONF_TEMP_MIN, CONF_TEMP_MAX, "temp_threshold_error", float),
        (CONF_ORP_MIN, CONF_ORP_MAX, "orp_threshold_error", float),
    ):
        threshold_error = _check_min_max(data, key_min, key_max, error_key, cast)
        if threshold_error is not None:
            return threshold_error

    relationship_error = _validate_ph_relationship(raw_c4, raw_c7, ref4, ref7)
    if relationship_error is not None:
        return relationship_error

    return _normalize_calibration(data, raw_c4, raw_c7, ref4, ref7)
