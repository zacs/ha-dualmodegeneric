"""Fan modes: the fan running alongside the heater or cooler (#11)."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.climate import HVACAction
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .common import (
    CONSENT,
    FAN,
    HEATER,
    ServiceCallRecorder,
    async_call,
    async_set_temperature,
    async_setup_restored,
    async_setup_thermostat,
    async_toggle,
    devices_on,
    thermostat,
)

RF_HEATER = "switch.rf_heater"
RF_FAN = "switch.rf_fan"
CONFIG = {
    "fan": FAN,
    "fan_with": "heater",
    "target_temp": 22,
    "cold_tolerance": 0.5,
    "hot_tolerance": 0.5,
}


async def test_fan_modes_offered(hass: HomeAssistant) -> None:
    """fan_with adds the auto, on and off fan modes, starting in auto."""
    await async_setup_thermostat(hass, **CONFIG)
    attributes = thermostat(hass).attributes
    assert attributes["fan_modes"] == ["auto", "on", "off"]
    assert attributes["fan_mode"] == "auto"


async def test_no_fan_modes_without_fan_with(hass: HomeAssistant) -> None:
    """Without fan_with there's no fan mode, as before."""
    await async_setup_thermostat(hass, fan=FAN)
    assert "fan_modes" not in thermostat(hass).attributes


