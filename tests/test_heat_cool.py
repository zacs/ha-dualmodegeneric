"""Heat/cool (range) mode with a wide range.

Range 20-24 with 0.5 tolerances: heating runs between 19.5 and 20.5, cooling
between 24.5 and 23.5, and nothing runs in between.
"""

from homeassistant.components.climate import HVACAction
from homeassistant.core import HomeAssistant

from .common import (
    COOLER,
    HEATER,
    async_call,
    async_set_temperature,
    async_setup_thermostat,
    devices_on,
    is_on,
    thermostat,
)

RANGE = {
    "enable_heat_cool": True,
    "target_temp_low": 20,
    "target_temp_high": 24,
    "cold_tolerance": 0.5,
    "hot_tolerance": 0.5,
}


async def _heat_cool(hass: HomeAssistant, temperature: float) -> None:
    await async_setup_thermostat(hass, temperature=temperature, **RANGE)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")


async def test_configured_range_is_default(hass: HomeAssistant) -> None:
    """target_temp_low/high from YAML are the initial range."""
    await _heat_cool(hass, 22)
    attributes = thermostat(hass).attributes
    assert (attributes["target_temp_low"], attributes["target_temp_high"]) == (20, 24)
    # A single target isn't used (or shown) in range mode.
    assert attributes["temperature"] is None


async def test_idle_inside_range(hass: HomeAssistant) -> None:
    """Nothing runs while the temperature is inside the range."""
    await _heat_cool(hass, 22)
    for reading in (19.6, 20, 22, 24, 24.4):
        await async_set_temperature(hass, reading)
        assert devices_on(hass) == set()
        assert thermostat(hass).attributes["hvac_action"] == HVACAction.IDLE


async def test_heating_cycle(hass: HomeAssistant) -> None:
    """Heat starts at low - cold_tolerance and stops at low + hot_tolerance."""
    await _heat_cool(hass, 22)
    await async_set_temperature(hass, 19.5)
    assert devices_on(hass) == {"heater"}
    assert thermostat(hass).attributes["hvac_action"] == HVACAction.HEATING

    await async_set_temperature(hass, 20.4)
    assert devices_on(hass) == {"heater"}
    await async_set_temperature(hass, 20.5)
    assert devices_on(hass) == set()


async def test_cooling_cycle(hass: HomeAssistant) -> None:
    """Cool starts at high + hot_tolerance and stops at high - cold_tolerance."""
    await _heat_cool(hass, 22)
    await async_set_temperature(hass, 24.5)
    assert devices_on(hass) == {"cooler"}
    assert thermostat(hass).attributes["hvac_action"] == HVACAction.COOLING

    await async_set_temperature(hass, 23.6)
    assert devices_on(hass) == {"cooler"}
    await async_set_temperature(hass, 23.5)
    assert devices_on(hass) == set()


async def test_starts_heating_or_cooling_when_entering_mode(hass: HomeAssistant) -> None:
    """Entering heat_cool acts on the current temperature right away."""
    await _heat_cool(hass, 18)
    assert devices_on(hass) == {"heater"}
    await async_call(hass, "set_hvac_mode", hvac_mode="off")
    await async_set_temperature(hass, 26)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    assert devices_on(hass) == {"cooler"}


async def test_set_range(hass: HomeAssistant) -> None:
    """A new range is applied immediately."""
    await _heat_cool(hass, 22)
    await async_call(hass, "set_temperature", target_temp_low=23, target_temp_high=26)
    attributes = thermostat(hass).attributes
    assert (attributes["target_temp_low"], attributes["target_temp_high"]) == (23, 26)
    assert devices_on(hass) == {"heater"}


async def test_heat_setpoint_becomes_range_low(hass: HomeAssistant) -> None:
    """A target set in heat mode carries over as the low end of the range."""
    await _heat_cool(hass, 22)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_temperature", temperature=21)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    attributes = thermostat(hass).attributes
    assert (attributes["target_temp_low"], attributes["target_temp_high"]) == (21, 24)


async def test_cool_setpoint_becomes_range_high(hass: HomeAssistant) -> None:
    """A target set in cool mode carries over as the high end of the range."""
    await _heat_cool(hass, 22)
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    await async_call(hass, "set_temperature", temperature=25)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    attributes = thermostat(hass).attributes
    assert (attributes["target_temp_low"], attributes["target_temp_high"]) == (20, 25)


async def test_never_heats_and_cools_at_once(hass: HomeAssistant) -> None:
    """Sweeping through the whole scale never runs both devices together."""
    await _heat_cool(hass, 22)
    for reading in (*range(15, 30), *range(30, 14, -1)):
        await async_set_temperature(hass, reading)
        assert not (is_on(hass, HEATER) and is_on(hass, COOLER))
