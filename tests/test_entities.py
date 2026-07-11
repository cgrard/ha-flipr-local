# Copyright (c) 2026 Adrien40
# Copyright (c) 2026 cgrard
# This file is part of Flipr Local.

from datetime import timedelta
from types import SimpleNamespace

import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature, EntityCategory

from custom_components.flipr_local import (
    binary_sensor,
    button,
    number,
    select,
    sensor,
    switch,
)
from custom_components.flipr_local.const import (
    BT_STATUS_OUT_OF_RANGE,
    BT_STATUS_WAITING,
    CONF_CYA,
    CONF_MAC_ADDRESS,
    CONF_MODEL,
    CONF_TAC,
    DATA_ACTIVE_CHLORINE_HOCL,
    DATA_ESTIMATED_FREE_CHLORINE,
    DOMAIN,
)

MAC = "AA:BB:CC:DD:EE:FF"


def make_coordinator(data=None, *, ble_available=True, interval=timedelta(minutes=60)):
    return SimpleNamespace(
        data={} if data is None else data,
        last_update_success=True,
        ble_available=ble_available,
        update_interval=interval,
        entry_id="e1",
        safe_mac=MAC,
    )


def _hass(coordinator):
    return SimpleNamespace(data={DOMAIN: {"e1": coordinator}})


def _entry():
    return SimpleNamespace(
        entry_id="e1",
        data={CONF_MAC_ADDRESS: MAC, CONF_MODEL: "Flipr AnalysR 3"},
        title="Flipr AnalysR 3",
    )


async def _setup(setup_fn, coordinator):
    added = []
    await setup_fn(_hass(coordinator), _entry(), lambda items: added.extend(items))
    return added


# ==========================================
# async_setup_entry creates the right entities
# ==========================================


async def test_setup_entities_per_platform():
    coord = make_coordinator()
    assert len(await _setup(sensor.async_setup_entry, coord)) >= 15
    assert len(await _setup(number.async_setup_entry, coord)) == 5
    assert len(await _setup(binary_sensor.async_setup_entry, coord)) == 3
    assert len(await _setup(select.async_setup_entry, coord)) == 1
    assert len(await _setup(switch.async_setup_entry, coord)) == 1
    assert len(await _setup(button.async_setup_entry, coord)) == 1


_M = SensorStateClass.MEASUREMENT
_D = EntityCategory.DIAGNOSTIC

# (device_class, unit, precision, category, icon, state_class, options) per FliprSensor.
# Snapshot of what async_setup_entry builds; guards the declarative-table refactor.
_EXPECTED_FLIPR_SENSORS = {
    "temperature": (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, 2, None, None, _M, None),
    "ph": (SensorDeviceClass.PH, None, 2, None, None, _M, None),
    "orp": (None, "mV", None, None, None, _M, None),
    DATA_ESTIMATED_FREE_CHLORINE: (None, "ppm", 2, None, "mdi:water-percent", _M, None),
    DATA_ACTIVE_CHLORINE_HOCL: (None, "mg/L", 4, None, "mdi:molecule", _M, None),
    "target_equilibrium_ph": (SensorDeviceClass.PH, None, 2, _D, None, _M, None),
    "lsi": (None, None, 2, _D, None, _M, None),
    "lsi_status": (
        SensorDeviceClass.ENUM, None, None, _D, None, None,
        ["corrosive", "balanced", "scaling", "unknown"],
    ),
    "ph_raw": (None, "mV", None, _D, "mdi:lightning-bolt", _M, None),
    "factory_ph": (SensorDeviceClass.PH, None, 2, _D, "mdi:factory", _M, None),
    "battery_level": (SensorDeviceClass.BATTERY, "%", None, _D, None, _M, None),
    "battery": (None, "mV", None, _D, "mdi:battery-bluetooth", _M, None),
    "last_received": (SensorDeviceClass.TIMESTAMP, None, None, _D, "mdi:clock-check", None, None),
    "raw_frame": (None, None, None, _D, "mdi:bluetooth-transfer", None, None),
}


async def test_flipr_sensor_specs_match_expected():
    """Every FliprSensor from async_setup_entry has the exact expected attributes.

    Snapshot of the pre-refactor behaviour; guards the declarative spec table.
    """
    added = await _setup(sensor.async_setup_entry, make_coordinator())
    got = {
        e._attr_translation_key: (
            e._attr_device_class,
            e._attr_native_unit_of_measurement,
            e._attr_suggested_display_precision,
            e._attr_entity_category,
            e._attr_icon,
            e._attr_state_class,
            getattr(e, "_attr_options", None),
        )
        for e in added
        if isinstance(e, sensor.FliprSensor)
    }
    assert got == _EXPECTED_FLIPR_SENSORS


# ==========================================
# Sensors
# ==========================================


def test_flipr_sensor_native_value():
    s = sensor.FliprSensor(make_coordinator({"ph": 7.2}), MAC, "ph", model_name="X")
    assert s.native_value == 7.2
    assert s.available is True
    assert sensor.FliprSensor(make_coordinator({}), MAC, "ph").native_value is None


