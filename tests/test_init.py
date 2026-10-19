"""UI-created thermostats: lifecycle, renamed entities, diagnostics, translations."""

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import section
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.translation import async_get_translations
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dualmode_generic import config_flow
from custom_components.dualmode_generic.diagnostics import async_get_config_entry_diagnostics

from .common import DOMAIN, HEATER, SENSOR, async_call, async_setup_devices

ENTITY = "climate.living_room"
TRANSLATIONS = json.loads(
    (
        Path(__file__).parents[1] / "custom_components/dualmode_generic/translations/en.json"
    ).read_text()
)


async def _entry(hass: HomeAssistant, heater: str = HEATER) -> MockConfigEntry:
    await async_setup_devices(hass)
    hass.states.async_set(SENSOR, "20")
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Living room",
        options={
            "name": "Living room",
            "target_sensor": SENSOR,
            "heater": heater,
            "cold_tolerance": 0.3,
            "hot_tolerance": 0.3,
            "target_temp": 22,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_and_unload(hass: HomeAssistant) -> None:
    """A UI thermostat controls its devices like a YAML one, and unloads cleanly."""
    entry = await _entry(hass)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat", entity_id=ENTITY)
    assert hass.states.is_state(HEATER, "on")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_follows_renamed_entities(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Renaming a device's entity ID updates the thermostat to match."""
    heater = entity_registry.async_get_or_create(
        "switch", "test", "heater", suggested_object_id="radiator"
    )
    hass.states.async_set(heater.entity_id, "off")
    entry = await _entry(hass, heater=heater.entity_id)

    entity_registry.async_update_entity(heater.entity_id, new_entity_id="switch.big_radiator")
    await hass.async_block_till_done()
    assert entry.options["heater"] == "switch.big_radiator"
    assert entry.options["target_sensor"] == SENSOR


async def test_diagnostics(hass: HomeAssistant) -> None:
    """Diagnostics show the options and the state of each source."""
    entry = await _entry(hass)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["options"]["heater"] == HEATER
    assert diagnostics["thermostat"]["entity_id"] == ENTITY
    assert diagnostics["sources"]["target_sensor"]["state"] == "20"
    assert diagnostics["sources"]["heater"]["state"] == "off"


def _assert_fields_have_text(schema: vol.Schema, text: dict, where: str) -> None:
    for key, value in schema.schema.items():
        name = str(key)
        if isinstance(value, section):
            assert text["sections"][name]["name"], f"{where}.{name} section name"
            _assert_fields_have_text(value.schema, text["sections"][name], f"{where}.{name}")
            continue
        assert name in text["data"], f"{where}.{name} label"
        if name != "name":
            assert name in text["data_description"], f"{where}.{name} description"


def test_every_form_field_has_text() -> None:
    """Each field of each step, in sections too, has a label and a description in English."""

    # Every optional field shows when all devices and heat_cool are configured;
    # the schema builders only read handler.options.
    handler = SimpleNamespace(
        options={"heater": "a", "cooler": "b", "fan": "c", "dryer": "d", "enable_heat_cool": True}
    )
    for flow_name, flow in (
        ("config", config_flow.CONFIG_FLOW),
        ("options", config_flow.OPTIONS_FLOW),
    ):
        steps = TRANSLATIONS[flow_name]["step"]
        for step_id, step in flow.items():
            assert step_id in steps, f"{flow_name}.{step_id} has no text"
            schema = getattr(step, "schema", None)
            if schema is None:
                assert set(steps[step_id]["menu_options"]) == {
                    "devices",
                    "behavior",
                    "settings",
                    "presets",
                    "interlocks",
                }
                continue
            if not isinstance(schema, vol.Schema):
                schema = asyncio.run(schema(handler))
            _assert_fields_have_text(schema, steps[step_id], f"{flow_name}.{step_id}")


def test_errors_and_exceptions_have_text() -> None:
    """Every error the flow raises and every exception key has English text."""
    source = (Path(config_flow.__file__)).read_text()
    raised = set(re.findall(r'SchemaFlowError\("(\w+)"\)', source))
    assert raised == set(TRANSLATIONS["config"]["error"]) == set(TRANSLATIONS["options"]["error"])
    climate_source = (Path(config_flow.__file__).parent / "climate.py").read_text()
    for key in TRANSLATIONS["exceptions"]:
        assert f'translation_key="{key}"' in climate_source


async def test_translations_load(hass: HomeAssistant) -> None:
    """Home Assistant loads the English text for the flows, selectors and errors."""
    await _entry(hass)
    for category, key in (
        ("config", f"component.{DOMAIN}.config.step.user.title"),
        ("options", f"component.{DOMAIN}.options.step.init.menu_options.settings"),
        ("selector", f"component.{DOMAIN}.selector.behavior.options.neutral"),
        ("exceptions", f"component.{DOMAIN}.exceptions.inverted_range.message"),
        ("services", f"component.{DOMAIN}.services.reload.name"),
    ):
        loaded = await async_get_translations(hass, "en", category, [DOMAIN])
        assert loaded.get(key), key
