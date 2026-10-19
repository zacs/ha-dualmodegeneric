"""Loading, configuration surface and exposed attributes.

These pin the public surface existing users depend on: YAML keys, entity
registration, the list and order of HVAC modes, features and attribute names.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant import config as hass_config
from homeassistant.components.climate import ClimateEntityFeature, HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component

from .common import (
    COOLER,
    DOMAIN,
    DRYER,
    ENTITY,
    FAN,
    HEATER,
    HUMIDITY,
    async_call,
    async_setup_devices,
    async_setup_thermostat,
    thermostat,
    thermostat_config,
)

BASE_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.TURN_OFF
)


async def test_minimal_config(hass: HomeAssistant) -> None:
    """Only a heater and a sensor are needed."""
    await async_setup_thermostat(hass, cooler=None)
    state = thermostat(hass)
    assert state.state == HVACMode.OFF
    assert state.attributes["hvac_modes"] == [HVACMode.HEAT, HVACMode.OFF]
    assert state.attributes["supported_features"] == BASE_FEATURES
    assert state.attributes["current_temperature"] == 20


@pytest.mark.parametrize(
    ("devices", "expected"),
    [
        ({"cooler": None}, [HVACMode.HEAT, HVACMode.OFF]),
        ({"heater": None}, [HVACMode.COOL, HVACMode.OFF]),
        ({}, [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF]),
        (
            {"enable_heat_cool": True},
            [HVACMode.COOL, HVACMode.HEAT, HVACMode.OFF, HVACMode.HEAT_COOL],
        ),
        # heat_cool needs both a heater and a cooler.
        ({"cooler": None, "enable_heat_cool": True}, [HVACMode.HEAT, HVACMode.OFF]),
        ({"heater": None, "cooler": None, "fan": FAN}, [HVACMode.FAN_ONLY, HVACMode.OFF]),
        ({"heater": None, "cooler": None, "dryer": DRYER}, [HVACMode.DRY, HVACMode.OFF]),
        (
            {"fan": FAN, "dryer": DRYER, "enable_heat_cool": True},
            [
                HVACMode.COOL,
                HVACMode.HEAT,
                HVACMode.DRY,
                HVACMode.FAN_ONLY,
                HVACMode.OFF,
                HVACMode.HEAT_COOL,
            ],
        ),
    ],
)
async def test_hvac_modes_follow_configured_devices(
    hass: HomeAssistant, devices: dict, expected: list[HVACMode]
) -> None:
    """Modes are offered only for configured devices, in a stable order."""
    await async_setup_thermostat(hass, **devices)
    assert thermostat(hass).attributes["hvac_modes"] == expected


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({}, BASE_FEATURES),
        (
            {"enable_heat_cool": True},
            BASE_FEATURES | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE,
        ),
        ({"away_temp": 16}, BASE_FEATURES | ClimateEntityFeature.PRESET_MODE),
        (
            {"away_temp_heater": 16, "away_temp_cooler": 28},
            BASE_FEATURES | ClimateEntityFeature.PRESET_MODE,
        ),
    ],
)
async def test_supported_features(
    hass: HomeAssistant, options: dict, expected: ClimateEntityFeature
) -> None:
    """Features depend on heat_cool and away configuration."""
    await async_setup_thermostat(hass, **options)
    assert thermostat(hass).attributes["supported_features"] == expected


async def test_state_attributes(hass: HomeAssistant) -> None:
    """Attribute names that dashboards and automations read stay available."""
    hass.states.async_set(HUMIDITY, "45")
    await async_setup_thermostat(
        hass,
        fan=FAN,
        dryer=DRYER,
        enable_heat_cool=True,
        away_temp=16,
        target_humidity_sensor=HUMIDITY,
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    attributes = thermostat(hass).attributes
    assert {
        "hvac_modes",
        "min_temp",
        "max_temp",
        "target_temp_step",
        "preset_modes",
        "current_temperature",
        "current_humidity",
        "temperature",
        "target_temp_high",
        "target_temp_low",
        "hvac_action",
        "preset_mode",
        "friendly_name",
        "supported_features",
    } <= set(attributes)
    assert attributes["current_humidity"] == 45
    assert attributes["preset_modes"] == ["none", "away"]
    assert attributes["friendly_name"] == "test"


async def test_humidity_sensor_updates(hass: HomeAssistant) -> None:
    """The optional humidity sensor is reported as current humidity."""
    await async_setup_thermostat(hass, target_humidity_sensor=HUMIDITY)
    hass.states.async_set(HUMIDITY, "51.5")
    await hass.async_block_till_done()
    assert thermostat(hass).attributes["current_humidity"] == 51.5


async def test_temperature_limits_and_step(hass: HomeAssistant) -> None:
    """min/max temp, precision and target_temp_step are honoured."""
    await async_setup_thermostat(hass, min_temp=15, max_temp=28, precision=0.5)
    attributes = thermostat(hass).attributes
    assert (attributes["min_temp"], attributes["max_temp"]) == (15, 28)
    assert attributes["target_temp_step"] == 0.5


async def test_target_temp_step_overrides_precision(hass: HomeAssistant) -> None:
    """target_temp_step wins over precision for the UI step."""
    await async_setup_thermostat(hass, precision=0.1, target_temp_step=1)
    assert thermostat(hass).attributes["target_temp_step"] == 1


async def test_default_temperature_limits(hass: HomeAssistant) -> None:
    """Without limits configured, Home Assistant's climate defaults apply."""
    await async_setup_thermostat(hass)
    attributes = thermostat(hass).attributes
    assert (attributes["min_temp"], attributes["max_temp"]) == (7, 35)


