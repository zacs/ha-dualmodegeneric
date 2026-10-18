"""Heat, cool, fan-only and dry modes.

Tolerances are 0.5 around a 22° target so every threshold is exact in binary
floating point: heating starts at 21.5 and stops at 22.5, cooling the reverse.
"""

import pytest
from homeassistant.components.climate import HVACAction, HVACMode
from homeassistant.core import HomeAssistant

from .common import (
    COOLER,
    DRYER,
    FAN,
    HEATER,
    async_call,
    async_set_temperature,
    async_setup_thermostat,
    devices_on,
    is_on,
    thermostat,
)

TOLERANCES = {"target_temp": 22, "cold_tolerance": 0.5, "hot_tolerance": 0.5}


async def test_heat_starts_at_cold_tolerance(hass: HomeAssistant) -> None:
    """Heating starts once the temperature is target - cold_tolerance or lower."""
    await async_setup_thermostat(hass, temperature=23, **TOLERANCES)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == set()
    assert thermostat(hass).attributes["hvac_action"] == HVACAction.IDLE

    await async_set_temperature(hass, 21.6)
    assert not is_on(hass, HEATER)
    await async_set_temperature(hass, 21.5)
    assert devices_on(hass) == {"heater"}
    assert thermostat(hass).attributes["hvac_action"] == HVACAction.HEATING


async def test_heat_stops_at_hot_tolerance(hass: HomeAssistant) -> None:
    """Once running, heating continues until target + hot_tolerance."""
    await async_setup_thermostat(hass, temperature=21, **TOLERANCES)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert is_on(hass, HEATER)

    await async_set_temperature(hass, 22.4)
    assert is_on(hass, HEATER)
    await async_set_temperature(hass, 22.5)
    assert devices_on(hass) == set()
    assert thermostat(hass).attributes["hvac_action"] == HVACAction.IDLE


async def test_heat_never_cools(hass: HomeAssistant) -> None:
    """Heat mode only ever uses the heater."""
    await async_setup_thermostat(hass, temperature=30, **TOLERANCES)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_set_temperature(hass, 31)
    assert devices_on(hass) == set()


async def test_cool_starts_at_hot_tolerance(hass: HomeAssistant) -> None:
    """Cooling starts once the temperature is target + hot_tolerance or higher."""
    await async_setup_thermostat(hass, temperature=21, **TOLERANCES)
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    assert devices_on(hass) == set()

    await async_set_temperature(hass, 22.4)
    assert not is_on(hass, COOLER)
    await async_set_temperature(hass, 22.5)
    assert devices_on(hass) == {"cooler"}
    assert thermostat(hass).attributes["hvac_action"] == HVACAction.COOLING


async def test_cool_stops_at_cold_tolerance(hass: HomeAssistant) -> None:
    """Once running, cooling continues until target - cold_tolerance."""
    await async_setup_thermostat(hass, temperature=23, **TOLERANCES)
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    assert is_on(hass, COOLER)

    await async_set_temperature(hass, 21.6)
    assert is_on(hass, COOLER)
    await async_set_temperature(hass, 21.5)
    assert devices_on(hass) == set()


async def test_cool_never_heats(hass: HomeAssistant) -> None:
    """Cool mode only ever uses the cooler."""
    await async_setup_thermostat(hass, temperature=10, **TOLERANCES)
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    assert devices_on(hass) == set()


async def test_target_change_acts_immediately(hass: HomeAssistant) -> None:
    """Changing the target re-evaluates without waiting for a sensor update."""
    await async_setup_thermostat(hass, temperature=21, **TOLERANCES)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert is_on(hass, HEATER)
    await async_call(hass, "set_temperature", temperature=19)
    assert devices_on(hass) == set()
    await async_call(hass, "set_temperature", temperature=24)
    assert devices_on(hass) == {"heater"}


