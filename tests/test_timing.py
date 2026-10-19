"""min_cycle_duration and keep_alive."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .common import (
    COOLER,
    HEATER,
    ServiceCallRecorder,
    async_call,
    async_set_temperature,
    async_setup_restored,
    async_setup_thermostat,
    devices_on,
    is_on,
)

CONFIG = {
    "target_temp": 22,
    "cold_tolerance": 0.5,
    "hot_tolerance": 0.5,
    "min_cycle_duration": {"minutes": 10},
}


async def test_min_cycle_keeps_device_on(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A device that just started isn't stopped before min_cycle_duration."""
    await async_setup_thermostat(hass, temperature=21, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert is_on(hass, HEATER)

    await async_set_temperature(hass, 23)
    assert is_on(hass, HEATER)

    freezer.tick(timedelta(minutes=11))
    await async_set_temperature(hass, 23.1)
    assert not is_on(hass, HEATER)


async def test_min_cycle_keeps_device_off(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A device that just stopped isn't restarted before min_cycle_duration."""
    await async_setup_thermostat(hass, temperature=21, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    freezer.tick(timedelta(minutes=11))
    await async_set_temperature(hass, 23)
    assert not is_on(hass, HEATER)

    await async_set_temperature(hass, 20)
    assert not is_on(hass, HEATER)

    freezer.tick(timedelta(minutes=11))
    await async_set_temperature(hass, 19.9)
    assert is_on(hass, HEATER)


async def test_user_actions_bypass_min_cycle(hass: HomeAssistant) -> None:
    """Changing the target or the mode acts immediately."""
    await async_setup_thermostat(hass, temperature=21, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert is_on(hass, HEATER)
    await async_call(hass, "set_temperature", temperature=19)
    assert not is_on(hass, HEATER)
    await async_call(hass, "set_temperature", temperature=24)
    assert is_on(hass, HEATER)
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    assert not is_on(hass, HEATER)


async def test_keep_alive_resends_off_while_idle(hass: HomeAssistant) -> None:
    """keep_alive repeats 'off' for an idle device (e.g. for lossy IR/RF switches)."""
    await async_setup_thermostat(hass, temperature=25, target_temp=22, keep_alive={"minutes": 5})
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    recorder = ServiceCallRecorder(hass)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5, seconds=1))
    await hass.async_block_till_done()
    assert ("turn_off", HEATER) in recorder.calls


async def test_min_cycle_rechecks_on_its_own(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A change held back by min_cycle_duration happens when it expires, not at the next reading."""
    await async_setup_thermostat(hass, temperature=21, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_set_temperature(hass, 23)
    assert is_on(hass, HEATER)

    freezer.tick(timedelta(minutes=10, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not is_on(hass, HEATER)


async def test_min_cycle_applies_per_device(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Each device has its own timer: a heater that just stopped doesn't hold up the cooler."""
    await async_setup_thermostat(
        hass,
        temperature=19,
        enable_heat_cool=True,
        target_temp_low=20,
        target_temp_high=24,
        cold_tolerance=0.5,
        hot_tolerance=0.5,
        min_cycle_duration={"minutes": 10},
    )
    freezer.tick(timedelta(minutes=11))  # devices have been off long enough
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    freezer.tick(timedelta(minutes=11))
    await async_set_temperature(hass, 25)  # heater ran long enough; cooler was off long enough
    assert devices_on(hass) == {"cooler"}


async def test_keep_alive_in_heat_cool(hass: HomeAssistant) -> None:
    """In heat_cool, keep_alive repeats the state of both devices."""
    await async_setup_thermostat(
        hass,
        temperature=22,
        enable_heat_cool=True,
        target_temp_low=20,
        target_temp_high=24,
        keep_alive={"minutes": 5},
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    recorder = ServiceCallRecorder(hass)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5, seconds=1))
    await hass.async_block_till_done()
    assert sorted(recorder.calls) == [("turn_off", COOLER), ("turn_off", HEATER)]


async def test_keep_alive_does_nothing_when_off(hass: HomeAssistant) -> None:
    """Off leaves devices entirely alone, keep_alive included."""
    await async_setup_thermostat(hass, temperature=25, keep_alive={"minutes": 5})
    recorder = ServiceCallRecorder(hass)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5, seconds=1))
    await hass.async_block_till_done()
    assert recorder.calls == []


async def test_max_cycle_stops_a_long_run(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A device is stopped after max_cycle_duration even if it's still needed."""
    await async_setup_thermostat(
        hass, temperature=18, target_temp=22, max_cycle_duration={"minutes": 30}
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert is_on(hass, HEATER)

    freezer.tick(timedelta(minutes=30, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not is_on(hass, HEATER)

    # Without a cooldown it starts again with the next reading.
    await async_set_temperature(hass, 18.1)
    assert is_on(hass, HEATER)


async def test_cooldown_after_max_cycle(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """max_cycle_duration with cycle_cooldown makes the device rest, then resume."""
    await async_setup_thermostat(
        hass,
        temperature=18,
        target_temp=22,
        max_cycle_duration={"minutes": 30},
        cycle_cooldown={"minutes": 10},
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    freezer.tick(timedelta(minutes=30, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not is_on(hass, HEATER)

    await async_set_temperature(hass, 18.1)
    assert not is_on(hass, HEATER)

    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert is_on(hass, HEATER)


async def test_cooldown_holds_a_restart(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """After stopping, a device waits cycle_cooldown before starting again."""
    await async_setup_thermostat(
        hass,
        temperature=21,
        target_temp=22,
        cold_tolerance=0.5,
        hot_tolerance=0.5,
        cycle_cooldown={"minutes": 10},
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_set_temperature(hass, 23)
    assert not is_on(hass, HEATER)

    await async_set_temperature(hass, 21)
    assert not is_on(hass, HEATER)

    freezer.tick(timedelta(minutes=10, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert is_on(hass, HEATER)


async def test_user_actions_bypass_cooldown(hass: HomeAssistant) -> None:
    """Changing the target starts a resting device straight away."""
    await async_setup_thermostat(
        hass,
        temperature=21,
        target_temp=22,
        cold_tolerance=0.5,
        hot_tolerance=0.5,
        cycle_cooldown={"minutes": 10},
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_set_temperature(hass, 23)
    await async_call(hass, "set_temperature", temperature=25)
    assert is_on(hass, HEATER)


async def test_cooldown_doesnt_hold_up_startup(hass: HomeAssistant) -> None:
    """After a restart, a device that's needed starts without waiting for the cooldown."""
    await async_setup_restored(
        hass, "heat", temperature=20, target_temp=22, cycle_cooldown={"minutes": 10}
    )
    assert is_on(hass, HEATER)
