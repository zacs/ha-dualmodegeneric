"""Known bugs in the current implementation.

Each test asserts the *correct* behaviour and is marked as an expected failure.
xfail is strict, so once a fix makes one pass, the suite fails until its marker
is removed and the test joins the regular suite.
"""

from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.climate import HVACAction
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .common import (
    COOLER,
    DRYER,
    FAN,
    HEATER,
    ServiceCallRecorder,
    async_call,
    async_set_temperature,
    async_setup_restored,
    async_setup_thermostat,
    async_toggle,
    devices_on,
    is_on,
    thermostat,
)


@pytest.mark.xfail(reason="#84: single target isn't saved in heat_cool -> TypeError")
async def test_fan_only_after_restart_in_heat_cool(hass: HomeAssistant) -> None:
    """Choosing fan-only after restarting in heat_cool works."""
    await async_setup_restored(
        hass,
        "heat_cool",
        {"target_temp_low": 20, "target_temp_high": 24},
        fan=FAN,
        fan_behavior="neutral",
        enable_heat_cool=True,
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="fan_only")
    assert is_on(hass, FAN)


@pytest.mark.xfail(reason="#83: heat_cool 'comfortable' band is empty for narrow ranges")
async def test_narrow_heat_cool_range_goes_idle(hass: HomeAssistant) -> None:
    """With a range narrower than both tolerances, heating still stops."""
    await async_setup_thermostat(
        hass, temperature=22.9, enable_heat_cool=True, cold_tolerance=0.3, hot_tolerance=0.3
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    await async_call(hass, "set_temperature", target_temp_low=23.3, target_temp_high=23.7)
    assert is_on(hass, HEATER)
    await async_set_temperature(hass, 23.9)
    assert devices_on(hass) == set()


@pytest.mark.xfail(reason="#28: any running device counts as 'running', so the fan blocks heat")
async def test_running_fan_does_not_block_heater(hass: HomeAssistant) -> None:
    """A fan switched on for circulation doesn't stop heat mode from heating."""
    await async_setup_thermostat(hass, temperature=23, fan=FAN, target_temp=22)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_toggle(hass, FAN, True)
    await async_set_temperature(hass, 21)
    assert is_on(hass, HEATER)


@pytest.mark.xfail(reason="#28: hvac_action reflects any device, not the heater")
async def test_action_not_heating_when_only_fan_runs(hass: HomeAssistant) -> None:
    """The action reports heating only when the heater runs."""
    await async_setup_thermostat(hass, temperature=25, fan=FAN, target_temp=20)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_toggle(hass, FAN, True)
    assert not is_on(hass, HEATER)
    assert thermostat(hass).attributes["hvac_action"] != HVACAction.HEATING


@pytest.mark.xfail(reason="#36: reverse_cycle leaves the cooler on and blocks the heater")
async def test_reverse_cycle_cool_to_heat(hass: HomeAssistant) -> None:
    """Switching cool -> heat on a reverse-cycle unit starts heating."""
    await async_setup_thermostat(hass, temperature=26, reverse_cycle="cooler, heater")
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    await async_call(hass, "set_temperature", temperature=22)
    assert is_on(hass, COOLER)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_temperature", temperature=28)
    assert is_on(hass, HEATER)


@pytest.mark.xfail(reason="#36: reverse_cycle device keeps running in the new mode")
async def test_reverse_cycle_cool_to_heat_without_demand(hass: HomeAssistant) -> None:
    """Switching cool -> heat when no heat is needed doesn't keep cooling."""
    await async_setup_thermostat(hass, temperature=26, reverse_cycle="cooler, heater")
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    await async_call(hass, "set_temperature", temperature=22)
    assert is_on(hass, COOLER)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert not is_on(hass, COOLER)


@pytest.mark.xfail(reason="keep_alive 'on' branch is unreachable for single modes")
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_keep_alive_resends_on_while_running(hass: HomeAssistant) -> None:
    """keep_alive repeats 'on' for a running device."""
    await async_setup_thermostat(hass, temperature=18, target_temp=22, keep_alive={"minutes": 5})
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert is_on(hass, HEATER)
    recorder = ServiceCallRecorder(hass)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5, seconds=1))
    await hass.async_block_till_done()
    assert ("turn_on", HEATER) in recorder.calls


@pytest.mark.xfail(reason="turn_on restores the mode *before* the last change")
async def test_turn_on_while_on_keeps_mode(hass: HomeAssistant) -> None:
    """climate.turn_on never turns the thermostat off."""
    await async_setup_thermostat(hass)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "turn_on")
    assert thermostat(hass).state == "heat"


@pytest.mark.xfail(reason="turn_on after a restart in off calls set_hvac_mode(None)")
async def test_turn_on_after_restart_in_off(hass: HomeAssistant) -> None:
    """climate.turn_on works after restarting in off."""
    await async_setup_restored(hass, "off", {"temperature": 21})
    await async_call(hass, "turn_on")
    assert thermostat(hass).state != "off"


@pytest.mark.xfail(reason="initial_hvac_mode is overwritten during startup")
async def test_initial_hvac_mode_on_first_start(hass: HomeAssistant) -> None:
    """initial_hvac_mode applies when there's no saved state."""
    await async_setup_thermostat(hass, initial_hvac_mode="heat", target_temp=21)
    assert thermostat(hass).state == "heat"


@pytest.mark.xfail(reason="restored mode isn't checked against configured devices")
async def test_restored_mode_must_still_exist(hass: HomeAssistant) -> None:
    """A saved mode whose device was removed from the config isn't restored."""
    await async_setup_restored(hass, "cool", {"temperature": 21}, cooler=None)
    state = thermostat(hass)
    assert state.state in state.attributes["hvac_modes"]


