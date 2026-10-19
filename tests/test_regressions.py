"""Regression tests for bugs fixed in 1.0.

Each reproduces a bug confirmed in 0.2.x (issue numbers in the comments), or
one found while reviewing the 1.0 rewrite (last section).
"""

from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.climate import HVACAction
from homeassistant.const import EVENT_CALL_SERVICE, EVENT_HOMEASSISTANT_START
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .common import (
    CONSENT,
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


# Fixed in 1.0: #84: single target isn't saved in heat_cool -> TypeError
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


# Fixed in 1.0: #83: heat_cool 'comfortable' band is empty for narrow ranges
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


# Fixed in 1.0: #28: any running device counts as 'running', so the fan blocks heat
async def test_running_fan_does_not_block_heater(hass: HomeAssistant) -> None:
    """A fan switched on for circulation doesn't stop heat mode from heating."""
    await async_setup_thermostat(hass, temperature=23, fan=FAN, target_temp=22)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_toggle(hass, FAN, True)
    await async_set_temperature(hass, 21)
    assert is_on(hass, HEATER)


# Fixed in 1.0: #28: hvac_action reflects any device, not the heater
async def test_action_not_heating_when_only_fan_runs(hass: HomeAssistant) -> None:
    """The action reports heating only when the heater runs."""
    await async_setup_thermostat(hass, temperature=25, fan=FAN, target_temp=20)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_toggle(hass, FAN, True)
    assert not is_on(hass, HEATER)
    assert thermostat(hass).attributes["hvac_action"] != HVACAction.HEATING


# Fixed in 1.0: #36: reverse_cycle leaves the cooler on and blocks the heater
async def test_reverse_cycle_cool_to_heat(hass: HomeAssistant) -> None:
    """Switching cool -> heat on a reverse-cycle unit starts heating."""
    await async_setup_thermostat(hass, temperature=26, reverse_cycle="cooler, heater")
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    await async_call(hass, "set_temperature", temperature=22)
    assert is_on(hass, COOLER)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_temperature", temperature=28)
    assert is_on(hass, HEATER)


# Fixed in 1.0: #36: reverse_cycle device keeps running in the new mode
async def test_reverse_cycle_cool_to_heat_without_demand(hass: HomeAssistant) -> None:
    """Switching cool -> heat when no heat is needed doesn't keep cooling."""
    await async_setup_thermostat(hass, temperature=26, reverse_cycle="cooler, heater")
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    await async_call(hass, "set_temperature", temperature=22)
    assert is_on(hass, COOLER)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert not is_on(hass, COOLER)


# Fixed in 1.0: keep_alive 'on' branch is unreachable for single modes
async def test_keep_alive_resends_on_while_running(hass: HomeAssistant) -> None:
    """keep_alive repeats 'on' for a running device."""
    await async_setup_thermostat(hass, temperature=18, target_temp=22, keep_alive={"minutes": 5})
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert is_on(hass, HEATER)
    recorder = ServiceCallRecorder(hass)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5, seconds=1))
    await hass.async_block_till_done()
    assert ("turn_on", HEATER) in recorder.calls


# Fixed in 1.0: turn_on restores the mode *before* the last change
async def test_turn_on_while_on_keeps_mode(hass: HomeAssistant) -> None:
    """climate.turn_on never turns the thermostat off."""
    await async_setup_thermostat(hass)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "turn_on")
    assert thermostat(hass).state == "heat"


# Fixed in 1.0: turn_on after a restart in off calls set_hvac_mode(None)
async def test_turn_on_after_restart_in_off(hass: HomeAssistant) -> None:
    """climate.turn_on works after restarting in off."""
    await async_setup_restored(hass, "off", {"temperature": 21})
    await async_call(hass, "turn_on")
    assert thermostat(hass).state != "off"


# Fixed in 1.0: initial_hvac_mode is overwritten during startup
async def test_initial_hvac_mode_on_first_start(hass: HomeAssistant) -> None:
    """initial_hvac_mode applies when there's no saved state."""
    await async_setup_thermostat(hass, initial_hvac_mode="heat", target_temp=21)
    assert thermostat(hass).state == "heat"


# Fixed in 1.0: restored mode isn't checked against configured devices
async def test_restored_mode_must_still_exist(hass: HomeAssistant) -> None:
    """A saved mode whose device was removed from the config isn't restored."""
    await async_setup_restored(hass, "cool", {"temperature": 21}, cooler=None)
    state = thermostat(hass)
    assert state.state in state.attributes["hvac_modes"]


