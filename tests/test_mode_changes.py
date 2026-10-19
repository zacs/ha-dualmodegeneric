"""Switching between modes, and turning the thermostat on and off."""

import pytest
from homeassistant.components.climate import HVACAction, HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .common import (
    DRYER,
    FAN,
    async_call,
    async_set_temperature,
    async_setup_thermostat,
    devices_on,
    thermostat,
)

CONFIG = {
    "fan": FAN,
    "dryer": DRYER,
    "target_temp": 22,
    "cold_tolerance": 0.5,
    "hot_tolerance": 0.5,
}


async def test_heat_to_cool(hass: HomeAssistant) -> None:
    """Leaving heat stops the heater; cool then acts on its own."""
    await async_setup_thermostat(hass, temperature=21, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == {"heater"}
    await async_set_temperature(hass, 21.4)
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    assert devices_on(hass) == set()
    await async_set_temperature(hass, 23)
    assert devices_on(hass) == {"cooler"}


async def test_cool_to_heat(hass: HomeAssistant) -> None:
    """Leaving cool stops the cooler and starts the heater when needed."""
    await async_setup_thermostat(hass, temperature=23, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    assert devices_on(hass) == {"cooler"}
    await async_call(hass, "set_temperature", temperature=25)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == {"heater"}


async def test_heat_to_fan_and_back(hass: HomeAssistant) -> None:
    """Fan-only replaces the heater, and heat replaces the fan."""
    await async_setup_thermostat(hass, temperature=21, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == {"heater"}
    await async_call(hass, "set_hvac_mode", hvac_mode="fan_only")
    assert devices_on(hass) == {"fan"}
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == {"heater"}


async def test_dry_to_cool(hass: HomeAssistant) -> None:
    """Leaving dry stops the dryer."""
    await async_setup_thermostat(hass, temperature=23, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="dry")
    assert devices_on(hass) == {"dryer"}
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    assert devices_on(hass) == {"cooler"}


async def test_off_stops_everything(hass: HomeAssistant) -> None:
    """Off turns every device off, including reverse_cycle ones."""
    await async_setup_thermostat(
        hass, temperature=21, reverse_cycle="heater, cooler, fan, dryer", **CONFIG
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == {"heater"}
    await async_call(hass, "set_hvac_mode", hvac_mode="off")
    assert devices_on(hass) == set()
    state = thermostat(hass)
    assert state.state == HVACMode.OFF
    assert state.attributes["hvac_action"] == HVACAction.OFF


async def test_turn_off_service(hass: HomeAssistant) -> None:
    """climate.turn_off switches to off."""
    await async_setup_thermostat(hass, temperature=21, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "turn_off")
    assert thermostat(hass).state == HVACMode.OFF
    assert devices_on(hass) == set()


async def test_turn_on_restores_previous_mode(hass: HomeAssistant) -> None:
    """climate.turn_on returns to the mode that was active before off."""
    await async_setup_thermostat(hass, temperature=23, **CONFIG)
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    await async_call(hass, "turn_off")
    await async_call(hass, "turn_on")
    assert thermostat(hass).state == HVACMode.COOL
    assert devices_on(hass) == {"cooler"}


async def test_turn_on_without_history(hass: HomeAssistant) -> None:
    """With no previous mode, turn_on prefers heat_cool, then heat, then cool."""
    await async_setup_thermostat(hass, enable_heat_cool=True)
    await async_call(hass, "turn_on")
    assert thermostat(hass).state == HVACMode.HEAT_COOL


async def test_set_temperature_with_mode(hass: HomeAssistant) -> None:
    """A mode passed with set_temperature applies, with the target linked to it."""
    await async_setup_thermostat(hass, temperature=21, **CONFIG)
    await async_call(hass, "set_temperature", temperature=24, hvac_mode="heat")
    state = thermostat(hass)
    assert state.state == HVACMode.HEAT
    assert state.attributes["temperature"] == 24
    assert devices_on(hass) == {"heater"}


async def test_inverted_range_rejected(hass: HomeAssistant) -> None:
    """A range whose low end is above its high end is refused."""
    await async_setup_thermostat(hass, enable_heat_cool=True)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    with pytest.raises(ServiceValidationError):
        await async_call(hass, "set_temperature", target_temp_low=25, target_temp_high=20)
