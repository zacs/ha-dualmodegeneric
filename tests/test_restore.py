"""Restoring state after a restart.

The saved states here are in the format written by releases up to 0.2.x, so
these tests double as the upgrade path: the first restart after updating must
bring back the user's mode, targets and preset.
"""

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.const import EVENT_HOMEASSISTANT_START
from homeassistant.core import CoreState, HomeAssistant, State
from pytest_homeassistant_custom_component.common import (
    async_mock_restore_state_shutdown_restart,
    mock_restore_cache,
    mock_restore_cache_with_extra_data,
)

from .common import (
    ENTITY,
    HEATER,
    async_call,
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


async def test_saves_everything_for_next_start(hass: HomeAssistant) -> None:
    """Targets hidden by the current mode, presets and the last mode are all saved."""
    await async_setup_thermostat(hass, enable_heat_cool=True, away_temp=16)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    await async_call(hass, "set_temperature", target_temp_low=19, target_temp_high=25)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_temperature", temperature=21)
    await async_call(hass, "set_preset_mode", preset_mode="away")

    data = await async_mock_restore_state_shutdown_restart(hass)
    saved = data.last_states[ENTITY]
    assert saved.state.attributes["preset_mode"] == "away"
    assert saved.extra_data.as_dict() == {
        "target_temp": 16,
        "target_temp_low": 21,
        "target_temp_high": 25,
        "saved_targets": {"target_temp": 21, "target_temp_low": 21, "target_temp_high": 25},
        "last_active_hvac_mode": "heat",
        "owners": {},
        "version": 1,
    }


async def test_restores_hidden_targets(hass: HomeAssistant) -> None:
    """After a restart in heat_cool, heat mode still has its own target (#84)."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(ENTITY, "heat_cool", {"target_temp_low": 19, "target_temp_high": 25}),
                {
                    "target_temp": 22.5,
                    "target_temp_low": 19,
                    "target_temp_high": 25,
                    "saved_targets": None,
                    "last_active_hvac_mode": "heat_cool",
                    "owners": {},
                    "version": 1,
                },
            )
        ],
    )
    await async_setup_thermostat(hass, enable_heat_cool=True)
    state = thermostat(hass)
    assert (state.attributes["target_temp_low"], state.attributes["target_temp_high"]) == (19, 25)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert thermostat(hass).attributes["temperature"] == 22.5


async def test_turn_on_after_restart_returns_to_saved_mode(hass: HomeAssistant) -> None:
    """The mode before off survives a restart."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(ENTITY, "off", {"temperature": 21}),
                {
                    "target_temp": 21,
                    "target_temp_low": None,
                    "target_temp_high": None,
                    "last_active_hvac_mode": "cool",
                },
            )
        ],
    )
    await async_setup_thermostat(hass)
    await async_call(hass, "turn_on")
    assert thermostat(hass).state == HVACMode.COOL


async def test_acts_at_startup_without_waiting_for_a_reading(hass: HomeAssistant) -> None:
    """A restored mode controls devices as soon as Home Assistant has started."""
    await async_setup_restored(hass, "heat", {"temperature": 21}, temperature=18)
    assert is_on(hass, HEATER)


async def test_waits_for_startup_before_acting(hass: HomeAssistant) -> None:
    """Readings that arrive while Home Assistant is still starting don't act early."""
    mock_restore_cache(hass, [State(ENTITY, "heat", {"temperature": 21})])
    hass.set_state(CoreState.not_running)  # integrations load before HA starts
    await async_setup_thermostat(hass, temperature=18)
    await async_set_temperature(hass, 17)
    assert not is_on(hass, HEATER)

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
    await hass.async_block_till_done()
    assert is_on(hass, HEATER)
    assert thermostat(hass).attributes["current_temperature"] == 17


async def test_unreadable_saved_extra_data_falls_back(hass: HomeAssistant) -> None:
    """Saved data that isn't ours is ignored in favour of the attributes."""
    mock_restore_cache_with_extra_data(
        hass, [(State(ENTITY, "heat", {"temperature": 23}), {"unexpected": True})]
    )
    await async_setup_thermostat(hass)
    assert thermostat(hass).attributes["temperature"] == 23
