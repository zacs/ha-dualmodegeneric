"""Shared fixtures for dualmode_generic tests."""

import pytest

# Import our package before the harness puts its own testing_config/custom_components
# on sys.path; otherwise that package shadows ours and the integration isn't found.
import custom_components  # noqa: F401

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in every test."""
    return