@pytest.mark.parametrize(
    ("mode", "device", "behavior_key", "action"),
    [
        ("fan_only", FAN, "fan_behavior", HVACAction.FAN),
        ("dry", DRYER, "dryer_behavior", HVACAction.DRYING),
    ],
)
async def test_neutral_runs_regardless_of_temperature(
    hass: HomeAssistant, mode: str, device: str, behavior_key: str, action: HVACAction
) -> None:
    """A neutral fan/dryer simply runs while its mode is selected."""
    await async_setup_thermostat(
        hass, fan=FAN, dryer=DRYER, **{behavior_key: "neutral"}, **TOLERANCES
    )
    await async_call(hass, "set_hvac_mode", hvac_mode=mode)
    assert is_on(hass, device)
    state = thermostat(hass)
    assert state.attributes["hvac_action"] == action
    # No target is shown because none is used.
    assert state.attributes["temperature"] is None

    for reading in (10, 22, 35):
        await async_set_temperature(hass, reading)
        assert is_on(hass, device)

    await async_call(hass, "set_hvac_mode", hvac_mode="off")
    assert not is_on(hass, device)


@pytest.mark.parametrize(
    ("mode", "device", "behavior_key"),
    [("fan_only", FAN, "fan_behavior"), ("dry", DRYER, "dryer_behavior")],
)
async def test_cooler_behavior(
    hass: HomeAssistant, mode: str, device: str, behavior_key: str
) -> None:
    """With behavior 'cooler', the device runs like a cooler around the target."""
    await async_setup_thermostat(
        hass, temperature=21, fan=FAN, dryer=DRYER, **{behavior_key: "cooler"}, **TOLERANCES
    )
    await async_call(hass, "set_hvac_mode", hvac_mode=mode)
    assert thermostat(hass).attributes["temperature"] == 22
    assert not is_on(hass, device)

    await async_set_temperature(hass, 22.5)
    assert is_on(hass, device)
    await async_set_temperature(hass, 21.6)
    assert is_on(hass, device)
    await async_set_temperature(hass, 21.5)
    assert not is_on(hass, device)
    assert not is_on(hass, HEATER)
    assert not is_on(hass, COOLER)


@pytest.mark.parametrize(
    ("mode", "device", "behavior_key"),
    [("fan_only", FAN, "fan_behavior"), ("dry", DRYER, "dryer_behavior")],
)
async def test_heater_behavior(
    hass: HomeAssistant, mode: str, device: str, behavior_key: str
) -> None:
    """With behavior 'heater', the device runs like a heater around the target."""
    await async_setup_thermostat(
        hass, temperature=23, fan=FAN, dryer=DRYER, **{behavior_key: "heater"}, **TOLERANCES
    )
    await async_call(hass, "set_hvac_mode", hvac_mode=mode)
    assert thermostat(hass).attributes["temperature"] == 22
    assert not is_on(hass, device)

    await async_set_temperature(hass, 21.5)
    assert is_on(hass, device)
    await async_set_temperature(hass, 22.4)
    assert is_on(hass, device)
    await async_set_temperature(hass, 22.5)
    assert not is_on(hass, device)


async def test_off_mode(hass: HomeAssistant) -> None:
    """Off never turns anything on and reports the off action."""
    await async_setup_thermostat(hass, temperature=5, fan=FAN, dryer=DRYER, **TOLERANCES)
    await async_set_temperature(hass, 40)
    assert devices_on(hass) == set()
    state = thermostat(hass)
    assert state.state == HVACMode.OFF
    assert state.attributes["hvac_action"] == HVACAction.OFF


async def test_unavailable_sensor_reading_is_ignored(hass: HomeAssistant) -> None:
    """unavailable/unknown readings keep the last good temperature."""
    await async_setup_thermostat(hass, temperature=21, **TOLERANCES)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    for reading in ("unavailable", "unknown"):
        await async_set_temperature(hass, reading)
        assert thermostat(hass).attributes["current_temperature"] == 21
        assert is_on(hass, HEATER)