# Fixed in 1.0: #54: away does nothing in heat_cool
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


# Fixed in 1.0: saved target before away isn't kept across restarts
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


# Fixed in 1.0: neutral fan/dryer re-sends turn_on on every sensor update
async def test_neutral_fan_no_redundant_commands(hass: HomeAssistant) -> None:
    """A running neutral fan isn't sent turn_on again on each reading."""
    await async_setup_thermostat(hass, fan=FAN, fan_behavior="neutral")
    await async_call(hass, "set_hvac_mode", hvac_mode="fan_only")
    assert is_on(hass, FAN)
    recorder = ServiceCallRecorder(hass)
    for reading in (20.1, 20.2, 20.3):
        await async_set_temperature(hass, reading)
    assert recorder.calls == []


# Fixed in 1.0: neutral fan/dryer waits for a temperature it doesn't use
async def test_neutral_fan_without_temperature(hass: HomeAssistant) -> None:
    """A neutral fan runs even before the sensor has reported."""
    await async_setup_thermostat(hass, temperature=None, fan=FAN, fan_behavior="neutral")
    await async_call(hass, "set_hvac_mode", hvac_mode="fan_only")
    assert is_on(hass, FAN)


# Fixed in 1.0: shared heater/cooler entity: hvac_action compares None
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


# Fixed in 1.0: heat target can be set above the cool target
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


# Fixed in 1.0: restored dry mode uses fan_behavior to pick a default target
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


# Fixed in 1.0: min_cycle_duration in heat_cool only checks the heater
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


# Fixed in 1.0: old device's turn_off isn't awaited, so it still looks 'running'
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


# --- Found in review of the 1.0 rewrite -------------------------------------
# A device with no integration behind it: commands are recorded, but its state
# only changes when the test says so (a lossy RF, Zigbee or Z-Wave switch).
RF_HEATER = "switch.rf_heater"


async def test_set_up_between_start_event_and_running(hass: HomeAssistant) -> None:
    """A platform that finishes loading after HA's start event still takes control."""
    hass.set_state(CoreState.starting)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
    await hass.async_block_till_done()
    await async_setup_thermostat(hass, temperature=25, target_temp=21)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_toggle(hass, HEATER, True)
    hass.set_state(CoreState.running)
    await async_set_temperature(hass, 26)
    assert not is_on(hass, HEATER)


