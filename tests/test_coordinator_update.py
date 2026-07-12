# Copyright (c) 2026 Adrien40
# Copyright (c) 2026 cgrard
# This file is part of Flipr Local.

import asyncio
from time import monotonic
from types import SimpleNamespace

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.flipr_local import FliprDataCoordinator
import custom_components.flipr_local.coordinator as coordinator_mod
import custom_components.flipr_local.ble as ble_mod
import custom_components.flipr_local.sensor as sensor_mod
from custom_components.flipr_local.const import (
    BT_STATUS_ERROR_RETRY,
    BT_STATUS_SUCCESS,
    CONF_CHLORINE_MODEL,
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

    def _recent_info(*a, **k):
        return SimpleNamespace(time=monotonic(), rssi=-60)

    monkeypatch.setattr(coordinator_mod, "async_scanner_count", lambda *a, **k: 1)
    # async_last_service_info is read by both the coordinator (ble_available)
    # and the ble exchange (freshness guard) -> patch both modules.
    monkeypatch.setattr(coordinator_mod, "async_last_service_info", _recent_info)
    monkeypatch.setattr(ble_mod, "async_last_service_info", _recent_info)
    monkeypatch.setattr(
        coordinator_mod, "async_ble_device_from_address", lambda *a, **k: device
    )
    # establish_connection now lives in the ble module.
    monkeypatch.setattr(ble_mod, "establish_connection", _establish)


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

    monkeypatch.setattr(coordinator_mod.asyncio, "sleep", _instant_sleep)

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


async def test_standby_frame_raises_without_history(hass, monkeypatch):
    """An all-zero (standby) frame with no stored history raises UpdateFailed."""
    client = FakeClient(b"\x00" * 13)
    _patch_ble(monkeypatch, client)

    coordinator = await _make_coordinator(hass)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_parse_failure_triggers_retry(hass, monkeypatch):
    """An implausible frame is rejected and schedules a retry."""
    client = FakeClient(_frame(ph_mv=100))  # 100 mV is below the 500 mV floor
    _patch_ble(monkeypatch, client)

    coordinator = await _make_coordinator(hass)
    try:
        data = await coordinator._async_update_data()
        assert data["bluetooth_status"] == BT_STATUS_ERROR_RETRY
    finally:
        coordinator._cancel_pending_retry()


async def test_write_timeout_triggers_retry(hass, monkeypatch):
    """Two failed GATT writes mark a write failure and schedule a retry."""

    async def _instant_sleep(_seconds):
        return None

    monkeypatch.setattr(coordinator_mod.asyncio, "sleep", _instant_sleep)

    class TimeoutClient(FakeClient):
        async def write_gatt_char(self, char, data, response=False):
            raise asyncio.TimeoutError()

    client = TimeoutClient(_frame())
    _patch_ble(monkeypatch, client)

    coordinator = await _make_coordinator(hass)
    try:
        data = await coordinator._async_update_data()
        assert data["bluetooth_status"] == BT_STATUS_ERROR_RETRY
    finally:
        coordinator._cancel_pending_retry()


async def test_save_and_restore_roundtrip(hass, monkeypatch):
    """Data saved to the Store is restored by a fresh coordinator."""
    monkeypatch.setattr(
        coordinator_mod, "async_track_unavailable", lambda *a, **k: lambda: None
    )
    monkeypatch.setattr(
        coordinator_mod, "async_register_callback", lambda *a, **k: lambda: None
    )
    monkeypatch.setattr(coordinator_mod, "async_scanner_count", lambda *a, **k: 0)
    monkeypatch.setattr(
        coordinator_mod, "async_last_service_info", lambda *a, **k: None
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MAC_ADDRESS: MAC, CONF_MODEL: "Flipr AnalysR 3"},
        options={},
        title="Flipr AnalysR 3",
    )
    entry.add_to_hass(hass)

    saver = FliprDataCoordinator(hass, entry, MAC, MAC)
    saver.data.update({"ph_raw": 1600, "raw_frame": "ABCDEF", "ph": 7.2})
    await saver.async_save_to_disk()

    loader = FliprDataCoordinator(hass, entry, MAC, MAC)
    await loader.async_initialize()
    try:
        assert loader.data.get("ph_raw") == 1600
        assert loader.data.get("raw_frame") == "ABCDEF"
        assert loader.data.get("ph") == 7.2
    finally:
        await loader.async_shutdown()


