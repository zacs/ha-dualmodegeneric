"""The tamper entity and the water guard (both from PR #88)."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.climate import HVACAction, HVACMode
from homeassistant.core import HomeAssistant

from .common import (
    CONSENT,
    FAN,
    async_call,
    async_set_temperature,
    async_setup_thermostat,
    async_toggle,
    devices_on,
    thermostat,
)

WINDOW = "binary_sensor.window"
WATER = "sensor.water"
WATER_HEAT = "input_number.water_heat"


async def _set(hass: HomeAssistant, entity_id: str, state: str) -> None:
    hass.states.async_set(entity_id, state)
    await hass.async_block_till_done()


# ----------------------------------------------------------------------
# Tamper entity
# ----------------------------------------------------------------------


async def test_tamper_stops_and_resumes(hass: HomeAssistant) -> None:
    """While the tamper entity is on, everything is off and the mode is kept."""
    hass.states.async_set(WINDOW, "off")
    await async_setup_thermostat(hass, temperature=20, target_temp=22, tamper_entity=WINDOW)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == {"heater"}

    await _set(hass, WINDOW, "on")
    state = thermostat(hass)
    assert devices_on(hass) == set()
    assert state.state == HVACMode.HEAT
    assert state.attributes["hvac_action"] == HVACAction.IDLE

    await async_set_temperature(hass, 19)
    assert devices_on(hass) == set()

    await _set(hass, WINDOW, "off")
    assert devices_on(hass) == {"heater"}


async def test_tamper_unavailable_doesnt_block(hass: HomeAssistant) -> None:
    """Unlike consent, a tamper entity that's unavailable doesn't hold anything off."""
    hass.states.async_set(WINDOW, "unavailable")
    await async_setup_thermostat(hass, temperature=20, target_temp=22, tamper_entity=WINDOW)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == {"heater"}


async def test_tamper_on_at_startup(hass: HomeAssistant) -> None:
    """A tamper entity that's already on holds devices off from the start."""
    hass.states.async_set(WINDOW, "on")
    await async_setup_thermostat(
        hass, temperature=20, target_temp=22, initial_hvac_mode="heat", tamper_entity=WINDOW
    )
    assert devices_on(hass) == set()


async def test_tamper_and_consent_both_needed(hass: HomeAssistant) -> None:
    """Devices run only with consent and without tamper."""
    hass.states.async_set(WINDOW, "on")
    await async_setup_thermostat(
        hass, temperature=20, target_temp=22, tamper_entity=WINDOW, consent_entity=CONSENT
    )
    await async_toggle(hass, CONSENT, True)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == set()
    await _set(hass, WINDOW, "off")
    assert devices_on(hass) == {"heater"}
    await async_toggle(hass, CONSENT, False)
    assert devices_on(hass) == set()


# ----------------------------------------------------------------------
# Water guard
# ----------------------------------------------------------------------

WATER_CONFIG = {
    "target_temp": 22,
    "water_sensor": WATER,
    "water_setpoint_heat": 30,
    "water_setpoint_cool": 15,
    "water_tolerance": 1,
}


