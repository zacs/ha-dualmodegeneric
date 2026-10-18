"""Restoring state after a restart.

The saved states here are in the format written by releases up to 0.2.x, so
these tests double as the upgrade path: the first restart after updating must
bring back the user's mode, targets and preset.
"""

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant

from .common import (
    HEATER,
    async_set_temperature,
    async_setup_restored,
    async_setup_thermostat,
    devices_on,
    is_on,
    thermostat,
)


async def test_no_saved_state_starts_off(hass: HomeAssistant) -> None:
    """A brand-new thermostat starts off, with the configured target."""
    await async_setup_thermostat(hass, temperature=10, target_temp=21)
    state = thermostat(hass)
    assert state.state == HVACMode.OFF
    assert state.attributes["temperature"] == 21
    assert devices_on(hass) == set()


@pytest.mark.parametrize("mode", ["heat", "cool"])
async def test_restores_mode_and_target(hass: HomeAssistant, mode: str) -> None:
    """The saved mode and target come back."""
    await async_setup_restored(hass, mode, {"temperature": 23.5})
    state = thermostat(hass)
    assert state.state == mode
    assert state.attributes["temperature"] == 23.5


async def test_saved_target_wins_over_configured(hass: HomeAssistant) -> None:
    """A target the user changed survives restarts despite target_temp in YAML."""
    await async_setup_restored(hass, "heat", {"temperature": 23.5}, target_temp=19)
    assert thermostat(hass).attributes["temperature"] == 23.5


async def test_restores_range(hass: HomeAssistant) -> None:
    """The heat_cool range comes back."""
    await async_setup_restored(
        hass,
        "heat_cool",
        {"target_temp_low": 18.5, "target_temp_high": 25.5},
        enable_heat_cool=True,
        target_temp_low=20,
        target_temp_high=24,
    )
    state = thermostat(hass)
    assert state.state == HVACMode.HEAT_COOL
    assert state.attributes["target_temp_low"] == 18.5
    assert state.attributes["target_temp_high"] == 25.5


async def test_restores_away_preset(hass: HomeAssistant) -> None:
    """The away preset comes back."""
    await async_setup_restored(
        hass, "heat", {"temperature": 16, "preset_mode": "away"}, away_temp=16
    )
    state = thermostat(hass)
    assert state.attributes["preset_mode"] == "away"
    assert state.attributes["temperature"] == 16


async def test_restored_off_stays_off(hass: HomeAssistant) -> None:
    """Restoring 'off' never turns devices on, however cold it is."""
    await async_setup_restored(hass, "off", {"temperature": 21}, temperature=10)
    await async_set_temperature(hass, 9)
    assert devices_on(hass) == set()


async def test_restored_heat_resumes_control(hass: HomeAssistant) -> None:
    """A restored active mode controls devices again."""
    await async_setup_restored(hass, "heat", {"temperature": 21}, temperature=18)
    await async_set_temperature(hass, 17.9)
    assert is_on(hass, HEATER)