@pytest.mark.xfail(reason="#54: away does nothing in heat_cool")
async def test_away_in_heat_cool(hass: HomeAssistant) -> None:
    """Away applies the heater/cooler away temperatures to the range."""
    await async_setup_thermostat(
        hass, enable_heat_cool=True, away_temp_heater=16, away_temp_cooler=28
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    await async_call(hass, "set_temperature", target_temp_low=20, target_temp_high=24)
    await async_call(hass, "set_preset_mode", preset_mode="away")
    attributes = thermostat(hass).attributes
    assert (attributes["target_temp_low"], attributes["target_temp_high"]) == (16, 28)


@pytest.mark.xfail(reason="saved target before away isn't kept across restarts")
async def test_leave_away_after_restart(hass: HomeAssistant) -> None:
    """Leaving away after a restart doesn't jump to the cooler's away temperature."""
    await async_setup_restored(
        hass,
        "heat",
        {"temperature": 16, "preset_mode": "away"},
        away_temp_heater=16,
        away_temp_cooler=28,
    )
    await async_call(hass, "set_preset_mode", preset_mode="none")
    assert thermostat(hass).attributes["temperature"] != 28


@pytest.mark.xfail(reason="neutral fan/dryer re-sends turn_on on every sensor update")
async def test_neutral_fan_no_redundant_commands(hass: HomeAssistant) -> None:
    """A running neutral fan isn't sent turn_on again on each reading."""
    await async_setup_thermostat(hass, fan=FAN, fan_behavior="neutral")
    await async_call(hass, "set_hvac_mode", hvac_mode="fan_only")
    assert is_on(hass, FAN)
    recorder = ServiceCallRecorder(hass)
    for reading in (20.1, 20.2, 20.3):
        await async_set_temperature(hass, reading)
    assert recorder.calls == []


@pytest.mark.xfail(reason="neutral fan/dryer waits for a temperature it doesn't use")
async def test_neutral_fan_without_temperature(hass: HomeAssistant) -> None:
    """A neutral fan runs even before the sensor has reported."""
    await async_setup_thermostat(hass, temperature=None, fan=FAN, fan_behavior="neutral")
    await async_call(hass, "set_hvac_mode", hvac_mode="fan_only")
    assert is_on(hass, FAN)


@pytest.mark.xfail(reason="shared heater/cooler entity: hvac_action compares None")
async def test_shared_heater_cooler_without_temperature(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """A single entity used as heater and cooler doesn't crash state updates."""
    await async_setup_restored(
        hass,
        "heat_cool",
        {"target_temp_low": 20, "target_temp_high": 24},
        temperature="unavailable",
        cooler=HEATER,
        enable_heat_cool=True,
    )
    await async_toggle(hass, HEATER, True)
    assert "TypeError" not in caplog.text


@pytest.mark.xfail(reason="heat target can be set above the cool target")
async def test_heat_target_cannot_invert_range(hass: HomeAssistant) -> None:
    """Raising the heat target above the range's high end keeps the range valid."""
    await async_setup_thermostat(
        hass, enable_heat_cool=True, target_temp_low=20, target_temp_high=24
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_temperature", temperature=26)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    attributes = thermostat(hass).attributes
    assert attributes["target_temp_low"] <= attributes["target_temp_high"]


@pytest.mark.xfail(reason="restored dry mode uses fan_behavior to pick a default target")
async def test_restored_cooling_dryer_does_not_run_flat_out(hass: HomeAssistant) -> None:
    """A dryer acting as a cooler with no saved target doesn't chase min_temp."""
    await async_setup_restored(
        hass,
        "dry",
        {},
        temperature=25,
        dryer=DRYER,
        dryer_behavior="cooler",
        fan=FAN,
        fan_behavior="neutral",
    )
    await async_set_temperature(hass, 25.1)
    assert not is_on(hass, DRYER)


@pytest.mark.xfail(reason="min_cycle_duration in heat_cool only checks the heater")
async def test_heat_cool_min_cycle_protects_cooler(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """In heat_cool, a cooler that just stopped isn't restarted immediately."""
    await async_setup_thermostat(
        hass,
        temperature=25,
        enable_heat_cool=True,
        target_temp_low=20,
        target_temp_high=24,
        cold_tolerance=0.5,
        hot_tolerance=0.5,
        min_cycle_duration={"minutes": 10},
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    assert is_on(hass, COOLER)
    freezer.tick(timedelta(minutes=11))
    await async_set_temperature(hass, 23)
    assert not is_on(hass, COOLER)
    freezer.tick(timedelta(minutes=11))  # heater's last change is now old
    await async_set_temperature(hass, 25)
    assert is_on(hass, COOLER)  # fine: cooler was off long enough
    freezer.tick(timedelta(minutes=11))
    await async_set_temperature(hass, 23)
    assert not is_on(hass, COOLER)
    await async_set_temperature(hass, 25)  # cooler stopped seconds ago
    assert not is_on(hass, COOLER)


@pytest.mark.xfail(reason="old device's turn_off isn't awaited, so it still looks 'running'")
@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [("fan_only", "heat", "heater"), ("dry", "cool", "cooler")],
)
async def test_mode_switch_starts_new_device_immediately(
    hass: HomeAssistant, first: str, second: str, expected: str
) -> None:
    """The new mode's device starts without waiting for a sensor reading."""
    temperature = 21 if expected == "heater" else 23
    await async_setup_thermostat(
        hass, temperature=temperature, fan=FAN, dryer=DRYER, target_temp=22
    )
    await async_call(hass, "set_hvac_mode", hvac_mode=first)
    assert devices_on(hass) == {"fan" if first == "fan_only" else "dryer"}
    await async_call(hass, "set_hvac_mode", hvac_mode=second)
    assert devices_on(hass) == {expected}
