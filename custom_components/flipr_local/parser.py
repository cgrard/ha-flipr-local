# Copyright (c) 2026 Adrien40
# Copyright (c) 2026 cgrard
# This file is part of Flipr Local.

"""Frame decoding and derived-value computation for Flipr Local: turn a raw
BLE frame into a data dict and recompute pool chemistry. Mixed into
FliprDataCoordinator, whose data/entry/error state these methods use."""

import logging
from typing import Any

import homeassistant.util.dt as dt_util
from homeassistant.config_entries import ConfigEntry

from .battery import battery_percent_from_mv
from .chemistry import (
    compute_active_chlorine_from_fc,
    compute_isl,
    compute_ph_equilibrium,
    estimate_free_chlorine,
    get_mv_from_input,
)
from .helpers import get_opt
from .const import (
    BATTERY_MAX_MV,
    BATTERY_MIN_MV,
    BT_STATUS_ERROR,
    BT_STATUS_SUCCESS,
    BT_STATUS_SYNC_APPLIED,
    BT_STATUS_WAITING,
    CONF_CHLORINE_MODEL,
    CONF_CYA,
    CONF_ORP_CALIB,
    CONF_ORP_REF,
    CONF_PH_CALIB_4,
    CONF_PH_CALIB_7,
    CONF_PH_REF_4,
    CONF_PH_REF_7,
    CONF_TAC,
    CONF_TDS,
    CONF_TEMP_OFFSET,
    CONF_TH,
    DATA_ACTIVE_CHLORINE_HOCL,
    DATA_ESTIMATED_FREE_CHLORINE,
    DEFAULT_ORP_CALIB,
    DEFAULT_ORP_REF,
    DEFAULT_PH_CALIB_4,
    DEFAULT_PH_CALIB_7,
    DEFAULT_PH_REF_4,
    DEFAULT_PH_REF_7,
    PH_FACTORY_OFFSET,
    PH_FACTORY_SLOPE,
    VALID_SYNC_MODES,
)

_LOGGER = logging.getLogger(__name__)

_TEMP_MIN_PLAUSIBLE = 0.0
_TEMP_MAX_PLAUSIBLE = 50.0
_ORP_MIN_PLAUSIBLE = 0.0
_ORP_MAX_PLAUSIBLE = 1500.0
_BAT_MIN_PLAUSIBLE = BATTERY_MIN_MV - 500
_BAT_MAX_PLAUSIBLE = BATTERY_MAX_MV + 500
_PH_MV_MIN_PLAUSIBLE = 500
_PH_MV_MAX_PLAUSIBLE = 3000


