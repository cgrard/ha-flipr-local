# Copyright (c) 2026 Adrien40
# Copyright (c) 2026 cgrard
# This file is part of Flipr Local.

"""Sensor entity classes for Flipr Local: the coordinator-driven measurement
sensors plus the sync-mode, bluetooth-status, live-RSSI and next-analysis sensors."""

from __future__ import annotations

from datetime import datetime as dt_datetime
from typing import Any, ClassVar
import logging
import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
    RestoreSensor,
)
from homeassistant.components.bluetooth import (
    async_register_callback,
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothServiceInfoBleak,
    async_last_service_info,
    BluetoothScanningMode,
)
from homeassistant.const import EntityCategory
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import (
    CONF_CHLORINE_MODEL,
    flipr_device_info,
    DATA_ESTIMATED_FREE_CHLORINE,
    DATA_ACTIVE_CHLORINE_HOCL,
    BT_STATUS_WAITING,
    BT_STATUS_CONNECTING,
    BT_STATUS_WAKING_UP,
    BT_STATUS_REQUESTING,
    BT_STATUS_READING,
    BT_STATUS_WRITING_SYNC,
    BT_STATUS_SUCCESS,
    BT_STATUS_SYNC_APPLIED,
    BT_STATUS_ERROR,
    BT_STATUS_ERROR_RETRY,
    BT_STATUS_WRITE_FAILED,
    BT_STATUS_PAUSED,
    BT_STATUS_OUT_OF_RANGE,
)
from .entity import FliprOptionsUpdatedEntity

_LOGGER = logging.getLogger(__name__)


# Sensors whose availability depends on the selected chlorine model.
_CHLORINE_MODEL_DEPENDENT_KEYS = frozenset(
    {DATA_ESTIMATED_FREE_CHLORINE, DATA_ACTIVE_CHLORINE_HOCL}
)


class FliprSensor(FliprOptionsUpdatedEntity, CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        mac: str,
        key: str,
        device_class: SensorDeviceClass | None = None,
        unit: str | None = None,
        precision: int | None = None,
        category: EntityCategory | None = None,
        icon: str | None = None,
        model_name: str = "Flipr",
        options: list[str] | None = None,
        state_class: SensorStateClass | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{mac}_{key}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_suggested_display_precision = precision
        self._attr_entity_category = category
        self._attr_state_class = state_class
        self._attr_icon = icon
        if options:
            self._attr_options = options
        self._attr_device_info = flipr_device_info(mac, model_name)

        # FIX: only sensors that depend on the chlorine model need this attribute.
        # Other sensors initialise it to None to make the distinction explicit.
        self._chlorine_model: str | None = (
            "chlorine" if key in _CHLORINE_MODEL_DEPENDENT_KEYS else None
        )

    def _refresh_chlorine_model(self) -> None:
        """Refresh the cached chlorine model from config entry options."""
        entry = self.hass.config_entries.async_get_entry(self.coordinator.entry_id)
        if entry:
            self._chlorine_model = entry.options.get(
                CONF_CHLORINE_MODEL, entry.data.get(CONF_CHLORINE_MODEL, "chlorine")
            )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        # FIX: subscribe to the chlorine model dispatcher ONLY for sensors whose
        # availability depends on it. Subscribing all ~14 sensors was wasting memory
        # and causing unnecessary dispatcher callbacks on every options update.
        if self._key in _CHLORINE_MODEL_DEPENDENT_KEYS:
            self._refresh_chlorine_model()
            self._subscribe_options_updated()

    @callback
    def _handle_options_updated(self) -> None:
        self._refresh_chlorine_model()
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        is_avail = super().available
        if self._key in _CHLORINE_MODEL_DEPENDENT_KEYS:
            return is_avail and self._chlorine_model != "bromine"
        return is_avail

    @property
    def native_value(self) -> Any | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._key)


_SYNC_MODE_ICONS = {
    "0": "mdi:power-sleep",
    "1": "mdi:waves",
    "2": "mdi:leaf",
    "3": "mdi:rocket-launch",
}

_BT_STATUS_ICONS = {
    BT_STATUS_WAITING: "mdi:bluetooth-off",
    BT_STATUS_CONNECTING: "mdi:bluetooth-connect",
    BT_STATUS_WAKING_UP: "mdi:bluetooth-audio",
    BT_STATUS_REQUESTING: "mdi:bluetooth-transfer",
    BT_STATUS_READING: "mdi:bluetooth-transfer",
    BT_STATUS_WRITING_SYNC: "mdi:bluetooth-settings",
    BT_STATUS_SUCCESS: "mdi:bluetooth",
    BT_STATUS_SYNC_APPLIED: "mdi:bluetooth-connect",
    BT_STATUS_ERROR: "mdi:bluetooth-off",
    BT_STATUS_ERROR_RETRY: "mdi:timer-sand",
    BT_STATUS_WRITE_FAILED: "mdi:alert-circle",
    BT_STATUS_PAUSED: "mdi:pause-circle",
    BT_STATUS_OUT_OF_RANGE: "mdi:bluetooth-off",
}


class FliprSyncModeSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "sync_mode_state"
    _attr_options: ClassVar[list[str]] = ["0", "1", "2", "3"]

    def __init__(self, coordinator, mac: str, model_name: str) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"{mac}_sync_mode"
        self._attr_device_info = flipr_device_info(mac, model_name)

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        val = self.coordinator.data.get("sync_mode")
        return str(val) if val is not None else None

    @property
    def icon(self) -> str:
        return _SYNC_MODE_ICONS.get(self.native_value or "", "mdi:sync-alert")


class FliprBluetoothStatusSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "bluetooth_status"
    _attr_options: ClassVar[list[str]] = list(_BT_STATUS_ICONS)

    def __init__(self, coordinator, mac: str, model_name: str) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"{mac}_bluetooth_status"
        self._attr_device_info = flipr_device_info(mac, model_name)

    @property
    def native_value(self) -> str:
        if not self.coordinator.data:
            return BT_STATUS_WAITING
        return self.coordinator.data.get("bluetooth_status", BT_STATUS_WAITING)

    @property
    def icon(self) -> str:
        return _BT_STATUS_ICONS.get(self.native_value, "mdi:bluetooth-alert")


class FliprRealTimeRSSISensor(RestoreSensor):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = "dBm"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "rssi"
    _attr_should_poll = False

    def __init__(self, coordinator, mac: str, model_name: str) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._mac = mac
        self._attr_unique_id = f"{mac}_rssi"
        self._attr_device_info = flipr_device_info(mac, model_name)
        self._attr_native_value = None
        self._was_available = False

    @property
    def available(self) -> bool:
        # RSSI is driven by BLE advertisement callbacks, independent of the polling
        # connection state. Rely on ble_available, which already flips to False
        # immediately on signal loss (via _on_ble_unavailable), rather than the
        # bluetooth_status field: that field can stay OUT_OF_RANGE while measurements
        # are paused even though advertisements (and thus RSSI) are still arriving.
        return self._coordinator.ble_available and self._attr_native_value is not None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        last_info = async_last_service_info(self.hass, self._mac, connectable=False)
        if last_info and hasattr(last_info, "rssi"):
            self._attr_native_value = last_info.rssi
        else:
            last_sensor_data = await self.async_get_last_sensor_data()
            if last_sensor_data and last_sensor_data.native_value is not None:
                self._attr_native_value = last_sensor_data.native_value

        self._was_available = self.available
        self.async_write_ha_state()

        @callback
        def _async_on_bluetooth_change(
            info: BluetoothServiceInfoBleak, change: BluetoothChange
        ) -> None:
            self._attr_native_value = info.rssi
            self._was_available = self.available
            self.async_write_ha_state()

        self.async_on_remove(
            async_register_callback(
                self.hass,
                _async_on_bluetooth_change,
                BluetoothCallbackMatcher(address=self._mac),
                BluetoothScanningMode.PASSIVE,
            )
        )

        # RSSI values come from advertisements, but `available` also depends on the
        # coordinator's ble_available, which flips to False on signal loss with no
        # advertisement to trigger a write. Listen to the coordinator and re-write only
        # when availability actually changes, so the drop is reflected without the
        # spurious per-poll writes a naive listener would cause.
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.available != self._was_available:
            self._was_available = self.available
            self.async_write_ha_state()


class FliprNextAnalysisSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "next_analysis"
    _attr_icon = "mdi:clock-end"

    def __init__(self, coordinator, mac: str, model_name: str) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self._attr_unique_id = f"{mac}_next_analysis"
        self._attr_device_info = flipr_device_info(mac, model_name)

    @property
    def native_value(self) -> dt_datetime | None:
        if not self.coordinator.data:
            return None
        if not self.coordinator.data.get("active_measures", True):
            return None
        if self.coordinator.data.get("action_running", False):
            return None
        last = self.coordinator.data.get("last_received")
        interval = self.coordinator.update_interval
        if not last or not interval:
            return None
        if last.tzinfo is None:
            # last_received is always stored as UTC, so a naive value (e.g. legacy
            # restored data) must be tagged as UTC, not reinterpreted as local time
            # the way dt_util.as_utc would do.
            last = last.replace(tzinfo=dt_util.UTC)
        next_dt = last + interval
        if next_dt < dt_util.utcnow():
            return None
        return next_dt
