# Copyright (c) 2026 Adrien40
# Copyright (c) 2026 cgrard
# This file is part of Flipr Local.

"""Bluetooth GATT transport for Flipr Local: connect, write the command and
read back the measurement frame. Mixed into FliprDataCoordinator, which owns
the status / retry / lock state that these methods drive."""

import asyncio
import contextlib
import logging
from time import monotonic
from typing import Any

from bleak import BleakClient
from bleak_retry_connector import establish_connection
from homeassistant.components.bluetooth import async_last_service_info
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import (
    BLE_RECENTLY_SEEN_THRESHOLD_S,
    BT_STATUS_CONNECTING,
    BT_STATUS_ERROR,
    BT_STATUS_OUT_OF_RANGE,
    BT_STATUS_READING,
    BT_STATUS_REQUESTING,
    BT_STATUS_WAKING_UP,
    BT_STATUS_WRITE_FAILED,
    BT_STATUS_WRITING_SYNC,
    FLIPR_CHARACTERISTIC_UUID,
    TIMEOUT_BLE_CONN,
)

_LOGGER = logging.getLogger(__name__)


async def _safely_disconnect(client: BleakClient | None) -> None:
    if client and client.is_connected:
        try:
            await client.disconnect()
        except Exception as err:
            _LOGGER.debug("Ignored error during disconnect: %s", err)