def _stub_ble_callbacks(monkeypatch):
    """Neutralise the bluetooth helpers used during entry setup/initialize."""
    for mod in (coordinator_mod, sensor_mod):
        monkeypatch.setattr(
            mod, "async_register_callback", lambda *a, **k: lambda: None, raising=False
        )
        monkeypatch.setattr(
            mod, "async_last_service_info", lambda *a, **k: None, raising=False
        )
        monkeypatch.setattr(
            mod, "async_scanner_count", lambda *a, **k: 0, raising=False
        )
    monkeypatch.setattr(
        coordinator_mod, "async_track_unavailable", lambda *a, **k: lambda: None
    )


async def test_recompute_derived_values_full_pipeline(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MAC_ADDRESS: MAC, CONF_MODEL: "Flipr AnalysR 3"},
        options={},
        title="Flipr AnalysR 3",
    )
    entry.add_to_hass(hass)
    coord = FliprDataCoordinator(hass, entry, MAC, MAC)
    coord.data.update(
        {
            "temp_raw": 25.0,
            "ph_raw": 1600,
            "orp_raw": 650,
            "tac": 100,
            "th": 200,
            "tds": 1000,
            "cya": 40,
        }
    )

    coord.recompute_derived_values()

    assert coord.data["temperature"] == 25.0
    assert coord.data["orp"] == 650
    assert "ph" in coord.data
    assert coord.data["lsi"] is not None
    assert coord.data["target_equilibrium_ph"] is not None
    assert coord.data["estimated_free_chlorine"] is not None


async def test_recompute_bromine_and_missing_water_params(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MAC_ADDRESS: MAC, CONF_MODEL: "X"},
        options={CONF_CHLORINE_MODEL: "bromine"},
        title="X",
    )
    entry.add_to_hass(hass)
    coord = FliprDataCoordinator(hass, entry, MAC, MAC)
    coord.data.update({"temp_raw": 25.0, "ph_raw": 1600, "orp_raw": 650})  # no TAC/TH

    coord.recompute_derived_values()

    assert coord.data["lsi"] is None  # missing TAC/TH -> not computable
    assert coord.data["lsi_status"] is None
    assert coord.data["estimated_free_chlorine"] is None  # bromine -> no chlorine


async def test_setup_and_unload_entry(hass, monkeypatch):
    _stub_ble_callbacks(monkeypatch)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MAC_ADDRESS: MAC, CONF_MODEL: "Flipr AnalysR 3"},
        options={},
        title="Flipr AnalysR 3",
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_ids = hass.states.async_entity_ids()
    assert any(eid.startswith("sensor.") for eid in entity_ids)
    assert any(eid.startswith("switch.") for eid in entity_ids)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_ble_seen_requests_catch_up_refresh(hass, monkeypatch):
    """When a fresh read is owed, seeing the sensor kicks a one-shot refresh.

    Regression guard: after a restart the coordinator would otherwise sit idle
    until its next (long) update_interval tick instead of reading right away.
    """
    coordinator = await _make_coordinator(hass)

    calls = []

    async def _fake_refresh():
        calls.append(True)

    monkeypatch.setattr(coordinator, "async_request_refresh", _fake_refresh)

    coordinator._needs_fresh_read = True
    info = SimpleNamespace(address=MAC, time=monotonic(), rssi=-60)
    coordinator._on_ble_seen(info, None)

    # Flag is consumed synchronously; the refresh runs on the event loop.
    assert coordinator._needs_fresh_read is False
    await hass.async_block_till_done()
    assert calls == [True]


async def test_ble_seen_no_refresh_when_up_to_date(hass, monkeypatch):
    """No spurious refresh when no fresh read is owed."""
    coordinator = await _make_coordinator(hass)

    calls = []

    async def _fake_refresh():
        calls.append(True)

    monkeypatch.setattr(coordinator, "async_request_refresh", _fake_refresh)

    coordinator._needs_fresh_read = False
    info = SimpleNamespace(address=MAC, time=monotonic(), rssi=-60)
    coordinator._on_ble_seen(info, None)

    await hass.async_block_till_done()
    assert calls == []