async def test_auto_runs_fan_with_heater(hass: HomeAssistant) -> None:
    """In auto, the fan starts and stops with the heater."""
    await async_setup_thermostat(hass, temperature=21, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == {"heater", "fan"}
    assert thermostat(hass).attributes["hvac_action"] == HVACAction.HEATING

    await async_set_temperature(hass, 23)
    assert devices_on(hass) == set()


async def test_fan_off_delay(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """fan_off_delay keeps the fan running for a while after the heater stops."""
    await async_setup_thermostat(hass, temperature=21, fan_off_delay={"minutes": 3}, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_set_temperature(hass, 23)
    assert devices_on(hass) == {"fan"}
    assert thermostat(hass).attributes["hvac_action"] == HVACAction.FAN

    freezer.tick(timedelta(minutes=3, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert devices_on(hass) == set()


async def test_fan_off_delay_restarts_with_heater(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """If the heater starts again during the delay, the fan just keeps running."""
    await async_setup_thermostat(hass, temperature=21, fan_off_delay={"minutes": 3}, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_set_temperature(hass, 23)
    freezer.tick(timedelta(minutes=2))
    await async_set_temperature(hass, 21)
    assert devices_on(hass) == {"heater", "fan"}

    freezer.tick(timedelta(minutes=2))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert devices_on(hass) == {"heater", "fan"}


async def test_on_runs_fan_continuously(hass: HomeAssistant) -> None:
    """The on fan mode runs the fan while the heater cycles."""
    await async_setup_thermostat(hass, temperature=23, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == set()

    await async_call(hass, "set_fan_mode", fan_mode="on")
    assert devices_on(hass) == {"fan"}
    assert thermostat(hass).attributes["hvac_action"] == HVACAction.FAN
    await async_set_temperature(hass, 21)
    assert devices_on(hass) == {"heater", "fan"}
    await async_set_temperature(hass, 23)
    assert devices_on(hass) == {"fan"}


async def test_on_runs_fan_in_other_modes(hass: HomeAssistant) -> None:
    """On runs the fan in cool mode too, though it only follows the heater in auto."""
    await async_setup_thermostat(hass, temperature=22, **CONFIG)
    await async_call(hass, "set_fan_mode", fan_mode="on")
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    assert devices_on(hass) == {"fan"}


async def test_switching_fan_mode_off_stops_the_fan(hass: HomeAssistant) -> None:
    """Choosing off stops a fan the fan mode was running; then it's left alone."""
    await async_setup_thermostat(hass, temperature=21, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_fan_mode", fan_mode="off")
    assert devices_on(hass) == {"heater"}

    await async_toggle(hass, FAN, True)
    await async_set_temperature(hass, 23)
    assert devices_on(hass) == {"fan"}


async def test_auto_leaves_fan_alone_without_device_to_follow(hass: HomeAssistant) -> None:
    """In cool mode, a fan that only follows the heater is left alone in auto."""
    await async_setup_thermostat(hass, temperature=25, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    await async_toggle(hass, FAN, True)
    await async_set_temperature(hass, 26)
    assert devices_on(hass) == {"cooler", "fan"}


async def test_fan_follows_device_switched_by_hand(hass: HomeAssistant) -> None:
    """In auto, the fan follows the heater even when someone else switches it."""
    await async_setup_thermostat(hass, temperature=21, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_toggle(hass, HEATER, False)
    assert devices_on(hass) == set()


async def test_fan_only_mode_ignores_fan_mode(hass: HomeAssistant) -> None:
    """Fan only mode runs the fan as its own device, by fan_behavior."""
    await async_setup_thermostat(hass, temperature=21, fan_behavior="cooler", **CONFIG)
    await async_call(hass, "set_fan_mode", fan_mode="on")
    await async_call(hass, "set_hvac_mode", hvac_mode="fan_only")
    assert devices_on(hass) == set()


async def test_leaving_to_off_stops_the_fan(hass: HomeAssistant) -> None:
    """Off mode stops everything, the fan included."""
    await async_setup_thermostat(hass, temperature=21, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_hvac_mode", hvac_mode="off")
    assert devices_on(hass) == set()


async def test_fan_stops_without_consent(hass: HomeAssistant) -> None:
    """Revoking consent stops the fan too, even in the on fan mode."""
    await async_setup_thermostat(hass, temperature=21, consent_entity=CONSENT, **CONFIG)
    await async_toggle(hass, CONSENT, True)
    await async_call(hass, "set_fan_mode", fan_mode="on")
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == {"heater", "fan"}
    await async_toggle(hass, CONSENT, False)
    assert devices_on(hass) == set()


async def test_fan_mode_restored(hass: HomeAssistant) -> None:
    """The fan mode survives a restart."""
    await async_setup_restored(hass, "heat", {"fan_mode": "on"}, temperature=23, **CONFIG)
    assert thermostat(hass).attributes["fan_mode"] == "on"
    assert devices_on(hass) == {"fan"}


async def test_fan_with_reverse_cycle_fan_is_ignored(hass: HomeAssistant) -> None:
    """A reverse-cycle fan is the same unit as the heater, so it can't run alongside it."""
    await async_setup_thermostat(hass, reverse_cycle="heater, fan", **CONFIG)
    assert "fan_modes" not in thermostat(hass).attributes


async def test_fan_mode_change_doesnt_skip_min_cycle(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """Changing the fan mode only acts on the fan; the heater's timing still holds."""
    await async_setup_thermostat(hass, temperature=21, min_cycle_duration={"minutes": 10}, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_set_temperature(hass, 23)
    assert devices_on(hass) == {"heater", "fan"}  # min_cycle_duration holds the heater

    await async_call(hass, "set_fan_mode", fan_mode="off")
    assert devices_on(hass) == {"heater"}


# Found in review.


async def test_off_delay_not_replayed_after_off_mode(hass: HomeAssistant) -> None:
    """A fan that followed the heater before off doesn't run its delay on returning to heat."""
    await async_setup_thermostat(hass, temperature=21, fan_off_delay={"minutes": 3}, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_hvac_mode", hvac_mode="off")
    await async_set_temperature(hass, 23)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == set()


async def test_off_delay_not_replayed_after_consent(hass: HomeAssistant) -> None:
    """Nor after consent was revoked and granted again."""
    await async_setup_thermostat(
        hass, temperature=21, fan_off_delay={"minutes": 3}, consent_entity=CONSENT, **CONFIG
    )
    await async_toggle(hass, CONSENT, True)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_toggle(hass, CONSENT, False)
    await async_set_temperature(hass, 23)
    await async_toggle(hass, CONSENT, True)
    assert devices_on(hass) == set()


async def test_off_delay_not_replayed_after_fan_mode_off(hass: HomeAssistant) -> None:
    """Nor after the fan mode was off while the heater stopped."""
    await async_setup_thermostat(hass, temperature=21, fan_off_delay={"minutes": 3}, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_fan_mode", fan_mode="off")
    await async_set_temperature(hass, 23)
    await async_call(hass, "set_fan_mode", fan_mode="auto")
    assert devices_on(hass) == set()


async def test_fan_starts_with_heater_despite_own_min_cycle(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A heater that needs airflow never runs without its fan.

    With fan_off_delay the fan stops later than the heater, so the fan's own
    min_cycle_duration would otherwise hold it off after the heater restarts.
    """
    await async_setup_thermostat(
        hass,
        temperature=21,
        fan_off_delay={"minutes": 3},
        min_cycle_duration={"minutes": 10},
        **CONFIG,
    )
    freezer.tick(timedelta(minutes=11))
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    freezer.tick(timedelta(minutes=11))
    await async_set_temperature(hass, 23)
    freezer.tick(timedelta(minutes=3, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert devices_on(hass) == set()

    freezer.tick(timedelta(minutes=7))  # the heater may start; the fan's own timer still runs
    await async_set_temperature(hass, 21)
    assert devices_on(hass) == {"heater", "fan"}


async def test_mode_change_doesnt_repeat_turn_off(hass: HomeAssistant) -> None:
    """The fan pass doesn't resend an off still on its way to another device."""
    hass.states.async_set(RF_HEATER, "off")
    await async_setup_thermostat(
        hass, temperature=18, heater=RF_HEATER, fan=FAN, fan_with="heater, cooler", target_temp=22
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    hass.states.async_set(RF_HEATER, "on")
    await hass.async_block_till_done()
    recorder = ServiceCallRecorder(hass)
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    assert recorder.calls.count(("turn_off", RF_HEATER)) == 1

    # Changing the fan mode only acts on the fan.
    recorder.clear()
    await async_call(hass, "set_fan_mode", fan_mode="on")
    assert ("turn_off", RF_HEATER) not in recorder.calls


async def test_fan_released_while_unavailable(hass: HomeAssistant) -> None:
    """A fan let go while unavailable is turned off when it comes back on."""
    hass.states.async_set(RF_FAN, "off")
    await async_setup_thermostat(
        hass, temperature=23, fan=RF_FAN, fan_with="heater", target_temp=22
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_fan_mode", fan_mode="on")
    hass.states.async_set(RF_FAN, "on")
    hass.states.async_set(RF_FAN, "unavailable")
    await hass.async_block_till_done()
    await async_call(hass, "set_fan_mode", fan_mode="off")
    recorder = ServiceCallRecorder(hass)
    hass.states.async_set(RF_FAN, "on")
    await hass.async_block_till_done()
    assert recorder.calls == [("turn_off", RF_FAN)]


async def test_fan_released_lost_turn_off_retried(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A turn_off the fan missed is sent again."""
    hass.states.async_set(RF_FAN, "off")
    await async_setup_thermostat(
        hass, temperature=23, fan=RF_FAN, fan_with="heater", target_temp=22
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_fan_mode", fan_mode="on")
    hass.states.async_set(RF_FAN, "on")
    await hass.async_block_till_done()
    recorder = ServiceCallRecorder(hass)
    await async_call(hass, "set_fan_mode", fan_mode="off")  # the fan misses it
    freezer.tick(timedelta(seconds=11))
    await async_set_temperature(hass, 23.1)
    assert recorder.calls == [("turn_off", RF_FAN)] * 2
