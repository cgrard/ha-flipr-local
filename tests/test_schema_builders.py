# Copyright (c) 2026 Adrien40
# This file is part of Flipr Local.

from custom_components.flipr_local.config_flow import (
    NUM_FIELDS,
    PROBE_FIELDS,
    THRESHOLD_FIELDS,
    _num_section,
    _number,
)


def test_num_fields_covers_every_section_field():
    for field in (*PROBE_FIELDS, *THRESHOLD_FIELDS):
        assert field in NUM_FIELDS


def test_number_selector_uses_table_bounds():
    for field, (min_val, max_val, step) in NUM_FIELDS.items():
        config = dict(_number(field).config)
        assert config["min"] == min_val
        assert config["max"] == max_val
        assert config["step"] == step
        assert config["mode"] == "box"


def test_num_section_preserves_field_order_and_defaults():
    defaults = {field: float(i) for i, field in enumerate(PROBE_FIELDS)}
    sec = _num_section(PROBE_FIELDS, defaults, collapsed=True)

    markers = list(sec.schema.schema)
    assert [m.schema for m in markers] == list(PROBE_FIELDS)
    for marker in markers:
        assert marker.default() == defaults[marker.schema]


def test_num_section_collapsed_flag_is_passed_through():
    expanded = _num_section(
        THRESHOLD_FIELDS, dict.fromkeys(THRESHOLD_FIELDS, 0), collapsed=False
    )
    collapsed = _num_section(
        THRESHOLD_FIELDS, dict.fromkeys(THRESHOLD_FIELDS, 0), collapsed=True
    )
    assert expanded.options == {"collapsed": False}
    assert collapsed.options == {"collapsed": True}