def test_flipr_sensor_chlorine_gating():
    s = sensor.FliprSensor(
        make_coordinator({DATA_ESTIMATED_FREE_CHLORINE: 1.0}),
        MAC,
        DATA_ESTIMATED_FREE_CHLORINE,
        model_name="X",
    )
    assert s.available is True
    s._chlorine_model = "bromine"
    assert s.available is False


def test_sync_mode_sensor():
    s = sensor.FliprSyncModeSensor(make_coordinator({"sync_mode": "2"}), MAC, "X")
    assert s.native_value == "2"
    assert s.icon == "mdi:leaf"
    assert (
        sensor.FliprSyncModeSensor(make_coordinator({}), MAC, "X").native_value is None
    )
    assert (
        sensor.FliprSyncModeSensor(make_coordinator({}), MAC, "X").icon
        == "mdi:sync-alert"
    )


def test_bluetooth_status_sensor():
    s = sensor.FliprBluetoothStatusSensor(
        make_coordinator({"bluetooth_status": BT_STATUS_OUT_OF_RANGE}), MAC, "X"
    )
    assert s.native_value == BT_STATUS_OUT_OF_RANGE
    assert s.icon == "mdi:bluetooth-off"
    fresh = sensor.FliprBluetoothStatusSensor(make_coordinator({}), MAC, "X")
    assert fresh.native_value == BT_STATUS_WAITING


def test_rssi_sensor_availability():
    s = sensor.FliprRealTimeRSSISensor(make_coordinator({}), MAC, "X")
    assert s.available is False  # no value yet
    s._attr_native_value = -60
    assert s.available is True
    # Driven by ble_available, not by a stale bluetooth_status: no signal -> off.
    no_signal = sensor.FliprRealTimeRSSISensor(
        make_coordinator({}, ble_available=False), MAC, "X"
    )
    no_signal._attr_native_value = -60
    assert no_signal.available is False


def test_rssi_sensor_writes_only_on_availability_change():
    """The coordinator listener re-writes on a signal drop, not on every poll."""
    coord = make_coordinator({}, ble_available=True)
    s = sensor.FliprRealTimeRSSISensor(coord, MAC, "X")
    s._attr_native_value = -60
    s._was_available = True
    writes = []
    s.async_write_ha_state = lambda: writes.append(1)

    s._handle_coordinator_update()  # nothing changed -> no spurious write
    assert writes == []

    coord.ble_available = False  # signal lost -> availability flips -> one write
    s._handle_coordinator_update()
    assert writes == [1]
    assert s.available is False and s._was_available is False


def test_next_analysis_sensor():
    now = dt_util.utcnow()
    coord = make_coordinator(
        {"last_received": now, "active_measures": True, "action_running": False}
    )
    nv = sensor.FliprNextAnalysisSensor(coord, MAC, "X").native_value
    assert nv is not None and nv > now
    paused = make_coordinator({"last_received": now, "active_measures": False})
    assert sensor.FliprNextAnalysisSensor(paused, MAC, "X").native_value is None


# ==========================================
# Binary sensors
# ==========================================


def test_alert_sensor_thresholds():
    high = binary_sensor.FliprAlertSensor(
        make_coordinator({"ph": 8.0}), "e1", MAC, "X", "ph_status", "ph"
    )
    assert high.is_on is True  # above default max 7.50
    ok = binary_sensor.FliprAlertSensor(
        make_coordinator({"ph": 7.2}), "e1", MAC, "X", "ph_status", "ph"
    )
    assert ok.is_on is False
    missing = binary_sensor.FliprAlertSensor(
        make_coordinator({}), "e1", MAC, "X", "ph_status", "ph"
    )
    assert missing.is_on is None


# ==========================================
# Select, switch, number
# ==========================================


def test_model_select():
    s = select.FliprModelSelect(make_coordinator({}), "e1", MAC, "X")
    assert s.current_option == "chlorine"
    assert s.available is True


def test_active_measures_switch():
    on = switch.FliprActiveMeasuresSwitch(
        make_coordinator({"active_measures": True}), MAC, "X"
    )
    off = switch.FliprActiveMeasuresSwitch(
        make_coordinator({"active_measures": False}), MAC, "X"
    )
    default = switch.FliprActiveMeasuresSwitch(make_coordinator({}), MAC, "X")
    assert on.is_on is True
    assert off.is_on is False
    assert default.is_on is True


def test_water_config_number_cya_availability():
    cya = number.FliprWaterConfigNumber(
        make_coordinator({}), MAC, CONF_CYA, 0, 150, 1, 0, "mdi:x", "e1", "X", "mg/L"
    )
    assert cya.available is True
    cya._chlorine_model = "bromine"
    assert cya.available is False  # CyA hidden in bromine mode

    tac = number.FliprWaterConfigNumber(
        make_coordinator({}), MAC, CONF_TAC, 0, 500, 1, 0, "mdi:x", "e1", "X", "mg/L"
    )
    tac._chlorine_model = "bromine"
    assert tac.available is True  # other water params stay available
