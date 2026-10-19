"""The away preset."""

from homeassistant.core import HomeAssistant

from .common import (
    HEATER,
    async_call,
    async_setup_thermostat,
    devices_on,
    is_on,
    thermostat,
)


async def test_away_and_back_in_heat(hass: HomeAssistant) -> None:
    """Away applies away_temp; leaving it restores the previous target."""
    await async_setup_thermostat(hass, temperature=20, target_temp=22, away_temp=16)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert is_on(hass, HEATER)

    await async_call(hass, "set_preset_mode", preset_mode="away")
    state = thermostat(hass)
    assert state.attributes["preset_mode"] == "away"
    assert state.attributes["temperature"] == 16
    assert devices_on(hass) == set()

    await async_call(hass, "set_preset_mode", preset_mode="none")
    state = thermostat(hass)
    assert state.attributes["preset_mode"] == "none"
    assert state.attributes["temperature"] == 22
    assert devices_on(hass) == {"heater"}


async def test_away_temps_per_device(hass: HomeAssistant) -> None:
    """away_temp_heater applies in heat mode and away_temp_cooler in cool mode."""
    await async_setup_thermostat(hass, target_temp=22, away_temp_heater=16, away_temp_cooler=28)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_preset_mode", preset_mode="away")
    assert thermostat(hass).attributes["temperature"] == 16
    await async_call(hass, "set_preset_mode", preset_mode="none")

    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    await async_call(hass, "set_preset_mode", preset_mode="away")
    assert thermostat(hass).attributes["temperature"] == 28


async def test_away_temp_is_the_fallback(hass: HomeAssistant) -> None:
    """Without a device-specific away temperature, away_temp is used."""
    await async_setup_thermostat(hass, target_temp=22, away_temp=18, away_temp_heater=15)
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    await async_call(hass, "set_preset_mode", preset_mode="away")
    assert thermostat(hass).attributes["temperature"] == 18