async def test_heater_waits_for_hot_water(hass: HomeAssistant) -> None:
    """The heater only runs once the water reaches water_setpoint_heat - tolerance."""
    hass.states.async_set(WATER, "25")
    await async_setup_thermostat(hass, temperature=20, **WATER_CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    state = thermostat(hass)
    assert devices_on(hass) == set()
    assert state.attributes["hvac_action"] == HVACAction.IDLE
    assert state.attributes["water_guard_active"] is True

    await _set(hass, WATER, "29")
    assert devices_on(hass) == {"heater"}
    assert thermostat(hass).attributes["water_guard_active"] is False


async def test_cooler_waits_for_cold_water(hass: HomeAssistant) -> None:
    """The cooler only runs while the water is at most water_setpoint_cool + tolerance."""
    hass.states.async_set(WATER, "17")
    await async_setup_thermostat(hass, temperature=25, **WATER_CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    assert devices_on(hass) == set()
    await _set(hass, WATER, "16")
    assert devices_on(hass) == {"cooler"}


async def test_guard_stops_a_running_device_at_once(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """When the water cools down, the heater stops without waiting for min_cycle_duration.

    Starting again still waits for it, so a water temperature hovering at the
    threshold can't make the device chatter.
    """
    hass.states.async_set(WATER, "35")
    await async_setup_thermostat(
        hass, temperature=20, min_cycle_duration={"minutes": 10}, **WATER_CONFIG
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == {"heater"}

    await _set(hass, WATER, "28")
    assert devices_on(hass) == set()

    await _set(hass, WATER, "29.5")
    assert devices_on(hass) == set()
    freezer.tick(timedelta(minutes=10, seconds=1))
    await _set(hass, WATER, "29.6")
    assert devices_on(hass) == {"heater"}


async def test_setpoint_entity_wins(hass: HomeAssistant) -> None:
    """An entity's setpoint takes priority over the fixed one, and keeps its last value."""
    hass.states.async_set(WATER, "33")
    hass.states.async_set(WATER_HEAT, "40")
    await async_setup_thermostat(
        hass, temperature=20, water_setpoint_heat_entity=WATER_HEAT, **WATER_CONFIG
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == set()
    assert thermostat(hass).attributes["water_setpoint_heat"] == 40

    await _set(hass, WATER_HEAT, "unavailable")
    assert thermostat(hass).attributes["water_setpoint_heat"] == 40
    await _set(hass, WATER_HEAT, "32")
    assert devices_on(hass) == {"heater"}


async def test_no_water_reading_doesnt_block(hass: HomeAssistant) -> None:
    """Without a water reading the guard holds nothing back."""
    await async_setup_thermostat(hass, temperature=20, **WATER_CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == {"heater"}
    assert thermostat(hass).attributes["water_temperature"] is None


async def test_guard_per_device_in_heat_cool(hass: HomeAssistant) -> None:
    """In heat/cool each device checks its own setpoint."""
    hass.states.async_set(WATER, "20")
    await async_setup_thermostat(
        hass,
        temperature=19,
        enable_heat_cool=True,
        target_temp_low=20,
        target_temp_high=24,
        **WATER_CONFIG,
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    assert devices_on(hass) == set()
    # Neither device could run at this water temperature, so the guard is active.
    assert thermostat(hass).attributes["water_guard_active"] is True

    await async_set_temperature(hass, 25)
    assert devices_on(hass) == set()
    await _set(hass, WATER, "14")
    assert devices_on(hass) == {"cooler"}


async def test_guard_applies_to_fan_by_behavior(hass: HomeAssistant) -> None:
    """A fan that heats (fan_behavior: heater) waits for hot water too."""
    hass.states.async_set(WATER, "25")
    await async_setup_thermostat(
        hass, temperature=20, fan=FAN, fan_behavior="heater", heater=None, **WATER_CONFIG
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="fan_only")
    assert devices_on(hass) == set()
    await _set(hass, WATER, "31")
    assert devices_on(hass) == {"fan"}


async def test_neutral_fan_not_guarded(hass: HomeAssistant) -> None:
    """A fan that just runs in its mode isn't held back by the water."""
    hass.states.async_set(WATER, "25")
    await async_setup_thermostat(hass, temperature=20, fan=FAN, **WATER_CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="fan_only")
    assert devices_on(hass) == {"fan"}
    assert thermostat(hass).attributes["water_guard_active"] is False


async def test_no_water_attributes_without_guard(hass: HomeAssistant) -> None:
    """The water attributes only appear when the guard is configured."""
    await async_setup_thermostat(hass)
    assert "water_temperature" not in thermostat(hass).attributes


async def test_tamper_clearing_respects_min_cycle(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A window flapping shut doesn't restart the compressor within min_cycle_duration."""
    hass.states.async_set(WINDOW, "off")
    await async_setup_thermostat(
        hass,
        temperature=26,
        target_temp=22,
        tamper_entity=WINDOW,
        min_cycle_duration={"minutes": 10},
    )
    freezer.tick(timedelta(minutes=11))
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    freezer.tick(timedelta(minutes=11))
    await _set(hass, WINDOW, "on")
    assert devices_on(hass) == set()

    freezer.tick(timedelta(seconds=20))
    await _set(hass, WINDOW, "off")
    assert devices_on(hass) == set()
    freezer.tick(timedelta(minutes=10))
    await async_set_temperature(hass, 26.1)
    assert devices_on(hass) == {"cooler"}