class FliprBleMixin:
    """GATT read cycle for one Flipr sensor.

    Runs on FliprDataCoordinator and uses its state: safe_mac, ble_lock,
    _set_bt_status, _handle_ble_error, retry_count, _pending_cmd_*, ...
    """

    async def _read_via_notify(
        self, queue: "asyncio.Queue[bytes]", reference: bytes, loop
    ) -> bytes:
        """Wait up to 60s for a new 13-byte frame via notifications.

        Returns the new frame, or raises asyncio.TimeoutError if none arrives.
        """
        deadline = loop.time() + 60.0
        while True:
            time_left = deadline - loop.time()
            if time_left <= 0:
                raise asyncio.TimeoutError()
            payload = await asyncio.wait_for(queue.get(), timeout=time_left)
            if len(payload) == 13 and (not reference or payload != reference):
                return payload

    async def _read_via_poll(
        self, client: BleakClient, reference: bytes
    ) -> bytes | None:
        """Start Max strategy: hold a silent connection, then poll for a new frame.

        Returns the new frame, or None if the three reads all yield the old frame.
        """
        _LOGGER.info(
            "Flipr %s: Start Max detected. Holding silent connection for 35s to allow internal measurement...",
            self.safe_mac,
        )
        await asyncio.sleep(35.0)

        for read_retry in range(3):
            if read_retry > 0:
                _LOGGER.debug(
                    "Flipr %s: Frame unchanged, waiting 8s more...",
                    self.safe_mac,
                )
                await asyncio.sleep(8.0)

            try:
                payload = await client.read_gatt_char(FLIPR_CHARACTERISTIC_UUID)
                _LOGGER.debug(
                    "Flipr %s: Read attempt %d: %s | REF: %s",
                    self.safe_mac,
                    read_retry + 1,
                    payload.hex().upper(),
                    reference.hex().upper() if reference else "NONE",
                )

                if len(payload) == 13 and (not reference or payload != reference):
                    return payload
            except Exception as read_err:
                _LOGGER.debug(
                    "Flipr %s: Error reading after silent wait: %s",
                    self.safe_mac,
                    read_err,
                )

        return None

    async def _run_ble_exchange(
        self,
        device,
        cmd_type: str,
        cmd_val: int,
        target_uuid: str,
        is_init_done: bool,
        is_start_max: bool,
        reference: bytes,
    ) -> bytes | dict[str, Any]:
        """Run one BLE connect/write/read cycle under the lock.

        Returns the received frame on success, or an error-status dict for a
        short-circuit; may raise UpdateFailed when the device is unreachable
        with no stored history.
        """
        client: BleakClient | None = None
        notify_started = False
        received_payload: bytes | None = None

        loop = asyncio.get_running_loop()

        async with self.ble_lock:
            try:
                self._set_bt_status(BT_STATUS_CONNECTING)

                client = await asyncio.wait_for(
                    establish_connection(
                        BleakClient,
                        device,
                        self.mac,
                        max_attempts=3,
                        **({"use_services_cache": False} if is_start_max else {}),
                    ),
                    timeout=TIMEOUT_BLE_CONN,
                )

                received_data_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=32)

                def notification_handler(sender, data: bytes) -> None:
                    try:
                        loop.call_soon_threadsafe(received_data_queue.put_nowait, data)
                    except asyncio.QueueFull:
                        _LOGGER.debug(
                            "Notification queue full for %s, dropping frame",
                            self.safe_mac,
                        )

                if not is_start_max:
                    await client.start_notify(
                        FLIPR_CHARACTERISTIC_UUID, notification_handler
                    )
                    notify_started = True

                reference_frame_bytes = reference

                for attempt in range(1, 3):
                    if not is_start_max:
                        while not received_data_queue.empty():
                            received_data_queue.get_nowait()

                    if cmd_type == "mode":
                        self._set_bt_status(BT_STATUS_WRITING_SYNC)
                        _LOGGER.info(
                            "Sending sync mode %s to Flipr %s - Attempt %d/2",
                            cmd_val,
                            self.safe_mac,
                            attempt,
                        )
                    else:
                        self._set_bt_status(
                            BT_STATUS_WAKING_UP
                            if not is_init_done
                            else BT_STATUS_REQUESTING
                        )

                    try:
                        await asyncio.wait_for(
                            client.write_gatt_char(
                                target_uuid, bytearray([cmd_val]), response=True
                            ),
                            timeout=15.0,
                        )
                    except asyncio.TimeoutError:
                        _LOGGER.warning(
                            "GATT write timed out for Flipr %s on attempt %d/2",
                            self.safe_mac,
                            attempt,
                        )
                        if attempt == 2:
                            return self._handle_ble_error(
                                "GATT write timed out", BT_STATUS_WRITE_FAILED
                            )
                        await asyncio.sleep(1.0)
                        continue
                    except Exception as write_err:
                        _LOGGER.warning(
                            "GATT write failed for Flipr %s on attempt %d/2: %s",
                            self.safe_mac,
                            attempt,
                            write_err,
                        )
                        if attempt == 2:
                            return self._handle_ble_error(
                                f"GATT write failed: {write_err}",
                                BT_STATUS_WRITE_FAILED,
                            )
                        await asyncio.sleep(1.0)
                        continue

                    self._set_bt_status(BT_STATUS_READING)

                    try:
                        if not is_start_max:
                            received_payload = await self._read_via_notify(
                                received_data_queue, reference_frame_bytes, loop
                            )
                            if received_payload:
                                break
                        else:
                            received_payload = await self._read_via_poll(
                                client, reference_frame_bytes
                            )
                            if received_payload:
                                break
                            raise asyncio.TimeoutError()

                    except asyncio.TimeoutError:
                        _LOGGER.warning(
                            "Timeout waiting for new data from Flipr %s on attempt %d/2.",
                            self.safe_mac,
                            attempt,
                        )

                if not received_payload:
                    return self._handle_ble_error(
                        "No valid data received from Flipr after 120 seconds.",
                        BT_STATUS_ERROR,
                    )

                if not is_init_done:
                    self._init_done = True

                # Only reset if the pending command hasn't been changed by
                # update_listener during this BLE cycle (race condition guard).
                # Compare BOTH type and value: a new "mode" command with a different
                # value written mid-cycle must survive, otherwise the user's sync-mode
                # change would be silently clobbered back to "analyze".
                # is_init_done guard: on the init cycle, cmd_type/cmd_val come from
                # config (not from _pending_cmd_*), so the equality check could be
                # accidentally True even if update_listener wrote a new command.
                if is_init_done and (self._pending_cmd_type, self._pending_cmd_val) == (
                    cmd_type,
                    cmd_val,
                ):
                    self._pending_cmd_type = "analyze"
                    self._pending_cmd_val = 0x01

            except asyncio.TimeoutError:
                last_info_now = async_last_service_info(
                    self.hass, self.mac, connectable=False
                )
                still_advertising = (
                    last_info_now is not None
                    and (monotonic() - last_info_now.time)
                    <= BLE_RECENTLY_SEEN_THRESHOLD_S
                )
                if still_advertising:
                    _LOGGER.warning(
                        "Connection timeout (>%ss) for %s but device is still advertising — treating as transient error",
                        TIMEOUT_BLE_CONN,
                        self.safe_mac,
                    )
                    return self._handle_ble_error(
                        f"Connection timed out after {TIMEOUT_BLE_CONN}s (device still advertising)",
                        BT_STATUS_ERROR,
                    )
                else:
                    _LOGGER.warning(
                        "Connection timeout (>%ss) for %s and no recent advertisement — marking out of range",
                        TIMEOUT_BLE_CONN,
                        self.safe_mac,
                    )
                    self.retry_count = 0
                    self._cancel_pending_retry()
                    self._set_bt_status(BT_STATUS_OUT_OF_RANGE)
                    if self.data.get("ph_raw") is not None:
                        return dict(self.data)
                    raise UpdateFailed(
                        f"Flipr {self.safe_mac} unreachable after {TIMEOUT_BLE_CONN}s and no advertisement"
                    ) from None
            except Exception as err:
                return self._handle_ble_error(
                    f"Communication error: {err}", BT_STATUS_ERROR
                )
            finally:
                if notify_started and client and client.is_connected:
                    with contextlib.suppress(Exception):
                        await client.stop_notify(FLIPR_CHARACTERISTIC_UUID)
                await _safely_disconnect(client)

        return received_payload
