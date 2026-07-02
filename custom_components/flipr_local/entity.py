# Copyright (c) 2026 Adrien40
# Copyright (c) 2026 cgrard
# This file is part of Flipr Local.

from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import options_updated_signal


class FliprOptionsUpdatedEntity:
    """Mixin: subscribe to the per-device "options updated" dispatcher signal.

    The consuming entity must set ``self._mac`` and define a
    ``_handle_options_updated`` callback. Call ``_subscribe_options_updated()``
    from ``async_added_to_hass`` to wire the subscription (auto-removed on
    teardown).
    """

    def _subscribe_options_updated(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                options_updated_signal(self._mac),
                self._handle_options_updated,
            )
        )
