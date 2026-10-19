"""Setting up and editing thermostats from the UI."""

from typing import Any

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .common import COOLER, DOMAIN, DRYER, FAN, HEATER, SENSOR, async_setup_devices

ENTITY = "climate.living_room"


async def _start(hass: HomeAssistant) -> dict[str, Any]:
    await async_setup_devices(hass)
    hass.states.async_set(SENSOR, "20")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def test_create_full(hass: HomeAssistant, entity_registry: er.EntityRegistry) -> None:
    """Every step, with all devices, creates a working thermostat."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "Living room",
            "target_sensor": SENSOR,
            "heater": HEATER,
            "cooler": COOLER,
            "fan": FAN,
        },
    )
    assert result["step_id"] == "behavior"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"enable_heat_cool": True, "fan_behavior": "cooler", "reverse_cycle": ["heater", "cooler"]},
    )
    assert result["step_id"] == "settings"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "cold_tolerance": 0.5,
            "hot_tolerance": 0.4,
            "target_temp_low": 20,
            "target_temp_high": 24,
            "min_cycle_duration": {"hours": 0, "minutes": 5, "seconds": 0},
            "precision": "0.5",
        },
    )
    assert result["step_id"] == "presets"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"away": {"away_temp_heater": 16, "away_temp_cooler": 28}}
    )
    assert result["step_id"] == "interlocks"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living room"
    assert result["data"] == {}
    assert result["options"] == {
        "name": "Living room",
        "target_sensor": SENSOR,
        "heater": HEATER,
        "cooler": COOLER,
        "fan": FAN,
        "enable_heat_cool": True,
        "fan_behavior": "cooler",
        "reverse_cycle": ["heater", "cooler"],
        "cold_tolerance": 0.5,
        "hot_tolerance": 0.4,
        "target_temp_low": 20,
        "target_temp_high": 24,
        "min_cycle_duration": {"hours": 0, "minutes": 5, "seconds": 0},
        "precision": "0.5",
        "away_temp_heater": 16,
        "away_temp_cooler": 28,
    }
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY)
    assert state is not None
    assert state.attributes["hvac_modes"] == [
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.FAN_ONLY,
        HVACMode.OFF,
        HVACMode.HEAT_COOL,
    ]
    assert state.attributes["target_temp_step"] == 0.5
    assert state.attributes["preset_modes"] == ["none", "away"]
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entity_registry.async_get(ENTITY).unique_id == entry.entry_id


async def test_single_device_skips_behavior(hass: HomeAssistant) -> None:
    """With only a heater there's nothing to choose about how devices combine."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Living room", "target_sensor": SENSOR, "heater": HEATER}
    )
    assert result["step_id"] == "settings"
    schema_keys = {str(key) for key in result["data_schema"].schema}
    assert "target_temp_low" not in schema_keys
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"cold_tolerance": 0.3, "hot_tolerance": 0.3}
    )
    assert result["step_id"] == "presets"
    schema = result["data_schema"].schema
    assert {str(key) for key in schema} == {"away", "comfort", "eco", "home", "sleep", "activity"}
    away = next(value for key, value in schema.items() if key == "away")
    assert {str(key) for key in away.schema.schema} == {"away_temp", "away_temp_heater"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "interlocks"
    schema_keys = {str(key) for key in result["data_schema"].schema}
    assert schema_keys == {"consent_entity", "tamper_entity", "water_guard"}


async def test_needs_a_device(hass: HomeAssistant) -> None:
    """A thermostat without any device is refused."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Living room", "target_sensor": SENSOR}
    )
    assert result["errors"] == {"base": "no_devices"}


@pytest.mark.parametrize(
    ("settings", "error"),
    [
        ({"min_temp": 25, "max_temp": 18}, "min_max_temp"),
        ({"target_temp_low": 25, "target_temp_high": 20}, "target_range"),
        ({"keep_alive": {"hours": 0, "minutes": 0, "seconds": 0}}, "zero_duration"),
    ],
)
async def test_settings_validation(
    hass: HomeAssistant, settings: dict[str, Any], error: str
) -> None:
    """Contradictory settings are caught in the form."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Living room", "target_sensor": SENSOR, "heater": HEATER, "cooler": COOLER},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"enable_heat_cool": True}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"cold_tolerance": 0.3, "hot_tolerance": 0.3, **settings}
    )
    assert result["errors"] == {"base": error}


