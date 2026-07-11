# Copyright (c) 2026 Adrien40
# Copyright (c) 2026 cgrard
# This file is part of Flipr Local.

"""Flipr Local data coordinator: BLE read cycle, frame parsing, derived-value
computation and on-disk persistence for a single Flipr sensor."""

import logging
import asyncio
from typing import Any
import homeassistant.util.dt as dt_util
from time import monotonic
from homeassistant.components.bluetooth import (
    async_ble_device_from_address,
    async_last_service_info,
    async_scanner_count,
    async_register_callback,
    async_track_unavailable,
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothServiceInfoBleak,
    BluetoothScanningMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, CALLBACK_TYPE
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_call_later

from .ble import FliprBleMixin
from .parser import FliprParseMixin
from .helpers import get_opt, store_key
from .const import (
    CONF_USE_GATEWAY,
    CONF_SYNC_MODE,
    FLIPR_ANALYZE_UUID,
    SYNC_CHAR_UUID,
    DEFAULT_UPDATE_INTERVAL,
    SAVE_DEBOUNCE_DELAY,
    DEBOUNCE_COOLDOWN,
    EXPECTED_FRAME_HEX_LEN,
    BT_STATUS_WAITING,
    BT_STATUS_ERROR,
    BT_STATUS_ERROR_RETRY,
    BT_STATUS_WRITE_FAILED,
    BT_STATUS_PAUSED,
    BT_STATUS_OUT_OF_RANGE,
    BLE_RECENTLY_SEEN_THRESHOLD_S,
    get_flipr_model,
)

_LOGGER = logging.getLogger(__name__)


class FliprDataCoordinator(FliprBleMixin, FliprParseMixin, DataUpdateCoordinator):
    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, mac: str, safe_mac: str
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Flipr {safe_mac}",
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self._entry_id = entry.entry_id
        self.mac = mac
        self.safe_mac = safe_mac
        self.store = Store(hass, 1, store_key(mac))

        self.ble_lock = asyncio.Lock()
        self.retry_count = 0

        self._pending_cmd_type: str = "analyze"
        self._pending_cmd_val: int = 0x01
        self._init_done: bool = False

        self._retry_cancel: CALLBACK_TYPE | None = None
        self._recalc_cancel: CALLBACK_TYPE | None = None
        self._save_cancel: asyncio.TimerHandle | None = None
        self._force_one_shot: bool = False
        self._is_shutdown: bool = False
        # True while we still owe a fresh read: at startup, and after every
        # out_of_range. Consumed by _on_ble_seen to kick a one-shot catch-up
        # refresh as soon as the sensor is back in range, instead of waiting
        # for the next (long) update_interval tick. Cleared on a successful read.
        self._needs_fresh_read: bool = True

        self._ble_available: bool = True
        self._ble_unavail_cancel: CALLBACK_TYPE | None = None
        self._ble_avail_cancel: CALLBACK_TYPE | None = None

        self.data: dict[str, Any] = {
            "active_measures": True,
            "action_running": False,
            "bluetooth_status": BT_STATUS_WAITING,
        }

        self.last_configured_sync_mode = entry.options.get(CONF_SYNC_MODE)
        self.last_configured_use_gw = get_opt(entry, CONF_USE_GATEWAY, True)

    @property
    def entry_id(self) -> str:
        return self._entry_id

    @property
    def is_shutdown(self) -> bool:
        return self._is_shutdown

    @property
    def entry(self) -> ConfigEntry | None:
        return self.hass.config_entries.async_get_entry(self._entry_id)

    @property
    def ble_available(self) -> bool:
        if async_scanner_count(self.hass, connectable=False) == 0:
            return False
        if not self._ble_available:
            return False
        last_info = async_last_service_info(self.hass, self.mac, connectable=False)
        if last_info:
            return (monotonic() - last_info.time) <= BLE_RECENTLY_SEEN_THRESHOLD_S
        return False

    def request_one_shot_analysis(self) -> None:
        self._force_one_shot = True

    def request_deferred_recompute(self) -> None:
        if self._recalc_cancel:
            self._recalc_cancel()
            self._recalc_cancel = None

        @callback
        def _do_recompute(_now) -> None:
            self._recalc_cancel = None
            if self.data:
                self.recompute_derived_values()

        self._recalc_cancel = async_call_later(
            self.hass, DEBOUNCE_COOLDOWN, _do_recompute
        )

    def set_pending_cmd(self, cmd_type: str, cmd_val: int) -> None:
        self._pending_cmd_type = cmd_type
        self._pending_cmd_val = cmd_val

    def _cancel_pending_retry(self) -> None:
        """Cancel an armed retry timer, if any (e.g. when going out of range)."""
        if self._retry_cancel:
            self._retry_cancel()
            self._retry_cancel = None

    @callback
    def _on_ble_unavailable(self, _info: BluetoothServiceInfoBleak) -> None:
        _LOGGER.debug("Flipr %s: BLE signal lost", self.safe_mac)
        self._ble_available = False
        self._set_bt_status(BT_STATUS_OUT_OF_RANGE)
        self._cancel_pending_retry()
        self.retry_count = 0

    @callback
    def _on_ble_seen(
        self, _info: BluetoothServiceInfoBleak, _change: BluetoothChange
    ) -> None:
        previously_unavailable = not self._ble_available
        self._ble_available = True

        current_status = self.data.get("bluetooth_status")
        active = self.data.get("active_measures", True)

        if current_status == BT_STATUS_OUT_OF_RANGE and active:
            if previously_unavailable:
                _LOGGER.debug("Flipr %s: BLE signal found", self.safe_mac)
            else:
                _LOGGER.debug(
                    "Flipr %s: recovering from stale out_of_range status",
                    self.safe_mac,
                )
            self._set_bt_status(BT_STATUS_WAITING)

        # The coordinator only reads on its (long) update_interval. After a
        # restart, or after recovering from out_of_range, that would leave the
        # pool without a fresh read for up to a full interval. Kick a one-shot
        # refresh the moment the sensor is back in range so recovery is
        # immediate instead of waiting for the next tick. async_request_refresh
        # is debounced, and the flag guarantees a single request per gap.
        if active and self._needs_fresh_read and not self._is_shutdown:
            self._needs_fresh_read = False
            _LOGGER.debug(
                "Flipr %s: sensor back in range, requesting catch-up refresh",
                self.safe_mac,
            )
            self.hass.async_create_task(self.async_request_refresh())

    async def async_initialize(self) -> None:
        saved_data = await self.store.async_load()

        if saved_data and "raw_frame" in saved_data:
            ts_val = saved_data.get("last_received")
            if isinstance(ts_val, str):
                parsed = dt_util.parse_datetime(ts_val)
                if parsed:
                    saved_data["last_received"] = parsed
                else:
                    saved_data.pop("last_received", None)

            for transient in ("bluetooth_status", "action_running"):
                saved_data.pop(transient, None)

            self.data.update(saved_data)
            self._init_done = True
            _LOGGER.debug("Data restored from disk for %s", self.safe_mac)
        else:
            _LOGGER.debug("No valid history on disk for %s", self.safe_mac)

        last_info = async_last_service_info(self.hass, self.mac, connectable=False)
        self._ble_available = (
            last_info is not None
            and (monotonic() - last_info.time) <= BLE_RECENTLY_SEEN_THRESHOLD_S
        )
        if not self._ble_available:
            _LOGGER.debug("Flipr %s: no recent BLE signal at startup", self.safe_mac)
            self.data["bluetooth_status"] = BT_STATUS_OUT_OF_RANGE

        self._ble_unavail_cancel = async_track_unavailable(
            self.hass,
            self._on_ble_unavailable,
            self.mac,
            connectable=False,
        )
        self._ble_avail_cancel = async_register_callback(
            self.hass,
            self._on_ble_seen,
            BluetoothCallbackMatcher(address=self.mac),
            BluetoothScanningMode.PASSIVE,
        )

    async def async_shutdown(self) -> None:
        self._is_shutdown = True

        if self._ble_unavail_cancel:
            self._ble_unavail_cancel()
            self._ble_unavail_cancel = None
        if self._ble_avail_cancel:
            self._ble_avail_cancel()
            self._ble_avail_cancel = None

        if self._retry_cancel:
            self._retry_cancel()
            self._retry_cancel = None

        if self._recalc_cancel:
            self._recalc_cancel()
            self._recalc_cancel = None

        # Cancel the debounce timer BEFORE saving. If the timer already fired and
        # spawned _do_save as a background task, that task checks _is_shutdown and bails
        # out cleanly. The authoritative save is the direct call below.
        if self._save_cancel:
            self._save_cancel.cancel()
            self._save_cancel = None

        try:
            await self.async_save_to_disk()
        except Exception as err:
            _LOGGER.debug("Error during final save on shutdown: %s", err)

    async def async_save_to_disk(self) -> None:
        data_to_save = dict(self.data)

        ts_val = data_to_save.get("last_received")
        if ts_val is not None and hasattr(ts_val, "isoformat"):
            data_to_save["last_received"] = ts_val.isoformat()

        for transient in ("bluetooth_status", "action_running"):
            data_to_save.pop(transient, None)

        await self.store.async_save(data_to_save)

    def _schedule_save(self) -> None:
        if self._is_shutdown:
            return
        if self._save_cancel:
            self._save_cancel.cancel()
            self._save_cancel = None

        loop = asyncio.get_running_loop()
        entry_id = self._entry_id

        def _schedule_save_callback() -> None:
            self._save_cancel = None  # handle has fired — clear before spawning task
            if self._is_shutdown:
                return
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry:
                entry.async_create_background_task(
                    self.hass, self._do_save(), "flipr_scheduled_save"
                )
            else:
                self.hass.async_create_task(self._do_save())

        self._save_cancel = loop.call_later(
            SAVE_DEBOUNCE_DELAY, _schedule_save_callback
        )

    async def _do_save(self) -> None:
        # NOTE: do not touch self._save_cancel here. The scheduler callback owns
        # it and may have already installed a new timer handle by the time this
        # coroutine runs; clearing it would leak that handle (uncancellable timer).
        if self._is_shutdown:
            return
        try:
            await self.async_save_to_disk()
        except Exception as err:
            _LOGGER.debug("Save failed: %s", err)

    def update_local_state(self, updates: dict[str, Any]) -> None:
        new_data = {**self.data, **updates}
        self.async_set_updated_data(new_data)
        self._schedule_save()

    def update_volatile_state(self, updates: dict[str, Any]) -> None:
        new_data = {**self.data, **updates}
        self.async_set_updated_data(new_data)

    def _set_bt_status(self, status: str) -> None:
        self.update_volatile_state({"bluetooth_status": status})

    def _data_or_fail(self, message: str) -> dict[str, Any]:
        """Return the last known data if we have history, else raise UpdateFailed."""
        if self.data.get("ph_raw") is not None:
            return dict(self.data)
        raise UpdateFailed(message)

    def _go_out_of_range(self, message: str) -> dict[str, Any]:
        """Mark out of range, reset retries, then return cached data or fail."""
        self._set_bt_status(BT_STATUS_OUT_OF_RANGE)
        self.retry_count = 0
        self._cancel_pending_retry()
        # Owe a fresh read again: _on_ble_seen will trigger it as soon as the
        # sensor reappears, rather than waiting for the next update_interval.
        self._needs_fresh_read = True
        return self._data_or_fail(message)

    def _select_command(self, entry: ConfigEntry) -> tuple[str, int, str]:
        """Return (cmd_type, cmd_val, target_uuid) for this cycle's GATT write.

        On the very first cycle (not yet init-done) the command comes from the
        gateway/sync configuration; afterwards it comes from the pending command.
        """
        if not self._init_done:
            if get_opt(entry, CONF_USE_GATEWAY, True):
                cmd_type, cmd_val = "mode", int(get_opt(entry, CONF_SYNC_MODE, "2"))
            else:
                cmd_type, cmd_val = "analyze", 0x01
        else:
            cmd_type, cmd_val = self._pending_cmd_type, self._pending_cmd_val
        target_uuid = SYNC_CHAR_UUID if cmd_type == "mode" else FLIPR_ANALYZE_UUID
        return cmd_type, cmd_val, target_uuid

    async def _async_update_data(self) -> dict[str, Any]:
        if self._is_shutdown:
            _LOGGER.debug(
                "Skipping update for %s: coordinator is shutting down",
                self.safe_mac,
            )
            return dict(self.data)

        if not self.data.get("active_measures", True):
            if self._force_one_shot:
                _LOGGER.debug("Force one-shot analysis requested for %s", self.safe_mac)
            else:
                _LOGGER.debug("Measurements paused by user for %s", self.safe_mac)
                self._set_bt_status(BT_STATUS_PAUSED)
                self.retry_count = 0
                return dict(self.data)

        if not self.ble_available:
            _LOGGER.debug(
                "Flipr %s: Bluetooth signal unavailable, connection ignored",
                self.safe_mac,
            )
            return self._go_out_of_range(
                f"Flipr {self.safe_mac} out of range and no history available"
            )

        device = async_ble_device_from_address(self.hass, self.mac, connectable=True)
        if not device:
            device = async_ble_device_from_address(
                self.hass, self.mac, connectable=False
            )
        if not device:
            _LOGGER.debug(
                "Flipr %s: ble_available is True but BLEDevice is missing from cache",
                self.safe_mac,
            )
            return self._go_out_of_range(
                f"Flipr {self.safe_mac}: Bluetooth device not found despite recent signal"
            )

        force_was_set = self._force_one_shot
        self._force_one_shot = False
        if force_was_set:
            _LOGGER.debug("Manual analysis triggered for %s", self.safe_mac)

        current_entry = self.entry
        if not current_entry:
            raise UpdateFailed("Config entry no longer available")

        is_init_done = self._init_done
        cmd_type, cmd_val, target_uuid = self._select_command(current_entry)

        old_raw_frame_hex = self.data.get("raw_frame") or ""
        try:
            # Use EXPECTED_FRAME_HEX_LEN constant instead of magic number 26.
            # A Flipr BLE frame is always 13 bytes → 26 hex characters when encoded.
            old_raw_frame_bytes = (
                bytes.fromhex(old_raw_frame_hex)
                if len(old_raw_frame_hex) == EXPECTED_FRAME_HEX_LEN
                else b""
            )
        except ValueError:
            _LOGGER.warning(
                "Corrupted raw_frame in storage for %s ('%s') — ignoring reference frame",
                self.safe_mac,
                old_raw_frame_hex,
            )
            old_raw_frame_bytes = b""

        # Identify model once before connecting to drive both connection options
        # and the data-reading strategy, without any GATT introspection.
        is_start_max = get_flipr_model(device.name).startswith("Flipr Start")

        result = await self._run_ble_exchange(
            device,
            cmd_type,
            cmd_val,
            target_uuid,
            is_init_done,
            is_start_max,
            old_raw_frame_bytes,
        )
        if isinstance(result, dict):
            return result

        self.retry_count = 0
        # GATT exchange succeeded: we no longer owe a catch-up read.
        self._needs_fresh_read = False
        return self._assemble_new_data(result, current_entry, cmd_type)

    def _handle_ble_error(
        self,
        error_msg: str,
        status: str = BT_STATUS_ERROR,
    ) -> dict[str, Any]:
        if status in (BT_STATUS_ERROR, BT_STATUS_WRITE_FAILED) and self.retry_count < 2:
            self.retry_count += 1
            self._set_bt_status(BT_STATUS_ERROR_RETRY)
            _LOGGER.warning(
                "Bluetooth error for %s: %s. Retrying in 60s (Attempt %d/3)...",
                self.safe_mac,
                error_msg,
                self.retry_count,
            )
            if self._retry_cancel:
                self._retry_cancel()
                self._retry_cancel = None

            @callback
            def _trigger_retry(_now) -> None:
                self._retry_cancel = None
                if self._is_shutdown:
                    _LOGGER.debug(
                        "Skipping retry for %s: coordinator is shutting down",
                        self.safe_mac,
                    )
                    return
                entry = self.hass.config_entries.async_get_entry(self._entry_id)
                if entry:
                    entry.async_create_background_task(
                        self.hass,
                        self.async_request_refresh(),
                        "flipr_retry_refresh",
                    )
                else:
                    self.hass.async_create_task(self.async_request_refresh())

            self._retry_cancel = async_call_later(self.hass, 60, _trigger_retry)
            return dict(self.data)

        self._set_bt_status(status)
        if status in (BT_STATUS_ERROR, BT_STATUS_OUT_OF_RANGE, BT_STATUS_WRITE_FAILED):
            _LOGGER.error(
                "Flipr %s unreachable after retries: %s",
                self.safe_mac,
                error_msg,
            )
            self.retry_count = 0

        return self._data_or_fail(f"Flipr unreachable and no history: {error_msg}")


