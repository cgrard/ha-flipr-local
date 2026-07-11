# Copyright (c) 2026 Adrien40
# Copyright (c) 2026 cgrard
# This file is part of Flipr Local.

from __future__ import annotations

import logging
from typing import NamedTuple

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature, EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    resolve_entry_context,
    DATA_ESTIMATED_FREE_CHLORINE,
    DATA_ACTIVE_CHLORINE_HOCL,
)
from .sensor_entities import (
    FliprSensor,
    FliprSyncModeSensor,
    FliprBluetoothStatusSensor,
    FliprRealTimeRSSISensor,
    FliprNextAnalysisSensor,
)

_LOGGER = logging.getLogger(__name__)

_M = SensorStateClass.MEASUREMENT
_D = EntityCategory.DIAGNOSTIC


class _SensorSpec(NamedTuple):
    """Declarative spec for one coordinator-driven FliprSensor."""

    key: str
    device_class: SensorDeviceClass | None = None
    unit: str | None = None
    precision: int | None = None
    category: EntityCategory | None = None
    icon: str | None = None
    options: list[str] | None = None
    state_class: SensorStateClass | None = None


# The coordinator-driven sensors, in display order. Add or tweak one here.
_SENSOR_SPECS: tuple[_SensorSpec, ...] = (
    _SensorSpec("temperature", device_class=SensorDeviceClass.TEMPERATURE, unit=UnitOfTemperature.CELSIUS, precision=2, state_class=_M),
    _SensorSpec("ph", device_class=SensorDeviceClass.PH, precision=2, state_class=_M),
    _SensorSpec("orp", unit="mV", state_class=_M),
    _SensorSpec(DATA_ESTIMATED_FREE_CHLORINE, unit="ppm", precision=2, icon="mdi:water-percent", state_class=_M),
    _SensorSpec(DATA_ACTIVE_CHLORINE_HOCL, unit="mg/L", precision=4, icon="mdi:molecule", state_class=_M),
    _SensorSpec("target_equilibrium_ph", device_class=SensorDeviceClass.PH, precision=2, category=_D, state_class=_M),
    _SensorSpec("lsi", precision=2, category=_D, state_class=_M),
    _SensorSpec("lsi_status", device_class=SensorDeviceClass.ENUM, category=_D, options=["corrosive", "balanced", "scaling", "unknown"]),
    _SensorSpec("ph_raw", unit="mV", category=_D, icon="mdi:lightning-bolt", state_class=_M),
    _SensorSpec("factory_ph", device_class=SensorDeviceClass.PH, precision=2, category=_D, icon="mdi:factory", state_class=_M),
    _SensorSpec("battery_level", device_class=SensorDeviceClass.BATTERY, unit="%", category=_D, state_class=_M),
    _SensorSpec("battery", unit="mV", category=_D, icon="mdi:battery-bluetooth", state_class=_M),
    _SensorSpec("last_received", device_class=SensorDeviceClass.TIMESTAMP, category=_D, icon="mdi:clock-check"),
    _SensorSpec("raw_frame", category=_D, icon="mdi:bluetooth-transfer"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator, mac_address, model_name = resolve_entry_context(hass, entry)

    entities = [
        FliprSensor(
            coordinator,
            mac_address,
            spec.key,
            device_class=spec.device_class,
            unit=spec.unit,
            precision=spec.precision,
            category=spec.category,
            icon=spec.icon,
            options=spec.options,
            state_class=spec.state_class,
            model_name=model_name,
        )
        for spec in _SENSOR_SPECS
    ]
    entities += [
        FliprSyncModeSensor(coordinator, mac_address, model_name),
        FliprBluetoothStatusSensor(coordinator, mac_address, model_name),
        FliprRealTimeRSSISensor(coordinator, mac_address, model_name),
        FliprNextAnalysisSensor(coordinator, mac_address, model_name),
    ]
    async_add_entities(entities)