async def test_heat_cool_min_cycle_never_runs_both(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """While min_cycle_duration keeps the heater on, the cooler doesn't start alongside it."""
    await async_setup_thermostat(
        hass,
        temperature=20.6,
        enable_heat_cool=True,
        target_temp_low=21,
        target_temp_high=22,
        min_cycle_duration={"minutes": 20},
    )
    freezer.tick(timedelta(minutes=30))
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    assert devices_on(hass) == {"heater"}
    freezer.tick(timedelta(minutes=10))
    await async_set_temperature(hass, 22.4)
    assert devices_on(hass) == {"heater"}

    # Once the heater may stop, the cooler takes over.
    freezer.tick(timedelta(minutes=10, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert devices_on(hass) == {"cooler"}


@pytest.mark.parametrize("new_mode", ["cool", "off"])
async def test_device_unavailable_during_mode_change(hass: HomeAssistant, new_mode: str) -> None:
    """A heater that missed its switch-off is turned off when it comes back."""
    hass.states.async_set(RF_HEATER, "off")
    await async_setup_thermostat(hass, temperature=18, heater=RF_HEATER, target_temp=22)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    hass.states.async_set(RF_HEATER, "on")
    hass.states.async_set(RF_HEATER, "unavailable")
    await hass.async_block_till_done()
    await async_call(hass, "set_hvac_mode", hvac_mode=new_mode)
    recorder = ServiceCallRecorder(hass)
    hass.states.async_set(RF_HEATER, "on")  # back, and still heating
    await hass.async_block_till_done()
    assert recorder.calls == [("turn_off", RF_HEATER)]

    # Once it reports off, the thermostat leaves it alone again.
    hass.states.async_set(RF_HEATER, "off")
    await hass.async_block_till_done()
    recorder.clear()
    await async_set_temperature(hass, 18.5)
    assert ("turn_off", RF_HEATER) not in recorder.calls


async def test_switch_to_off_resends_lost_turn_off(hass: HomeAssistant) -> None:
    """Switching to off re-sends a turn_off the device hasn't acted on yet."""
    hass.states.async_set(RF_HEATER, "off")
    await async_setup_thermostat(hass, temperature=18, heater=RF_HEATER, target_temp=22)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    hass.states.async_set(RF_HEATER, "on")
    await hass.async_block_till_done()
    recorder = ServiceCallRecorder(hass)
    await async_set_temperature(hass, 23)  # turn_off sent but lost
    await async_call(hass, "set_hvac_mode", hvac_mode="off")
    assert recorder.calls == [("turn_off", RF_HEATER)] * 2


async def test_off_mode_keeps_finishing_the_switch_off(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """In off mode a device still on after the switch to off gets it re-sent."""
    hass.states.async_set(RF_HEATER, "on")
    await async_setup_thermostat(hass, temperature=18, heater=RF_HEATER, target_temp=22)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    recorder = ServiceCallRecorder(hass)
    await async_call(hass, "set_hvac_mode", hvac_mode="off")
    freezer.tick(timedelta(seconds=11))
    await async_set_temperature(hass, 18.1)
    assert recorder.calls == [("turn_off", RF_HEATER)] * 2


async def test_lost_turn_off_not_held_by_min_cycle(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """min_cycle_duration counts from real changes, so a lost turn_off is retried promptly."""
    hass.states.async_set(RF_HEATER, "off")
    await async_setup_thermostat(
        hass, temperature=18, heater=RF_HEATER, target_temp=22, min_cycle_duration={"minutes": 20}
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    hass.states.async_set(RF_HEATER, "on")
    await hass.async_block_till_done()
    freezer.tick(timedelta(minutes=30))
    recorder = ServiceCallRecorder(hass)
    await async_set_temperature(hass, 23)  # lost
    freezer.tick(timedelta(seconds=30))
    await async_set_temperature(hass, 23.1)
    assert recorder.calls == [("turn_off", RF_HEATER)] * 2


async def test_reverse_cycle_needs_a_reverse_cycle_successor(hass: HomeAssistant) -> None:
    """A separate fan taking over doesn't count as the reverse-cycle unit switching over."""
    await async_setup_thermostat(
        hass, temperature=18, target_temp=22, fan=FAN, reverse_cycle="heater, cooler"
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert is_on(hass, HEATER)
    await async_call(hass, "set_hvac_mode", hvac_mode="fan_only")
    assert devices_on(hass) == {"fan"}


async def test_reverse_cycle_device_recommanded_after_handover(hass: HomeAssistant) -> None:
    """A device that handed over (and may still read on) is told to start again later."""
    await async_setup_thermostat(
        hass, temperature=26, target_temp=22, reverse_cycle="cooler, heater"
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    await async_call(hass, "set_temperature", temperature=28, hvac_mode="heat")
    assert is_on(hass, COOLER)  # an optimistic template switch keeps reading on
    assert thermostat(hass).attributes["hvac_action"] == HVACAction.HEATING

    recorder = ServiceCallRecorder(hass)
    await async_call(hass, "set_temperature", temperature=22, hvac_mode="cool")
    assert recorder.calls == [("turn_on", COOLER)]


async def test_shared_entity_kept_across_mode_change(hass: HomeAssistant) -> None:
    """Leaving heat_cool for heat doesn't switch off an entity heat mode still uses."""
    await async_setup_thermostat(
        hass,
        temperature=None,
        cooler=HEATER,
        enable_heat_cool=True,
        target_temp_low=20,
        target_temp_high=24,
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    await async_toggle(hass, HEATER, True)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert is_on(hass, HEATER)


async def test_keep_alive_skips_unavailable(hass: HomeAssistant) -> None:
    """keep_alive doesn't send commands to unavailable devices."""
    hass.states.async_set(RF_HEATER, "unavailable")
    await async_setup_thermostat(
        hass, temperature=25, heater=RF_HEATER, target_temp=22, keep_alive={"minutes": 5}
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    recorder = ServiceCallRecorder(hass)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5, seconds=1))
    await hass.async_block_till_done()
    assert recorder.calls == []


async def test_consent_revoked_in_off_mode_stops_devices(hass: HomeAssistant) -> None:
    """Revoking consent turns everything off in any mode, as in 0.2.x."""
    await async_setup_thermostat(hass, consent_entity=CONSENT)
    await async_toggle(hass, CONSENT, True)
    await async_toggle(hass, HEATER, True)  # switched on by hand while off
    await async_toggle(hass, CONSENT, False)
    assert devices_on(hass) == set()


# Commands still on their way to a slow device.
RF_COOLER = "switch.rf_cooler"


async def test_switch_to_off_cancels_turn_on_in_flight(hass: HomeAssistant) -> None:
    """Off right after heat: a turn_on that hasn't landed yet is countered."""
    hass.states.async_set(RF_HEATER, "off")
    await async_setup_thermostat(hass, temperature=18, heater=RF_HEATER, target_temp=22)
    recorder = ServiceCallRecorder(hass)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_hvac_mode", hvac_mode="off")
    assert recorder.calls == [("turn_on", RF_HEATER), ("turn_off", RF_HEATER)]


async def test_lowered_target_cancels_turn_on_in_flight(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Raising then lowering the target quickly ends with the heater told to stop."""
    hass.states.async_set(RF_HEATER, "off")
    await async_setup_thermostat(
        hass, temperature=20, heater=RF_HEATER, target_temp=19, min_cycle_duration={"minutes": 20}
    )
    freezer.tick(timedelta(minutes=30))
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    recorder = ServiceCallRecorder(hass)
    await async_call(hass, "set_temperature", temperature=24)
    await async_call(hass, "set_temperature", temperature=19)
    assert recorder.calls == [("turn_on", RF_HEATER), ("turn_off", RF_HEATER)]

    # The turn_on lands late and the turn_off is lost: re-asserting what the
    # user asked for isn't held back by min_cycle_duration.
    hass.states.async_set(RF_HEATER, "on")
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=11))
    await async_set_temperature(hass, 20.1)
    assert recorder.calls[-1] == ("turn_off", RF_HEATER)
    assert len(recorder.calls) == 3


async def test_heat_cool_no_cooler_while_heater_turn_on_in_flight(hass: HomeAssistant) -> None:
    """A range change right after a heater turn_on doesn't start the cooler alongside it."""
    hass.states.async_set(RF_HEATER, "off")
    hass.states.async_set(RF_COOLER, "off")
    await async_setup_thermostat(
        hass,
        temperature=19,
        heater=RF_HEATER,
        cooler=RF_COOLER,
        enable_heat_cool=True,
        target_temp_low=20,
        target_temp_high=24,
    )
    recorder = ServiceCallRecorder(hass)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    await async_call(hass, "set_temperature", target_temp_low=16, target_temp_high=18)
    assert recorder.calls == [
        ("turn_on", RF_HEATER),
        ("turn_off", RF_HEATER),
        ("turn_on", RF_COOLER),
    ]


async def test_device_echo_does_not_loop(hass: HomeAssistant) -> None:
    """A device answering turn_off by re-reporting 'on' (new attributes) isn't flooded."""
    hass.states.async_set(RF_HEATER, "off")
    await async_setup_thermostat(hass, temperature=18, heater=RF_HEATER, target_temp=22)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    hass.states.async_set(RF_HEATER, "on", {"n": 0})
    await hass.async_block_till_done()
    count = 0

    @callback
    def echo(event: Event) -> None:
        nonlocal count
        if event.data["domain"] == "homeassistant" and event.data["service"] == "turn_off":
            count += 1
            if count < 50:
                hass.loop.call_soon(hass.states.async_set, RF_HEATER, "on", {"n": count})

    hass.bus.async_listen(EVENT_CALL_SERVICE, echo)
    await async_call(hass, "set_hvac_mode", hvac_mode="off")
    for _ in range(10):
        await hass.async_block_till_done()
    assert count == 1


async def test_handed_over_device_not_powered_off(hass: HomeAssistant) -> None:
    """A reverse_cycle device that handed over isn't sent 'off' while its unit runs."""
    await async_setup_thermostat(
        hass,
        temperature=26,
        target_temp=28,
        enable_heat_cool=True,
        target_temp_low=20,
        reverse_cycle="heater, cooler",
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_temperature", temperature=22, hvac_mode="cool")
    assert is_on(hass, COOLER)
    recorder = ServiceCallRecorder(hass)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    assert ("turn_off", HEATER) not in recorder.calls

    # Switching everything off still switches it off.
    await async_call(hass, "set_hvac_mode", hvac_mode="off")
    assert devices_on(hass) == set()
