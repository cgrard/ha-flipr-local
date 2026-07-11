# Copyright (c) 2026 Adrien40
# Copyright (c) 2026 cgrard
# This file is part of Flipr Local.

from __future__ import annotations

import logging
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


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator, mac_address, model_name = resolve_entry_context(hass, entry)

    async_add_entities(
        [
            FliprSensor(
                coordinator,
                mac_address,
                "temperature",
                SensorDeviceClass.TEMPERATURE,
                UnitOfTemperature.CELSIUS,
                2,
                model_name=model_name,
                state_class=SensorStateClass.MEASUREMENT,
            ),
            FliprSensor(
                coordinator,
                mac_address,
                "ph",
                SensorDeviceClass.PH,
                None,
                2,
                model_name=model_name,
                state_class=SensorStateClass.MEASUREMENT,
            ),
            FliprSensor(
                coordinator,
                mac_address,
                "orp",
                None,
                "mV",
                model_name=model_name,
                state_class=SensorStateClass.MEASUREMENT,
            ),
            FliprSensor(
                coordinator,
                mac_address,
                DATA_ESTIMATED_FREE_CHLORINE,
                None,
                "ppm",
                2,
                model_name=model_name,
                state_class=SensorStateClass.MEASUREMENT,
                icon="mdi:water-percent",
            ),
            FliprSensor(
                coordinator,
                mac_address,
                DATA_ACTIVE_CHLORINE_HOCL,
                None,
                "mg/L",
                4,
                model_name=model_name,
                state_class=SensorStateClass.MEASUREMENT,
                icon="mdi:molecule",
            ),
            FliprSensor(
                coordinator,
                mac_address,
                "target_equilibrium_ph",
                SensorDeviceClass.PH,
                None,
                2,
                category=EntityCategory.DIAGNOSTIC,
                model_name=model_name,
                state_class=SensorStateClass.MEASUREMENT,
            ),
            FliprSensor(
                coordinator,
                mac_address,
                "lsi",
                None,
                None,
                2,
                category=EntityCategory.DIAGNOSTIC,
                model_name=model_name,
                state_class=SensorStateClass.MEASUREMENT,
            ),
            FliprSensor(
                coordinator,
                mac_address,
                "lsi_status",
                SensorDeviceClass.ENUM,
                None,
                category=EntityCategory.DIAGNOSTIC,
                model_name=model_name,
                options=["corrosive", "balanced", "scaling", "unknown"],
            ),
            FliprSensor(
                coordinator,
                mac_address,
                "ph_raw",
                None,
                "mV",
                category=EntityCategory.DIAGNOSTIC,
                icon="mdi:lightning-bolt",
                model_name=model_name,
                state_class=SensorStateClass.MEASUREMENT,
            ),
            FliprSensor(
                coordinator,
                mac_address,
                "factory_ph",
                SensorDeviceClass.PH,
                None,
                2,
                category=EntityCategory.DIAGNOSTIC,
                icon="mdi:factory",
                model_name=model_name,
                state_class=SensorStateClass.MEASUREMENT,
            ),
            FliprSensor(
                coordinator,
                mac_address,
                "battery_level",
                SensorDeviceClass.BATTERY,
                "%",
                category=EntityCategory.DIAGNOSTIC,
                model_name=model_name,
                state_class=SensorStateClass.MEASUREMENT,
            ),
            FliprSensor(
                coordinator,
                mac_address,
                "battery",
                None,
                "mV",
                category=EntityCategory.DIAGNOSTIC,
                icon="mdi:battery-bluetooth",
                model_name=model_name,
                state_class=SensorStateClass.MEASUREMENT,
            ),
            FliprSensor(
                coordinator,
                mac_address,
                "last_received",
                SensorDeviceClass.TIMESTAMP,
                None,
                category=EntityCategory.DIAGNOSTIC,
                icon="mdi:clock-check",
                model_name=model_name,
            ),
            FliprSensor(
                coordinator,
                mac_address,
                "raw_frame",
                None,
                None,
                category=EntityCategory.DIAGNOSTIC,
                icon="mdi:bluetooth-transfer",
                model_name=model_name,
            ),
            FliprSyncModeSensor(coordinator, mac_address, model_name),
            FliprBluetoothStatusSensor(coordinator, mac_address, model_name),
            FliprRealTimeRSSISensor(coordinator, mac_address, model_name),
            FliprNextAnalysisSensor(coordinator, mac_address, model_name),
        ]
    )


