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


async def test_away_follows_mode_changes(hass: HomeAssistant) -> None:
    """Changing mode while away applies the new mode's away temperature."""
    await async_setup_thermostat(hass, target_temp=22, away_temp_heater=16, away_temp_cooler=28)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_preset_mode", preset_mode="away")
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    assert thermostat(hass).attributes["temperature"] == 28
    await async_call(hass, "set_preset_mode", preset_mode="none")
    assert thermostat(hass).attributes["temperature"] == 22


async def test_plain_away_temp_in_heat_cool(hass: HomeAssistant) -> None:
    """A single away_temp lowers the heating end of the range and keeps the cooling end."""
    await async_setup_thermostat(
        hass, enable_heat_cool=True, target_temp_low=20, target_temp_high=24, away_temp=16
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    await async_call(hass, "set_preset_mode", preset_mode="away")
    attributes = thermostat(hass).attributes
    assert (attributes["target_temp_low"], attributes["target_temp_high"]) == (16, 24)
    await async_call(hass, "set_preset_mode", preset_mode="none")
    attributes = thermostat(hass).attributes
    assert (attributes["target_temp_low"], attributes["target_temp_high"]) == (20, 24)


async def test_no_preset_support_without_away_temps(hass: HomeAssistant) -> None:
    """Without away temperatures there are no presets to offer."""
    await async_setup_thermostat(hass)
    attributes = thermostat(hass).attributes
    assert "preset_modes" not in attributes
    assert "preset_mode" not in attributes


async def test_any_away_temperature_enables_away(hass: HomeAssistant) -> None:
    """A heater-only thermostat with just away_temp_heater gets the away preset."""
    await async_setup_thermostat(hass, cooler=None, target_temp=22, away_temp_heater=16)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_preset_mode", preset_mode="away")
    assert thermostat(hass).attributes["temperature"] == 16


async def test_all_presets_in_display_order(hass: HomeAssistant) -> None:
    """Every configured preset is offered, in the built-in thermostat's order."""
    await async_setup_thermostat(
        hass, target_temp=22, sleep_temp=18, away_temp=16, eco_temp_heater=19, comfort_temp=23
    )
    assert thermostat(hass).attributes["preset_modes"] == [
        "none",
        "away",
        "comfort",
        "eco",
        "sleep",
    ]


async def test_switching_between_presets(hass: HomeAssistant) -> None:
    """Going from one preset to another keeps the targets from before either."""
    await async_setup_thermostat(hass, temperature=20, target_temp=22, eco_temp=19, comfort_temp=23)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_call(hass, "set_preset_mode", preset_mode="eco")
    assert thermostat(hass).attributes["temperature"] == 19
    assert devices_on(hass) == set()

    await async_call(hass, "set_preset_mode", preset_mode="comfort")
    assert thermostat(hass).attributes["temperature"] == 23
    assert devices_on(hass) == {"heater"}

    await async_call(hass, "set_preset_mode", preset_mode="none")
    assert thermostat(hass).attributes["temperature"] == 22


async def test_preset_variants_set_the_range(hass: HomeAssistant) -> None:
    """In heat/cool, a preset's heating and cooling temperatures become the range."""
    await async_setup_thermostat(
        hass,
        enable_heat_cool=True,
        target_temp_low=20,
        target_temp_high=24,
        eco_temp_heater=17,
        eco_temp_cooler=28,
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    await async_call(hass, "set_preset_mode", preset_mode="eco")
    attributes = thermostat(hass).attributes
    assert (attributes["target_temp_low"], attributes["target_temp_high"]) == (17, 28)
    await async_call(hass, "set_preset_mode", preset_mode="none")
    attributes = thermostat(hass).attributes
    assert (attributes["target_temp_low"], attributes["target_temp_high"]) == (20, 24)
