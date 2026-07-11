# Copyright (c) 2026 Adrien40
# Copyright (c) 2026 cgrard
# This file is part of Flipr Local.

"""Flipr Local: config entry setup, teardown and options reload."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    PLATFORMS,
    CONF_MAC_ADDRESS,
    CONF_USE_GATEWAY,
    CONF_SYNC_MODE,
    options_updated_signal,
)
from .coordinator import FliprDataCoordinator
from .helpers import format_mac_safe, get_opt, store_key

_LOGGER = logging.getLogger(__name__)

__all__ = ["FliprDataCoordinator"]


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    coordinator: FliprDataCoordinator | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )
    if not coordinator:
        return

    new_sync_mode = entry.options.get(CONF_SYNC_MODE)
    new_use_gw = get_opt(entry, CONF_USE_GATEWAY, True)

    mode_changed = new_sync_mode != coordinator.last_configured_sync_mode
    gw_changed = new_use_gw != coordinator.last_configured_use_gw

    coordinator.last_configured_sync_mode = new_sync_mode
    coordinator.last_configured_use_gw = new_use_gw

    coordinator.recompute_derived_values()

    async_dispatcher_send(hass, options_updated_signal(coordinator.mac))

    if (mode_changed or gw_changed) and new_use_gw and new_sync_mode is not None:
        coordinator.set_pending_cmd("mode", int(new_sync_mode))
        coordinator.request_one_shot_analysis()
        if coordinator.is_shutdown:
            _LOGGER.debug(
                "Skipping sync mode refresh for %s: coordinator is shutting down",
                coordinator.safe_mac,
            )
            return
        if not coordinator.ble_lock.locked():
            entry.async_create_background_task(
                hass,
                coordinator.async_request_refresh(),
                "flipr_sync_mode_refresh",
            )
        else:
            _LOGGER.debug(
                "BLE lock already held for %s - sync mode refresh will apply on next cycle",
                coordinator.safe_mac,
            )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    mac = entry.data[CONF_MAC_ADDRESS]
    safe_mac = format_mac_safe(mac)

    coordinator = FliprDataCoordinator(hass, entry, mac, safe_mac)
    await coordinator.async_initialize()

    hass.data[DOMAIN][entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if coordinator.data.get("ph_raw"):
        _LOGGER.debug("History restored from disk; refreshing for current data.")
    else:
        _LOGGER.debug("No history found, launching initial analysis.")
    # Always trigger an initial read after (re)start. Restored history gives an
    # instant display, but without this the coordinator would otherwise wait a
    # full update_interval before its first live read. If Bluetooth is not ready
    # yet, this goes out_of_range and _on_ble_seen retries once the sensor is up.
    entry.async_create_background_task(
        hass,
        coordinator.async_request_refresh(),
        "flipr_initial_refresh",
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if ok:
        coordinator: FliprDataCoordinator | None = hass.data[DOMAIN].get(entry.entry_id)
        if coordinator:
            await coordinator.async_shutdown()
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    mac = entry.data.get(CONF_MAC_ADDRESS)
    if mac:
        store = Store(hass, 1, store_key(mac))
        await store.async_remove()