async def test_needs_fresh_read_lifecycle(hass, monkeypatch):
    """A successful read clears the flag; going out_of_range re-arms it."""
    client = FakeClient(_frame())
    _patch_ble(monkeypatch, client)
    coordinator = await _make_coordinator(hass)
    coordinator._needs_fresh_read = True
    try:
        data = await coordinator._async_update_data()
        assert data["bluetooth_status"] == BT_STATUS_SUCCESS
        assert coordinator._needs_fresh_read is False

        # The DataUpdateCoordinator normally stores the returned data; replicate
        # that so _go_out_of_range finds history and returns it instead of failing.
        coordinator.data = dict(data)

        # Losing the signal re-arms the one-shot catch-up.
        coordinator._go_out_of_range("signal lost")
        assert coordinator._needs_fresh_read is True
    finally:
        if coordinator._save_cancel:
            coordinator._save_cancel.cancel()


async def test_ble_unavailable_arms_catch_up(hass):
    """Signal loss via _on_ble_unavailable arms the catch-up flag (not just polls)."""
    coordinator = await _make_coordinator(hass)
    coordinator._needs_fresh_read = False
    coordinator._on_ble_unavailable(None)
    assert coordinator._needs_fresh_read is True
    coordinator._cancel_pending_retry()


async def test_out_of_range_schedules_fast_retry(hass):
    """Out of range must re-poll on a short cadence, not wait a full update_interval.

    Root cause of the field "stuck until a manual reload" reports: _go_out_of_range
    armed no retry, so after a restart landing in a brief signal gap the sensor sat
    out_of_range for up to update_interval (an hour). A short self-perpetuating retry
    recovers within ~a minute, the same as a manual reload.
    """
    coordinator = await _make_coordinator(hass)
    coordinator.data = {**coordinator.data, "ph_raw": 1600}  # history so it returns
    assert coordinator._retry_cancel is None
    coordinator._go_out_of_range("out of range")
    assert coordinator._retry_cancel is not None
    coordinator._cancel_pending_retry()


async def test_ble_unavailable_schedules_fast_retry(hass):
    """Losing the signal via the unavailable callback also arms the short retry."""
    coordinator = await _make_coordinator(hass)
    assert coordinator._retry_cancel is None
    coordinator._on_ble_unavailable(None)
    assert coordinator._retry_cancel is not None
    coordinator._cancel_pending_retry()


async def test_ble_available_trusts_fresh_advert_over_stuck_flag(hass, monkeypatch):
    """A stuck _ble_available=False must not veto availability when an advert is fresh.

    Root-cause guard: at marginal signal async_track_unavailable can flip the flag
    False without a matching _on_ble_seen advert callback flipping it back. The flag
    then strands the coordinator in out_of_range until a manual reload, even while
    adverts keep arriving. ble_available must follow the fresh advert, not the flag.
    """
    coordinator = await _make_coordinator(hass)
    monkeypatch.setattr(coordinator_mod, "async_scanner_count", lambda *a, **k: 1)
    monkeypatch.setattr(
        coordinator_mod,
        "async_last_service_info",
        lambda *a, **k: SimpleNamespace(time=monotonic(), rssi=-75),
    )

    coordinator._ble_available = False  # stuck from a missed _on_ble_seen
    assert coordinator.ble_available is True

    # A genuinely stale advert (older than the freshness window) stays out of range.
    stale = monotonic() - (coordinator_mod.BLE_RECENTLY_SEEN_THRESHOLD_S + 5)
    monkeypatch.setattr(
        coordinator_mod,
        "async_last_service_info",
        lambda *a, **k: SimpleNamespace(time=stale, rssi=-75),
    )
    assert coordinator.ble_available is False

    # No scanners at all is still unavailable regardless of a cached advert.
    monkeypatch.setattr(coordinator_mod, "async_scanner_count", lambda *a, **k: 0)
    monkeypatch.setattr(
        coordinator_mod,
        "async_last_service_info",
        lambda *a, **k: SimpleNamespace(time=monotonic(), rssi=-75),
    )
    assert coordinator.ble_available is False
