"""Diagnostics for thermostats created in the UI."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import ENTITY_OPTIONS
from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return the configuration and the state of everything the thermostat uses."""
    entity_id = er.async_get(hass).async_get_entity_id(CLIMATE_DOMAIN, DOMAIN, entry.entry_id)
    thermostat = hass.states.get(entity_id) if entity_id else None
    sources = {}
    for key in ENTITY_OPTIONS:
        if source := entry.options.get(key):
            state = hass.states.get(source)
            sources[key] = {
                "entity_id": source,
                "state": state.state if state else None,
                "last_changed": state.last_changed.isoformat() if state else None,
            }
    return {
        "options": dict(entry.options),
        "thermostat": thermostat.as_dict() if thermostat else None,
        "sources": sources,
    }