async def _entry(hass: HomeAssistant, **options: Any) -> MockConfigEntry:
    await async_setup_devices(hass)
    hass.states.async_set(SENSOR, "20")
    options = {
        "name": "Living room",
        "target_sensor": SENSOR,
        "heater": HEATER,
        "cold_tolerance": 0.3,
        "hot_tolerance": 0.3,
        **options,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Living room",
        # A value of None drops the key.
        options={key: value for key, value in options.items() if value is not None},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_options_menu(hass: HomeAssistant) -> None:
    """The options start from a menu of sections; behavior only when it applies."""
    entry = await _entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["devices", "settings", "presets", "interlocks"]

    entry = await _entry(hass, cooler=COOLER)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["menu_options"] == ["devices", "behavior", "settings", "presets", "interlocks"]


async def test_options_edit_settings(hass: HomeAssistant) -> None:
    """Editing a section saves it and reloads the thermostat."""
    entry = await _entry(hass, max_temp=30)
    assert hass.states.get(ENTITY).attributes["max_temp"] == 30

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
    )
    assert result["step_id"] == "settings"
    # max_temp left out: cleared.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"cold_tolerance": 0.5, "hot_tolerance": 0.5, "min_temp": 15}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert entry.options["cold_tolerance"] == 0.5
    assert "max_temp" not in entry.options
    attributes = hass.states.get(ENTITY).attributes
    assert (attributes["min_temp"], attributes["max_temp"]) == (15, 35)


async def test_options_add_device_then_behavior(hass: HomeAssistant) -> None:
    """Adding a fan leads on to choosing how it behaves."""
    entry = await _entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "devices"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"target_sensor": SENSOR, "heater": HEATER, "dryer": DRYER}
    )
    assert result["step_id"] == "behavior"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"dryer_behavior": "cooler"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["dryer_behavior"] == "cooler"
    assert HVACMode.DRY in hass.states.get(ENTITY).attributes["hvac_modes"]


async def test_options_removing_a_device_forgets_its_settings(hass: HomeAssistant) -> None:
    """Settings for a removed device go too, so no hidden choice can fail a form."""
    entry = await _entry(
        hass,
        cooler=COOLER,
        fan=FAN,
        enable_heat_cool=True,
        fan_behavior="cooler",
        reverse_cycle=["heater", "cooler", "fan"],
        target_temp_low=20,
        target_temp_high=24,
        away_temp_heater=16,
        away_temp_cooler=28,
        initial_hvac_mode="heat_cool",
    )
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "devices"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"target_sensor": SENSOR, "heater": HEATER, "fan": FAN}
    )
    assert result["step_id"] == "behavior"
    suggested = {
        str(key): key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description
    }
    assert suggested == {"fan_behavior": "cooler", "reverse_cycle": ["heater", "fan"]}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"fan_behavior": "cooler", "reverse_cycle": ["heater", "fan"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {
        "name": "Living room",
        "target_sensor": SENSOR,
        "heater": HEATER,
        "fan": FAN,
        "cold_tolerance": 0.3,
        "hot_tolerance": 0.3,
        "fan_behavior": "cooler",
        "reverse_cycle": ["heater", "fan"],
        "away_temp_heater": 16,
    }

    # Down to one device: nothing left to choose, so the behavior settings go.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "devices"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"target_sensor": SENSOR, "heater": HEATER}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert "fan_behavior" not in entry.options
    assert "reverse_cycle" not in entry.options
    assert hass.states.get(ENTITY).attributes["hvac_modes"] == [HVACMode.HEAT, HVACMode.OFF]


async def test_options_turning_off_heat_cool_forgets_its_range(hass: HomeAssistant) -> None:
    """Without Heat/cool, its range and its use as the starting mode go too."""
    entry = await _entry(
        hass,
        cooler=COOLER,
        enable_heat_cool=True,
        target_temp_low=20,
        target_temp_high=24,
        initial_hvac_mode="heat_cool",
    )
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "behavior"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"enable_heat_cool": False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    for key in ("target_temp_low", "target_temp_high", "initial_hvac_mode"):
        assert key not in entry.options


async def _options_step(hass: HomeAssistant, entry: MockConfigEntry, step: str) -> dict[str, Any]:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


def _suggested(schema: Any) -> dict[str, Any]:
    """Return the suggested values of a form, nested by section."""
    values: dict[str, Any] = {}
    for key, value in schema.schema.items():
        if hasattr(value, "schema") and hasattr(value, "options"):  # a section
            values[str(key)] = _suggested(value.schema)
        elif key.description and "suggested_value" in key.description:
            values[str(key)] = key.description["suggested_value"]
    return values


async def test_presets_saved_flat(hass: HomeAssistant) -> None:
    """Preset sections are saved as plain options, and emptying a field removes it."""
    entry = await _entry(hass, cooler=COOLER, away_temp=16)
    result = await _options_step(hass, entry, "presets")
    assert _suggested(result["data_schema"])["away"] == {"away_temp": 16}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"away": {}, "eco": {"eco_temp_heater": 18, "eco_temp_cooler": 26}}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert "away_temp" not in entry.options
    assert (entry.options["eco_temp_heater"], entry.options["eco_temp_cooler"]) == (18, 26)
    assert hass.states.get(ENTITY).attributes["preset_modes"] == ["none", "eco"]


