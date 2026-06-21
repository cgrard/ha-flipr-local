# Copyright (c) 2026 Adrien40
# This file is part of Flipr Local.

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    yield
