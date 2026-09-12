"""Config flow and Options flow for Multi-Mode Generic Thermostat."""
from __future__ import annotations

import uuid
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import DOMAIN

# ---------------------------------------------------------------------------
# Selector helpers — reusable selectors for entity pickers
# ---------------------------------------------------------------------------

ENTITY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
)
SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["sensor"])
)
CONSENT_ENTITY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["binary_sensor", "input_boolean", "calendar", "switch"])
)
TAMPER_ENTITY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["binary_sensor", "input_boolean"])
)
CLIMATE_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["climate"])
)
NUMBER_ENTITY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["input_number", "number", "sensor"])
)
DURATION_SELECTOR = selector.DurationSelector(
    selector.DurationSelectorConfig(enable_day=False)
)
TEMPERATURE_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX, step=0.1)
)
TOLERANCE_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(min=0.0, max=10.0, step=0.1, mode=selector.NumberSelectorMode.BOX)
)
PRECISION_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value="0.1", label="0.1"),
            selector.SelectOptionDict(value="0.5", label="0.5"),
            selector.SelectOptionDict(value="1.0", label="1.0"),
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)
FAN_BEHAVIOR_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value="cooler", label="Cooler"),
            selector.SelectOptionDict(value="heater", label="Heater"),
            selector.SelectOptionDict(value="neutral", label="Neutral"),
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)
DRYER_BEHAVIOR_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value="cooler", label="Cooler"),
            selector.SelectOptionDict(value="heater", label="Heater"),
            selector.SelectOptionDict(value="neutral", label="Neutral"),
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)
REVERSE_CYCLE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value="heater", label="Heater"),
            selector.SelectOptionDict(value="cooler", label="Cooler"),
            selector.SelectOptionDict(value="fan", label="Fan"),
            selector.SelectOptionDict(value="dryer", label="Dryer"),
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
        multiple=True,
    )
)
INITIAL_HVAC_MODE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value="off", label="Off"),
            selector.SelectOptionDict(value="heat", label="Heat"),
            selector.SelectOptionDict(value="cool", label="Cool"),
            selector.SelectOptionDict(value="heat_cool", label="Heat/Cool"),
            selector.SelectOptionDict(value="fan_only", label="Fan Only"),
            selector.SelectOptionDict(value="dry", label="Dry"),
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)


# ---------------------------------------------------------------------------
# Config Flow — multi-step initial setup
# ---------------------------------------------------------------------------


class DualModeGenericConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Multi-Mode Generic Thermostat."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get the options flow handler."""
        return DualModeGenericOptionsFlow(config_entry)

    # ---- Step 1: Base ----
    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Step 1 — Base configuration: name, temperature sensor, humidity sensor."""
        errors = {}
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_devices()

        schema = vol.Schema(
            {
                vol.Required("name", default="Generic Thermostat"): selector.TextSelector(),
                vol.Required("target_sensor"): SENSOR_SELECTOR,
                vol.Optional("target_humidity_sensor"): SENSOR_SELECTOR,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    # ---- Step 2: Devices ----
    async def async_step_devices(self, user_input: dict[str, Any] | None = None):
        """Step 2 — Devices: heater, cooler, fan, dryer, behaviors, reverse cycle."""
        errors = {}
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_temperature()

        schema = vol.Schema(
            {
                vol.Optional("heater"): ENTITY_SELECTOR,
                vol.Optional("cooler"): ENTITY_SELECTOR,
                vol.Optional("fan"): ENTITY_SELECTOR,
                vol.Optional("fan_behavior", default="neutral"): FAN_BEHAVIOR_SELECTOR,
                vol.Optional("dryer"): ENTITY_SELECTOR,
                vol.Optional("dryer_behavior", default="neutral"): DRYER_BEHAVIOR_SELECTOR,
                vol.Optional("reverse_cycle", default=[]): REVERSE_CYCLE_SELECTOR,
                vol.Optional("enable_heat_cool", default=False): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="devices", data_schema=schema, errors=errors)

    # ---- Step 3: Temperature & Control ----
    async def async_step_temperature(self, user_input: dict[str, Any] | None = None):
        """Step 3 — Temperature parameters: targets, tolerances, precision."""
        errors = {}
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_timing()

        schema = vol.Schema(
            {
                vol.Optional("target_temp"): TEMPERATURE_SELECTOR,
                vol.Optional("target_temp_high"): TEMPERATURE_SELECTOR,
                vol.Optional("target_temp_low"): TEMPERATURE_SELECTOR,
                vol.Optional("min_temp"): TEMPERATURE_SELECTOR,
                vol.Optional("max_temp"): TEMPERATURE_SELECTOR,
                vol.Optional("min_heat_temp"): TEMPERATURE_SELECTOR,
                vol.Optional("max_heat_temp"): TEMPERATURE_SELECTOR,
                vol.Optional("min_cool_temp"): TEMPERATURE_SELECTOR,
                vol.Optional("max_cool_temp"): TEMPERATURE_SELECTOR,
                vol.Optional("cold_tolerance", default=0.3): TOLERANCE_SELECTOR,
                vol.Optional("hot_tolerance", default=0.3): TOLERANCE_SELECTOR,
                vol.Optional("precision"): PRECISION_SELECTOR,
                vol.Optional("target_temp_step"): PRECISION_SELECTOR,
            }
        )
        return self.async_show_form(step_id="temperature", data_schema=schema, errors=errors)

    # ---- Step 4: Timing & Modes ----
    async def async_step_timing(self, user_input: dict[str, Any] | None = None):
        """Step 4 — Timing and modes: cycle duration, keep-alive, initial mode, away temps."""
        errors = {}
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_water_guard()

        schema = vol.Schema(
            {
                vol.Optional("min_cycle_duration"): DURATION_SELECTOR,
                vol.Optional("keep_alive"): DURATION_SELECTOR,
                vol.Optional("initial_hvac_mode", default="off"): INITIAL_HVAC_MODE_SELECTOR,
                vol.Optional("away_temp"): TEMPERATURE_SELECTOR,
                vol.Optional("away_temp_heater"): TEMPERATURE_SELECTOR,
                vol.Optional("away_temp_cooler"): TEMPERATURE_SELECTOR,
                vol.Optional("consent_entity"): CONSENT_ENTITY_SELECTOR,
                vol.Optional("tamper_entity"): TAMPER_ENTITY_SELECTOR,
                vol.Optional("command_climate"): CLIMATE_SELECTOR,
            }
        )
        return self.async_show_form(step_id="timing", data_schema=schema, errors=errors)

    # ---- Step 5: Water Guard ----
    async def async_step_water_guard(self, user_input: dict[str, Any] | None = None):
        """Step 5 — Water temperature guard: sensor, setpoints, tolerance."""
        errors = {}
        if user_input is not None:
            self._data.update(user_input)
            return self._create_entry()

        schema = vol.Schema(
            {
                vol.Optional("water_sensor"): SENSOR_SELECTOR,
                vol.Optional("water_setpoint_heat"): TEMPERATURE_SELECTOR,
                vol.Optional("water_setpoint_cool"): TEMPERATURE_SELECTOR,
                vol.Optional("water_setpoint_heat_entity"): NUMBER_ENTITY_SELECTOR,
                vol.Optional("water_setpoint_cool_entity"): NUMBER_ENTITY_SELECTOR,
                vol.Optional("water_tolerance", default=0.3): TOLERANCE_SELECTOR,
            }
        )
        return self.async_show_form(step_id="water_guard", data_schema=schema, errors=errors)

    # ---- Create entry ----
    def _create_entry(self):
        """Create the config entry with all collected data."""
        # Auto-generate unique_id
        self._data["unique_id"] = str(uuid.uuid4())
        title = self._data.get("name", "Generic Thermostat")
        return self.async_create_entry(title=title, data=self._data)


# ---------------------------------------------------------------------------
# Options Flow — menu-based editing by category
# ---------------------------------------------------------------------------


class DualModeGenericOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Multi-Mode Generic Thermostat."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    def _get(self, key: str, default=None):
        """Get current value from options (if previously changed) or data (initial config)."""
        return self._config_entry.options.get(
            key, self._config_entry.data.get(key, default)
        )

    # ---- Menu ----
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["devices", "temperature", "timing", "water_guard"],
        )

    # ---- Devices ----
    async def async_step_devices(self, user_input: dict[str, Any] | None = None):
        """Edit device entities and behaviors."""
        if user_input is not None:
            return self.async_create_entry(
                title="", data={**self._config_entry.options, **user_input}
            )

        schema = vol.Schema(
            {
                vol.Optional("heater", description={"suggested_value": self._get("heater", "")}): ENTITY_SELECTOR,
                vol.Optional("cooler", description={"suggested_value": self._get("cooler", "")}): ENTITY_SELECTOR,
                vol.Optional("fan", description={"suggested_value": self._get("fan", "")}): ENTITY_SELECTOR,
                vol.Optional("fan_behavior", default=self._get("fan_behavior", "neutral")): FAN_BEHAVIOR_SELECTOR,
                vol.Optional("dryer", description={"suggested_value": self._get("dryer", "")}): ENTITY_SELECTOR,
                vol.Optional("dryer_behavior", default=self._get("dryer_behavior", "neutral")): DRYER_BEHAVIOR_SELECTOR,
                vol.Optional("reverse_cycle", default=self._get("reverse_cycle", [])): REVERSE_CYCLE_SELECTOR,
                vol.Optional("enable_heat_cool", default=self._get("enable_heat_cool", False)): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="devices", data_schema=schema)

    # ---- Temperature ----
    async def async_step_temperature(self, user_input: dict[str, Any] | None = None):
        """Edit temperature parameters."""
        if user_input is not None:
            return self.async_create_entry(
                title="", data={**self._config_entry.options, **user_input}
            )

        schema = vol.Schema(
            {
                vol.Optional("target_temp", description={"suggested_value": self._get("target_temp")}): TEMPERATURE_SELECTOR,
                vol.Optional("target_temp_high", description={"suggested_value": self._get("target_temp_high")}): TEMPERATURE_SELECTOR,
                vol.Optional("target_temp_low", description={"suggested_value": self._get("target_temp_low")}): TEMPERATURE_SELECTOR,
                vol.Optional("min_temp", description={"suggested_value": self._get("min_temp")}): TEMPERATURE_SELECTOR,
                vol.Optional("max_temp", description={"suggested_value": self._get("max_temp")}): TEMPERATURE_SELECTOR,
                vol.Optional("min_heat_temp", description={"suggested_value": self._get("min_heat_temp")}): TEMPERATURE_SELECTOR,
                vol.Optional("max_heat_temp", description={"suggested_value": self._get("max_heat_temp")}): TEMPERATURE_SELECTOR,
                vol.Optional("min_cool_temp", description={"suggested_value": self._get("min_cool_temp")}): TEMPERATURE_SELECTOR,
                vol.Optional("max_cool_temp", description={"suggested_value": self._get("max_cool_temp")}): TEMPERATURE_SELECTOR,
                vol.Optional("cold_tolerance", default=self._get("cold_tolerance", 0.3)): TOLERANCE_SELECTOR,
                vol.Optional("hot_tolerance", default=self._get("hot_tolerance", 0.3)): TOLERANCE_SELECTOR,
                vol.Optional("precision", description={"suggested_value": self._get("precision")}): PRECISION_SELECTOR,
                vol.Optional("target_temp_step", description={"suggested_value": self._get("target_temp_step")}): PRECISION_SELECTOR,
            }
        )
        return self.async_show_form(step_id="temperature", data_schema=schema)

    # ---- Timing & Modes ----
    async def async_step_timing(self, user_input: dict[str, Any] | None = None):
        """Edit timing and mode options."""
        if user_input is not None:
            return self.async_create_entry(
                title="", data={**self._config_entry.options, **user_input}
            )

        schema = vol.Schema(
            {
                vol.Optional("min_cycle_duration", description={"suggested_value": self._get("min_cycle_duration")}): DURATION_SELECTOR,
                vol.Optional("keep_alive", description={"suggested_value": self._get("keep_alive")}): DURATION_SELECTOR,
                vol.Optional("initial_hvac_mode", default=self._get("initial_hvac_mode", "off")): INITIAL_HVAC_MODE_SELECTOR,
                vol.Optional("away_temp", description={"suggested_value": self._get("away_temp")}): TEMPERATURE_SELECTOR,
                vol.Optional("away_temp_heater", description={"suggested_value": self._get("away_temp_heater")}): TEMPERATURE_SELECTOR,
                vol.Optional("away_temp_cooler", description={"suggested_value": self._get("away_temp_cooler")}): TEMPERATURE_SELECTOR,
                vol.Optional("consent_entity", description={"suggested_value": self._get("consent_entity", "")}): CONSENT_ENTITY_SELECTOR,
                vol.Optional("tamper_entity", description={"suggested_value": self._get("tamper_entity", "")}): TAMPER_ENTITY_SELECTOR,
                vol.Optional("command_climate", description={"suggested_value": self._get("command_climate", "")}): CLIMATE_SELECTOR,
            }
        )
        return self.async_show_form(step_id="timing", data_schema=schema)

    # ---- Water Guard ----
    async def async_step_water_guard(self, user_input: dict[str, Any] | None = None):
        """Edit water temperature guard options."""
        if user_input is not None:
            return self.async_create_entry(
                title="", data={**self._config_entry.options, **user_input}
            )

        schema = vol.Schema(
            {
                vol.Optional("water_sensor", description={"suggested_value": self._get("water_sensor", "")}): SENSOR_SELECTOR,
                vol.Optional("water_setpoint_heat", description={"suggested_value": self._get("water_setpoint_heat")}): TEMPERATURE_SELECTOR,
                vol.Optional("water_setpoint_cool", description={"suggested_value": self._get("water_setpoint_cool")}): TEMPERATURE_SELECTOR,
                vol.Optional("water_setpoint_heat_entity", description={"suggested_value": self._get("water_setpoint_heat_entity", "")}): NUMBER_ENTITY_SELECTOR,
                vol.Optional("water_setpoint_cool_entity", description={"suggested_value": self._get("water_setpoint_cool_entity", "")}): NUMBER_ENTITY_SELECTOR,
                vol.Optional("water_tolerance", default=self._get("water_tolerance", 0.3)): TOLERANCE_SELECTOR,
            }
        )
        return self.async_show_form(step_id="water_guard", data_schema=schema)
