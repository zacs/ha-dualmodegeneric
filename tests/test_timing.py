"""min_cycle_duration and keep_alive."""

from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .common import (
    HEATER,
    ServiceCallRecorder,
    async_call,
    async_set_temperature,
    async_setup_thermostat,
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


# TODO(phase 1): track keep_alive with cancel_on_shutdown=True and drop this marker.
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_keep_alive_resends_off_while_idle(hass: HomeAssistant) -> None:
    """keep_alive repeats 'off' for an idle device (e.g. for lossy IR/RF switches)."""
    await async_setup_thermostat(hass, temperature=25, target_temp=22, keep_alive={"minutes": 5})
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    recorder = ServiceCallRecorder(hass)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5, seconds=1))
    await hass.async_block_till_done()
    assert ("turn_off", HEATER) in recorder.calls