class FliprParseMixin:
    """Frame decoding and pool-chemistry computation for FliprDataCoordinator.

    Uses the host coordinator's state: data, entry, safe_mac,
    update_volatile_state, _handle_ble_error, _schedule_save, retry_count.
    """

    def _compute_ph_calibrated(
        self,
        ph_raw_mv: float,
        c4_mv: float,
        c7_mv: float,
        ph_ref_4: float,
        ph_ref_7: float,
    ) -> float:
        if abs(ph_ref_4 - ph_ref_7) < 1e-9:
            return 7.0
        slope = (float(c4_mv) - float(c7_mv)) / (ph_ref_4 - ph_ref_7)
        if abs(slope) < 1e-9:
            return 7.0
        return ph_ref_7 + (ph_raw_mv - float(c7_mv)) / slope

    def _load_ph_calibration(
        self, entry: ConfigEntry
    ) -> tuple[float, float, float, float]:
        raw_c4 = get_opt(entry, CONF_PH_CALIB_4, DEFAULT_PH_CALIB_4)
        raw_c7 = get_opt(entry, CONF_PH_CALIB_7, DEFAULT_PH_CALIB_7)
        try:
            c4_mv = get_mv_from_input(raw_c4)
        except ValueError:
            _LOGGER.warning(
                "Invalid pH 4 calibration value '%s' for %s - using factory default",
                raw_c4,
                self.safe_mac,
            )
            c4_mv = get_mv_from_input(DEFAULT_PH_CALIB_4)
        try:
            c7_mv = get_mv_from_input(raw_c7)
        except ValueError:
            _LOGGER.warning(
                "Invalid pH 7 calibration value '%s' for %s - using factory default",
                raw_c7,
                self.safe_mac,
            )
            c7_mv = get_mv_from_input(DEFAULT_PH_CALIB_7)
        ph_ref_7 = float(get_opt(entry, CONF_PH_REF_7, DEFAULT_PH_REF_7))
        ph_ref_4 = float(get_opt(entry, CONF_PH_REF_4, DEFAULT_PH_REF_4))
        return c4_mv, c7_mv, ph_ref_4, ph_ref_7

    def _build_chemistry_updates(
        self,
        temp: float | None,
        ph: float | None,
        orp: float | None,
        tac: float,
        th: float,
        tds: float,
        cya: float,
        chlorine_model: str,
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {}

        if temp is not None and tac > 0 and th > 0:
            updates["target_equilibrium_ph"] = compute_ph_equilibrium(
                temp, tac, th, tds
            )
        else:
            updates["target_equilibrium_ph"] = None

        if temp is not None and ph is not None and tac > 0 and th > 0:
            lsi_val = compute_isl(temp, ph, tac, th, tds)
            updates["lsi"] = lsi_val
            if lsi_val is not None:
                if lsi_val < -0.3:
                    updates["lsi_status"] = "corrosive"
                elif lsi_val > 0.3:
                    updates["lsi_status"] = "scaling"
                else:
                    updates["lsi_status"] = "balanced"
            else:
                updates["lsi_status"] = None
        else:
            updates["lsi"] = None
            updates["lsi_status"] = None

        if ph is not None:
            if orp is None or chlorine_model == "bromine":
                updates[DATA_ESTIMATED_FREE_CHLORINE] = None
                updates[DATA_ACTIVE_CHLORINE_HOCL] = None
            else:
                fc = estimate_free_chlorine(orp, ph, cya)
                updates[DATA_ESTIMATED_FREE_CHLORINE] = fc
                updates[DATA_ACTIVE_CHLORINE_HOCL] = (
                    compute_active_chlorine_from_fc(
                        fc, ph, temp if temp is not None else 25.0, cya
                    )
                    if fc is not None
                    else None
                )
        else:
            updates[DATA_ESTIMATED_FREE_CHLORINE] = None
            updates[DATA_ACTIVE_CHLORINE_HOCL] = None

        return updates

    def recompute_derived_values(self) -> None:
        if not self.data:
            return

        current_entry = self.entry
        if not current_entry:
            return

        raw_temp = self.data.get("temp_raw", self.data.get("temperature"))
        ph_raw_mv = self.data.get("ph_raw")
        raw_orp = self.data.get("orp_raw")

        tac = self.data.get(CONF_TAC) or 0
        th = self.data.get(CONF_TH) or 0
        tds = self.data.get(CONF_TDS) or 0

        cya_raw = self.data.get(CONF_CYA)
        cya = float(cya_raw) if cya_raw is not None else 40.0

        chlorine_model = get_opt(current_entry, CONF_CHLORINE_MODEL, "chlorine")
        updates: dict[str, Any] = {}

        temp_offset = float(get_opt(current_entry, CONF_TEMP_OFFSET, 0.0))
        if raw_temp is not None:
            updates["temperature"] = round(raw_temp + temp_offset, 2)
            temp = updates["temperature"]
        else:
            temp = None

        if ph_raw_mv is not None:
            c4_mv, c7_mv, ph_ref_4, ph_ref_7 = self._load_ph_calibration(current_entry)
            ph_calculated = self._compute_ph_calibrated(
                ph_raw_mv, c4_mv, c7_mv, ph_ref_4, ph_ref_7
            )
            updates["ph"] = round(ph_calculated, 2)
            ph = updates["ph"]
        else:
            ph = self.data.get("ph")

        if raw_orp is not None:
            orp_target = float(get_opt(current_entry, CONF_ORP_REF, DEFAULT_ORP_REF))
            orp_measured = float(
                get_opt(current_entry, CONF_ORP_CALIB, DEFAULT_ORP_CALIB)
            )
            orp_offset = orp_target - orp_measured
            updates["orp"] = round(raw_orp + orp_offset)
            orp = updates["orp"]
        else:
            orp = self.data.get("orp")

        updates.update(
            self._build_chemistry_updates(
                temp, ph, orp, tac, th, tds, cya, chlorine_model
            )
        )

        # Use `k not in self.data` to correctly detect keys that are new (not yet
        # present in self.data) even when their computed value is None. The previous
        # `self.data.get(k) != v` would silently skip a new key whose value is None,
        # since get() also returns None for missing keys — identical but not the same.
        changed_updates = {
            k: v for k, v in updates.items() if k not in self.data or self.data[k] != v
        }
        if changed_updates:
            self.update_volatile_state(changed_updates)

    def _parse_raw_frame(
        self, data: bytes
    ) -> tuple[float, float, float, str | None, int] | None:
        if len(data) < 13:
            _LOGGER.debug("Frame too short: %d bytes", len(data))
            return None
        raw_temp = int.from_bytes(data[0:2], "little") * 0.06
        ph_raw_mv = int.from_bytes(data[2:4], "little")
        raw_orp = int.from_bytes(data[4:6], "little") / 2.0
        sync_mode_raw = str(data[8])
        bat_raw = int.from_bytes(data[11:13], "little")

        if not (_PH_MV_MIN_PLAUSIBLE <= ph_raw_mv <= _PH_MV_MAX_PLAUSIBLE):
            _LOGGER.warning("Implausible pH raw value %d mV", ph_raw_mv)
            return None

        if not (_TEMP_MIN_PLAUSIBLE <= raw_temp <= _TEMP_MAX_PLAUSIBLE):
            _LOGGER.warning("Implausible temperature value %.2f", raw_temp)
            return None

        if not (_ORP_MIN_PLAUSIBLE <= raw_orp <= _ORP_MAX_PLAUSIBLE):
            _LOGGER.warning("Implausible ORP value %.1f mV", raw_orp)
            return None

        if not (_BAT_MIN_PLAUSIBLE <= bat_raw <= _BAT_MAX_PLAUSIBLE):
            _LOGGER.warning("Implausible battery value %d mV", bat_raw)
            return None

        return raw_temp, ph_raw_mv, raw_orp, sync_mode_raw, bat_raw

    def _assemble_new_data(
        self, payload: bytes, entry: ConfigEntry, cmd_type: str
    ) -> dict[str, Any]:
        """Parse a received frame and build the coordinator data dict.

        Returns the new data, or an error-status dict (standby / parse failure)
        produced by _handle_ble_error.
        """
        data = payload
        hex_frame = data.hex().upper()

        if hex_frame.startswith("0000"):
            # Device in standby — reset retry_count so it doesn't accumulate
            # across standby cycles and cause spurious retry escalation.
            self.retry_count = 0
            return self._handle_ble_error(
                "Sensor is in standby or frame is empty", BT_STATUS_WAITING
            )

        parsed = self._parse_raw_frame(data)
        if parsed is None:
            return self._handle_ble_error("Payload parsing error", BT_STATUS_ERROR)

        raw_temp, ph_raw_mv, raw_orp, sync_mode_raw, bat_raw = parsed
        actual_sync_mode = sync_mode_raw if sync_mode_raw in VALID_SYNC_MODES else None

        temp_offset = float(get_opt(entry, CONF_TEMP_OFFSET, 0.0))
        orp_target = float(get_opt(entry, CONF_ORP_REF, DEFAULT_ORP_REF))
        orp_measured = float(get_opt(entry, CONF_ORP_CALIB, DEFAULT_ORP_CALIB))
        orp_offset = orp_target - orp_measured

        temp = raw_temp + temp_offset
        orp = raw_orp + orp_offset

        c4_mv, c7_mv, ph_ref_4, ph_ref_7 = self._load_ph_calibration(entry)
        ph_calculated = self._compute_ph_calibrated(
            ph_raw_mv, c4_mv, c7_mv, ph_ref_4, ph_ref_7
        )
        factory_ph = PH_FACTORY_SLOPE * ph_raw_mv + PH_FACTORY_OFFSET

        tac_val = self.data.get(CONF_TAC) or 0
        th_val = self.data.get(CONF_TH) or 0
        tds_val = self.data.get(CONF_TDS) or 0

        cya_raw = self.data.get(CONF_CYA)
        cya_val = float(cya_raw) if cya_raw is not None else 40.0

        chlorine_model = get_opt(entry, CONF_CHLORINE_MODEL, "chlorine")

        now = dt_util.utcnow()
        measurement_time = (
            (self.data.get("last_received") or now)
            if self.data.get("raw_frame") == hex_frame
            else now
        )

        # Li-SOCl2 state-of-charge from the cell voltage (see battery.py). A linear
        # map is not usable for this chemistry because of its flat discharge plateau.
        bat_pct: int = battery_percent_from_mv(bat_raw)

        new_data: dict[str, Any] = {
            **self.data,
            "temp_raw": raw_temp,
            "temperature": round(temp, 2),
            "ph": round(ph_calculated, 2),
            "ph_raw": ph_raw_mv,
            "factory_ph": round(factory_ph, 2),
            "orp_raw": raw_orp,
            "orp": round(orp),
            "battery": bat_raw,
            "battery_level": bat_pct,
            "sync_mode": actual_sync_mode,
            "last_received": measurement_time,
            "raw_frame": hex_frame,
            "bluetooth_status": (
                BT_STATUS_SYNC_APPLIED if cmd_type == "mode" else BT_STATUS_SUCCESS
            ),
        }

        new_data.update(
            self._build_chemistry_updates(
                round(temp, 2),
                round(ph_calculated, 2),
                round(orp),
                tac_val,
                th_val,
                tds_val,
                cya_val,
                chlorine_model,
            )
        )
        self._schedule_save()
        return new_data
