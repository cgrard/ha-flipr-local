# Copyright (c) 2026 Adrien40
# This file is part of Flipr Local.

from time import monotonic
from types import SimpleNamespace

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.flipr_local import FliprDataCoordinator
import custom_components.flipr_local as integration
from custom_components.flipr_local.const import (
    BT_STATUS_SUCCESS,
    CONF_MAC_ADDRESS,
    CONF_MODEL,
    DOMAIN,
)

MAC = "AA:BB:CC:DD:EE:FF"


def _frame(temp_int=417, ph_mv=1600, orp_int=1300, sync=2, bat_mv=3600):
    """Build a 13-byte Flipr BLE frame (little-endian), matching the device layout."""
    return bytes(
        [
            *temp_int.to_bytes(2, "little"),
            *ph_mv.to_bytes(2, "little"),
            *orp_int.to_bytes(2, "little"),
            0x00,
            0x00,
            sync,
            0x00,
            0x00,
            *bat_mv.to_bytes(2, "little"),
        ]
    )


class FakeClient:
    """A minimal Bleak client that answers a GATT write by pushing one frame."""

    def __init__(self, frame: bytes) -> None:
        self._frame = frame
        self._notify_handler = None
        self.is_connected = True

    async def start_notify(self, char, handler) -> None:
        self._notify_handler = handler

    async def write_gatt_char(self, char, data, response=False) -> None:
        # Simulate the probe replying to the request with a notification frame.
        if self._notify_handler is not None:
            self._notify_handler(None, self._frame)

    async def read_gatt_char(self, char) -> bytes:
        return self._frame

    async def stop_notify(self, char) -> None:
        pass

    async def disconnect(self) -> None:
        self.is_connected = False


def _patch_ble(monkeypatch, client, device_name="F3A1"):
    """Make the coordinator see a reachable device and our fake client."""
    device = SimpleNamespace(name=device_name, address=MAC)

    async def _establish(*args, **kwargs):
        return client

    monkeypatch.setattr(integration, "async_scanner_count", lambda *a, **k: 1)
    monkeypatch.setattr(
        integration,
        "async_last_service_info",
        lambda *a, **k: SimpleNamespace(time=monotonic(), rssi=-60),
    )
    monkeypatch.setattr(
        integration, "async_ble_device_from_address", lambda *a, **k: device
    )
    monkeypatch.setattr(integration, "establish_connection", _establish)


async def _make_coordinator(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MAC_ADDRESS: MAC, CONF_MODEL: "Flipr AnalysR 3"},
        options={},
        title="Flipr AnalysR 3",
    )
    entry.add_to_hass(hass)
    coordinator = FliprDataCoordinator(hass, entry, MAC, MAC)
    # Skip the gateway init cycle so the test exercises a plain analyze request.
    coordinator._init_done = True
    coordinator._pending_cmd_type = "analyze"
    coordinator._pending_cmd_val = 0x01
    return coordinator


async def test_full_notify_cycle_returns_parsed_data(hass, monkeypatch):
    """A complete connect -> write -> notify -> parse cycle yields the frame values."""
    frame = _frame()
    client = FakeClient(frame)
    _patch_ble(monkeypatch, client)

    coordinator = await _make_coordinator(hass)
    try:
        data = await coordinator._async_update_data()
    finally:
        if coordinator._save_cancel:
            coordinator._save_cancel.cancel()

    assert data["ph_raw"] == 1600
    assert data["orp"] == 650
    assert data["battery"] == 3600
    assert data["battery_level"] == 100
    assert data["sync_mode"] == "2"
    assert data["raw_frame"] == frame.hex().upper()
    assert data["temperature"] == pytest.approx(25.02, abs=0.01)
    assert data["bluetooth_status"] == BT_STATUS_SUCCESS


async def test_start_max_poll_cycle_returns_parsed_data(hass, monkeypatch):
    """The Start Max read-by-poll path also yields the frame values."""

    async def _instant_sleep(_seconds):
        return None

    monkeypatch.setattr(integration.asyncio, "sleep", _instant_sleep)

    frame = _frame(ph_mv=1700, sync=1)
    client = FakeClient(frame)
    _patch_ble(monkeypatch, client, device_name="FLIPR 01-AB")

    coordinator = await _make_coordinator(hass)
    try:
        data = await coordinator._async_update_data()
    finally:
        if coordinator._save_cancel:
            coordinator._save_cancel.cancel()

    assert data["ph_raw"] == 1700
    assert data["sync_mode"] == "1"
    assert data["raw_frame"] == frame.hex().upper()
    assert data["bluetooth_status"] == BT_STATUS_SUCCESS
