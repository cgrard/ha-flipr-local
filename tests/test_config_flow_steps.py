# Copyright (c) 2026 Adrien40
# Copyright (c) 2026 cgrard
# This file is part of Flipr Local.

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.flipr_local.config_flow as config_flow
from custom_components.flipr_local.config_flow import FliprConfigFlow
from custom_components.flipr_local.const import (
    CONF_CHLORINE_MODEL,
    CONF_CYA,
    CONF_MAC_ADDRESS,
    CONF_MODEL,
    CONF_ORP_CALIB,
    CONF_ORP_REF,
    CONF_PH_CALIB_4,
    CONF_PH_CALIB_7,
    CONF_PH_MAX,
    CONF_PH_MIN,
    CONF_PH_REF_4,
    CONF_PH_REF_7,
    CONF_ORP_MAX,
    CONF_ORP_MIN,
    CONF_SYNC_MODE,
    CONF_TEMP_MAX,
    CONF_TEMP_MIN,
    CONF_TEMP_OFFSET,
    CONF_USE_GATEWAY,
    DOMAIN,
)

MAC = "AA:BB:CC:DD:EE:FF"

VALID_SECTIONS = {
    "general": {CONF_USE_GATEWAY: True, CONF_CHLORINE_MODEL: "chlorine", CONF_CYA: 40},
    "probes_calibration": {
        CONF_PH_CALIB_7: 8.40,
        CONF_PH_REF_7: 7.02,
        CONF_PH_CALIB_4: 6.02,
        CONF_PH_REF_4: 4.00,
        CONF_ORP_CALIB: 650,
        CONF_ORP_REF: 650,
        CONF_TEMP_OFFSET: 0.0,
    },
}


@pytest.fixture(autouse=True)
def _no_bluetooth_discovery(monkeypatch):
    monkeypatch.setattr(
        config_flow, "async_discovered_service_info", lambda *a, **k: []
    )


def _flow(hass):
    flow = FliprConfigFlow()
    flow.hass = hass
    flow.context = {}
    return flow


async def test_user_step_shows_form(hass):
    result = await _flow(hass).async_step_user()
    assert result["type"] == "form"
    assert result["step_id"] == "user"


async def test_user_step_creates_entry(hass):
    user_input = {CONF_MAC_ADDRESS: MAC, **VALID_SECTIONS}
    result = await _flow(hass).async_step_user(user_input)
    assert result["type"] == "create_entry"
    assert result["data"][CONF_MAC_ADDRESS] == MAC
    # No discovered device name -> the model falls back to the generic "Flipr".
    assert result["data"][CONF_MODEL] == "Flipr"
    # The calibration values are normalised into the entry options.
    assert result["options"][CONF_PH_REF_7] == 7.02


async def test_user_step_invalid_mac(hass):
    user_input = {CONF_MAC_ADDRESS: "not-a-mac", **VALID_SECTIONS}
    result = await _flow(hass).async_step_user(user_input)
    assert result["type"] == "form"
    assert result["errors"].get(CONF_MAC_ADDRESS) == "invalid_mac"


async def test_user_step_calibration_error(hass):
    bad = {
        CONF_MAC_ADDRESS: MAC,
        "general": VALID_SECTIONS["general"],
        "probes_calibration": {
            **VALID_SECTIONS["probes_calibration"],
            CONF_PH_REF_4: 6.0,  # outside the pH 4 buffer window
        },
    }
    result = await _flow(hass).async_step_user(bad)
    assert result["type"] == "form"
    assert result["errors"]


async def test_manual_step_resumes_user_form(hass):
    result = await _flow(hass).async_step_manual({CONF_MAC_ADDRESS: MAC})
    assert result["type"] == "form"


async def test_manual_step_invalid_mac(hass):
    result = await _flow(hass).async_step_manual({CONF_MAC_ADDRESS: "bad"})
    assert result["type"] == "form"
    assert result["step_id"] == "manual"
    assert result["errors"].get(CONF_MAC_ADDRESS) == "invalid_mac"


def _options_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MAC_ADDRESS: MAC, CONF_MODEL: "Flipr AnalysR 3"},
        options={},
        title="Flipr AnalysR 3",
    )
    entry.add_to_hass(hass)
    return entry


def _options_input(sync_mode):
    return {
        "general": {
            CONF_USE_GATEWAY: True,
            CONF_SYNC_MODE: sync_mode,
            CONF_CHLORINE_MODEL: "chlorine",
            CONF_CYA: 40,
        },
        "probes_calibration": VALID_SECTIONS["probes_calibration"],
        "alert_thresholds": {
            CONF_PH_MIN: 6.90,
            CONF_PH_MAX: 7.50,
            CONF_ORP_MIN: 650,
            CONF_ORP_MAX: 800,
            CONF_TEMP_MIN: 6.0,
            CONF_TEMP_MAX: 32.0,
        },
    }


async def test_options_init_shows_form(hass):
    entry = _options_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    assert result["step_id"] == "init"


async def test_options_submit_eco_saves(hass):
    entry = _options_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        _options_input("2"),  # Eco mode -> no battery warning
    )
    assert result2["type"] == "create_entry"


async def test_options_submit_high_sync_mode_warns(hass):
    entry = _options_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        _options_input("1"),  # Normal mode + gateway -> warning step
    )
    assert result2["type"] == "form"
    assert result2["step_id"] == "warning"
