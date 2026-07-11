# Copyright (c) 2026 Adrien40
# Copyright (c) 2026 cgrard
# This file is part of Flipr Local.

"""Small shared, side-effect-free helpers for the Flipr Local integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN


def store_key(mac: str) -> str:
    """Storage key for a device's persisted state."""
    return f"{DOMAIN}_{mac.replace(':', '').lower()}"


def format_mac_safe(mac: str | None) -> str:
    """Return a log-safe, partially masked MAC address."""
    if not mac or len(mac) < 17:
        return "XX:XX:XX:XX:XX:XX"
    return f"{mac[:8]}...{mac[-5:]}"


def get_opt(entry: ConfigEntry, key: str, default: Any = None) -> Any:
    """Read an option, falling back to entry data then to a default."""
    if key in entry.options:
        return entry.options[key]
    if key in entry.data:
        return entry.data[key]
    return default
