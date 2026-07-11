# Copyright (c) 2026 Adrien40
# Copyright (c) 2026 cgrard
# This file is part of Flipr Local.

"""On-disk persistence for Flipr Local: a debounced save of the last known
sensor data. Mixed into FliprDataCoordinator, whose store/data/shutdown
state these methods use."""

import asyncio
import logging

from .const import SAVE_DEBOUNCE_DELAY

_LOGGER = logging.getLogger(__name__)


class FliprStoreMixin:
    """Debounced on-disk persistence for FliprDataCoordinator."""

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
