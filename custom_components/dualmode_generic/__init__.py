"""The dualmode_generic thermostat integration.

Thermostats can be set up in YAML (the climate platform) or from the UI
(config entries); both run the same code.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_entity_registry_updated_event

from .const import (
    CONF_CONSENT_ENTITY,
    CONF_COOLER,
    CONF_DRYER,
    CONF_FAN,
    CONF_HEATER,
    CONF_HUMIDITY_SENSOR,
    CONF_SENSOR,
    CONF_TAMPER_ENTITY,
    CONF_WATER_SENSOR,
    CONF_WATER_SETPOINT_COOL_ENTITY,
    CONF_WATER_SETPOINT_HEAT_ENTITY,
    PLATFORMS,
)

# Options that hold entity IDs; kept up to date when those entities are renamed.
ENTITY_OPTIONS = (
    CONF_SENSOR,
    CONF_HUMIDITY_SENSOR,
    CONF_HEATER,
    CONF_COOLER,
    CONF_FAN,
    CONF_DRYER,
    CONF_CONSENT_ENTITY,
    CONF_TAMPER_ENTITY,
    CONF_WATER_SENSOR,
    CONF_WATER_SETPOINT_HEAT_ENTITY,
    CONF_WATER_SETPOINT_COOL_ENTITY,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a thermostat created in the UI."""

    @callback
    def async_entity_renamed(event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        data = event.data
        if data["action"] != "update" or "entity_id" not in data["changes"]:
            return
        old, new = data["old_entity_id"], data["entity_id"]
        options = {
            key: new if key in ENTITY_OPTIONS and value == old else value
            for key, value in entry.options.items()
        }
        hass.config_entries.async_update_entry(entry, options=options)
        hass.config_entries.async_schedule_reload(entry.entry_id)

    entity_ids = [entry.options[key] for key in ENTITY_OPTIONS if entry.options.get(key)]
    entry.async_on_unload(
        async_track_entity_registry_updated_event(hass, entity_ids, async_entity_renamed)
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a thermostat created in the UI."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
