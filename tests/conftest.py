# Copyright (c) 2026 Adrien40
# This file is part of Flipr Local.

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    yield


@pytest.fixture(autouse=True)
def auto_mock_bluetooth(mock_bluetooth):
    """Keep Home Assistant's bluetooth component from touching real hardware.

    Recent Home Assistant releases open a real Bluetooth management socket when the
    bluetooth component is set up, which the pytest sandbox blocks (SocketBlockedError).
    flipr_local depends on the bluetooth component, so mock it out for every test that
    sets up the integration.
    """
    yield