async def test_device_tolerances_saved_flat(hass: HomeAssistant) -> None:
    """Separate heater and cooler tolerances are only offered with both devices."""
    entry = await _entry(hass)
    result = await _options_step(hass, entry, "settings")
    assert "device_tolerances" not in {str(key) for key in result["data_schema"].schema}

    entry = await _entry(hass, cooler=COOLER)
    result = await _options_step(hass, entry, "settings")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "cold_tolerance": 0.3,
            "hot_tolerance": 0.3,
            "device_tolerances": {"heater_hot_tolerance": 0},
            "max_cycle_duration": {"hours": 1, "minutes": 0, "seconds": 0},
            "cycle_cooldown": {"hours": 0, "minutes": 10, "seconds": 0},
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["heater_hot_tolerance"] == 0
    assert "device_tolerances" not in entry.options


async def test_max_must_exceed_min(hass: HomeAssistant) -> None:
    """A maximum run time no longer than the minimum is refused."""
    entry = await _entry(hass)
    result = await _options_step(hass, entry, "settings")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "cold_tolerance": 0.3,
            "hot_tolerance": 0.3,
            "min_cycle_duration": {"hours": 0, "minutes": 10, "seconds": 0},
            "max_cycle_duration": {"hours": 0, "minutes": 5, "seconds": 0},
        },
    )
    assert result["errors"] == {"base": "max_below_min"}


async def test_fan_with(hass: HomeAssistant) -> None:
    """The fan can be set to run with the heater; not when it's a reverse-cycle device."""
    entry = await _entry(hass, fan=FAN)
    result = await _options_step(hass, entry, "behavior")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"fan_behavior": "neutral", "fan_with": ["heater"], "reverse_cycle": ["heater", "fan"]},
    )
    assert result["errors"] == {"base": "fan_with_reverse_cycle"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "fan_behavior": "neutral",
            "fan_with": ["heater"],
            "fan_off_delay": {"hours": 0, "minutes": 2, "seconds": 0},
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).attributes["fan_modes"] == ["auto", "on", "off"]

    # Removing the fan forgets what it ran with.
    result = await _options_step(hass, entry, "devices")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"target_sensor": SENSOR, "heater": HEATER}
    )
    assert "fan_with" not in entry.options
    assert "fan_off_delay" not in entry.options


async def test_interlocks(hass: HomeAssistant) -> None:
    """Tamper and the water guard are saved flat; setpoints need a water sensor."""
    entry = await _entry(hass)
    result = await _options_step(hass, entry, "interlocks")
    water = next(
        value for key, value in result["data_schema"].schema.items() if key == "water_guard"
    )
    # Only a heater: no cooling setpoints.
    assert {str(key) for key in water.schema.schema} == {
        "water_sensor",
        "water_setpoint_heat",
        "water_setpoint_heat_entity",
        "water_tolerance",
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"water_guard": {"water_setpoint_heat": 30}}
    )
    assert result["errors"] == {"base": "water_needs_sensor"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "tamper_entity": "binary_sensor.window",
            "water_guard": {"water_sensor": "sensor.water", "water_setpoint_heat": 30},
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["tamper_entity"] == "binary_sensor.window"
    assert (entry.options["water_sensor"], entry.options["water_setpoint_heat"]) == (
        "sensor.water",
        30,
    )


async def test_behavior_change_forgets_water_setpoint(hass: HomeAssistant) -> None:
    """A fan that no longer heats drops the heating water setpoint it alone needed."""
    entry = await _entry(
        hass,
        heater=None,
        fan=FAN,
        fan_behavior="heater",
        water_sensor="sensor.water",
        water_setpoint_heat=30,
    )
    result = await _options_step(hass, entry, "behavior")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"fan_behavior": "neutral"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert "water_setpoint_heat" not in entry.options
    assert "water_sensor" not in entry.options


async def test_removing_cooler_forgets_cooling_settings(hass: HomeAssistant) -> None:
    """Cooling temperatures of presets, tolerances and the guard go with the cooler."""
    entry = await _entry(
        hass,
        cooler=COOLER,
        eco_temp_cooler=26,
        eco_temp_heater=18,
        cooler_hot_tolerance=1,
        water_sensor="sensor.water",
        water_setpoint_cool=15,
    )
    result = await _options_step(hass, entry, "devices")
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"target_sensor": SENSOR, "heater": HEATER}
    )
    for key in ("eco_temp_cooler", "cooler_hot_tolerance", "water_setpoint_cool"):
        assert key not in entry.options
    assert entry.options["eco_temp_heater"] == 18
    assert entry.options["water_sensor"] == "sensor.water"
