"""The dualmode_generic thermostat component."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

DOMAIN = "dualmode_generic"
PLATFORMS = ["climate"]


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the dualmode_generic component (YAML-based legacy support)."""
    # Legacy YAML platform setup is handled by climate.py async_setup_platform
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up dualmode_generic from a config entry (UI-based)."""
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload the entry to apply changes."""
    await hass.config_entries.async_reload(entry.entry_id)