async def test_unique_id(hass: HomeAssistant, entity_registry: er.EntityRegistry) -> None:
    """A configured unique_id registers the entity."""
    await async_setup_thermostat(hass, unique_id="climate.my_thermostat")
    entry = entity_registry.async_get(ENTITY)
    assert entry is not None
    assert entry.unique_id == "climate.my_thermostat"


@pytest.mark.parametrize("value", [True, False, "heater, cooler", "cooler,heater,fan,dryer"])
async def test_reverse_cycle_formats(hass: HomeAssistant, value) -> None:
    """Legacy booleans and comma-separated lists are both accepted."""
    await async_setup_thermostat(hass, fan=FAN, dryer=DRYER, reverse_cycle=value)


async def test_readme_example(hass: HomeAssistant) -> None:
    """The configuration shown in the README loads."""
    await async_setup_thermostat(
        hass,
        unique_id="climate.my_thermostat",
        heater=HEATER,
        cooler=COOLER,
        fan=FAN,
        fan_behavior="cooler",
        dryer=DRYER,
        dryer_behavior="cooler",
        reverse_cycle="cooler, heater",
        enable_heat_cool=True,
        min_temp=16,
        max_temp=30,
        cold_tolerance=0.8,
        hot_tolerance=0.4,
        min_cycle_duration={"minutes": 20},
        consent_entity="calendar.schedule_time",
    )


# TODO(phase 1): track keep_alive with cancel_on_shutdown=True and drop this marker.
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_every_documented_option(hass: HomeAssistant) -> None:
    """All options the integration documents or inherits load together."""
    await async_setup_thermostat(
        hass,
        fan=FAN,
        dryer=DRYER,
        target_humidity_sensor=HUMIDITY,
        consent_entity="input_boolean.consent",
        fan_behavior="heater",
        dryer_behavior="neutral",
        reverse_cycle="heater",
        enable_heat_cool=True,
        min_temp=10,
        max_temp=30,
        target_temp=21,
        target_temp_low=19,
        target_temp_high=25,
        cold_tolerance=0.2,
        hot_tolerance=0.4,
        min_cycle_duration={"seconds": 30},
        keep_alive={"minutes": 3},
        initial_hvac_mode="heat",
        away_temp=15,
        away_temp_heater=14,
        away_temp_cooler=29,
        precision=0.5,
        target_temp_step=0.5,
        unique_id="every_option",
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"fan_behavior": "sideways"},
        {"initial_hvac_mode": "auto"},
        {"precision": 0.25},
        {"target_sensor": None},
    ],
)
async def test_invalid_config_rejected(hass: HomeAssistant, bad: dict) -> None:
    """Invalid values are rejected rather than half-loaded."""
    await async_setup_devices(hass)
    await async_setup_component(hass, "climate", {"climate": thermostat_config(**bad)})
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY) is None


async def test_reload(hass: HomeAssistant, tmp_path: Path) -> None:
    """The reload service picks up YAML changes."""
    await async_setup_thermostat(hass)
    yaml_path = tmp_path / "configuration.yaml"
    yaml_path.write_text(
        "climate:\n"
        f"  - platform: {DOMAIN}\n"
        "    name: reloaded\n"
        f"    heater: {HEATER}\n"
        "    target_sensor: sensor.temperature\n"
    )
    with patch.object(hass_config, "YAML_CONFIG_FILE", str(yaml_path)):
        await hass.services.async_call(DOMAIN, "reload", {}, blocking=True)
        await hass.async_block_till_done()
    assert hass.states.get(ENTITY) is None
    assert hass.states.get("climate.reloaded") is not None
