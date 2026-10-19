"""UI setup for the multi-mode generic thermostat.

YAML setup keeps working unchanged alongside it. Everything is stored in the
config entry's options, in the same shape as YAML, so both run through the same
schema (``schema.COMMON_SCHEMA``).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any, cast

import voluptuous as vol
from homeassistant.components.climate import HVACMode
from homeassistant.const import CONF_NAME, DEGREE
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaCommonFlowHandler,
    SchemaConfigFlowHandler,
    SchemaFlowError,
    SchemaFlowFormStep,
    SchemaFlowMenuStep,
)

from .const import (
    CONF_AWAY_TEMP,
    CONF_AWAY_TEMP_COOLER,
    CONF_AWAY_TEMP_HEATER,
    CONF_COLD_TOLERANCE,
    CONF_CONSENT_ENTITY,
    CONF_COOLER,
    CONF_DRYER,
    CONF_DRYER_BEHAVIOR,
    CONF_ENABLE_HEAT_COOL,
    CONF_FAN,
    CONF_FAN_BEHAVIOR,
    CONF_HEATER,
    CONF_HOT_TOLERANCE,
    CONF_HUMIDITY_SENSOR,
    CONF_INITIAL_HVAC_MODE,
    CONF_KEEP_ALIVE,
    CONF_MAX_TEMP,
    CONF_MIN_DUR,
    CONF_MIN_TEMP,
    CONF_PRECISION,
    CONF_REVERSE_CYCLE,
    CONF_SENSOR,
    CONF_TARGET_TEMP,
    CONF_TARGET_TEMP_HIGH,
    CONF_TARGET_TEMP_LOW,
    CONF_TEMP_STEP,
    DEFAULT_TOLERANCE,
    DOMAIN,
    Behavior,
)

# Anything homeassistant.turn_on/turn_off can switch and that reports on/off.
# YAML accepts any entity.
DEVICE_DOMAINS = ["switch", "input_boolean", "fan", "light", "group", "humidifier"]
SENSOR_DOMAINS = ["sensor", "input_number"]
DEVICE_KEYS = (CONF_HEATER, CONF_COOLER, CONF_FAN, CONF_DRYER)
STEPS = ["0.1", "0.5", "1.0"]

_TEMPERATURE = selector.NumberSelector(
    selector.NumberSelectorConfig(
        mode=selector.NumberSelectorMode.BOX, step=0.1, unit_of_measurement=DEGREE
    )
)
_TOLERANCE = selector.NumberSelector(
    selector.NumberSelectorConfig(
        mode=selector.NumberSelectorMode.BOX, min=0, step=0.1, unit_of_measurement=DEGREE
    )
)
_DURATION = selector.DurationSelector(selector.DurationSelectorConfig(allow_negative=False))
_DEVICE = selector.EntitySelector(selector.EntitySelectorConfig(domain=DEVICE_DOMAINS))
_SENSOR = selector.EntitySelector(selector.EntitySelectorConfig(domain=SENSOR_DOMAINS))
_BEHAVIOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[behavior.value for behavior in Behavior],
        mode=selector.SelectSelectorMode.DROPDOWN,
        translation_key="behavior",
    )
)
_STEP = selector.SelectSelector(
    selector.SelectSelectorConfig(options=STEPS, mode=selector.SelectSelectorMode.DROPDOWN)
)

DEVICES_SCHEMA = {
    vol.Required(CONF_SENSOR): _SENSOR,
    vol.Optional(CONF_HEATER): _DEVICE,
    vol.Optional(CONF_COOLER): _DEVICE,
    vol.Optional(CONF_FAN): _DEVICE,
    vol.Optional(CONF_DRYER): _DEVICE,
    vol.Optional(CONF_HUMIDITY_SENSOR): _SENSOR,
}


def _devices(options: Mapping[str, Any]) -> list[str]:
    return [key for key in DEVICE_KEYS if options.get(key)]


def _heat_cool_possible(options: Mapping[str, Any]) -> bool:
    return bool(options.get(CONF_HEATER) and options.get(CONF_COOLER))


def _has_behavior_step(options: Mapping[str, Any]) -> bool:
    """Whether there is anything to choose about how the devices work together."""
    return bool(options.get(CONF_FAN) or options.get(CONF_DRYER) or len(_devices(options)) > 1)


def _available_modes(options: Mapping[str, Any]) -> list[str]:
    modes = [HVACMode.OFF.value]
    for key, mode in (
        (CONF_HEATER, HVACMode.HEAT),
        (CONF_COOLER, HVACMode.COOL),
        (CONF_FAN, HVACMode.FAN_ONLY),
        (CONF_DRYER, HVACMode.DRY),
    ):
        if options.get(key):
            modes.append(mode.value)
    if _heat_cool_possible(options) and options.get(CONF_ENABLE_HEAT_COOL):
        modes.append(HVACMode.HEAT_COOL.value)
    return modes


async def _behavior_schema(handler: SchemaCommonFlowHandler) -> vol.Schema:
    options = handler.options
    schema: dict[vol.Marker, Any] = {}
    if _heat_cool_possible(options):
        schema[vol.Optional(CONF_ENABLE_HEAT_COOL, default=False)] = selector.BooleanSelector()
    if options.get(CONF_FAN):
        schema[vol.Required(CONF_FAN_BEHAVIOR, default=Behavior.NEUTRAL.value)] = _BEHAVIOR
    if options.get(CONF_DRYER):
        schema[vol.Required(CONF_DRYER_BEHAVIOR, default=Behavior.NEUTRAL.value)] = _BEHAVIOR
    if len(devices := _devices(options)) > 1:
        schema[vol.Optional(CONF_REVERSE_CYCLE)] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=devices,
                multiple=True,
                mode=selector.SelectSelectorMode.LIST,
                translation_key="device",
            )
        )
    return vol.Schema(schema)


async def _settings_schema(handler: SchemaCommonFlowHandler) -> vol.Schema:
    options = handler.options
    schema: dict[vol.Marker, Any] = {
        vol.Required(CONF_COLD_TOLERANCE, default=DEFAULT_TOLERANCE): _TOLERANCE,
        vol.Required(CONF_HOT_TOLERANCE, default=DEFAULT_TOLERANCE): _TOLERANCE,
        vol.Optional(CONF_TARGET_TEMP): _TEMPERATURE,
    }
    if _heat_cool_possible(options) and options.get(CONF_ENABLE_HEAT_COOL):
        schema[vol.Optional(CONF_TARGET_TEMP_LOW)] = _TEMPERATURE
        schema[vol.Optional(CONF_TARGET_TEMP_HIGH)] = _TEMPERATURE
    schema.update(
        {
            vol.Optional(CONF_MIN_TEMP): _TEMPERATURE,
            vol.Optional(CONF_MAX_TEMP): _TEMPERATURE,
            vol.Optional(CONF_MIN_DUR): _DURATION,
            vol.Optional(CONF_KEEP_ALIVE): _DURATION,
            vol.Optional(CONF_INITIAL_HVAC_MODE): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_available_modes(options),
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="hvac_mode",
                )
            ),
            vol.Optional(CONF_PRECISION): _STEP,
            vol.Optional(CONF_TEMP_STEP): _STEP,
        }
    )
    return vol.Schema(schema)


async def _presets_schema(handler: SchemaCommonFlowHandler) -> vol.Schema:
    options = handler.options
    schema: dict[vol.Marker, Any] = {vol.Optional(CONF_AWAY_TEMP): _TEMPERATURE}
    if options.get(CONF_HEATER):
        schema[vol.Optional(CONF_AWAY_TEMP_HEATER)] = _TEMPERATURE
    if options.get(CONF_COOLER):
        schema[vol.Optional(CONF_AWAY_TEMP_COOLER)] = _TEMPERATURE
    schema[vol.Optional(CONF_CONSENT_ENTITY)] = selector.EntitySelector()
    return vol.Schema(schema)


async def _validate_devices(
    handler: SchemaCommonFlowHandler, user_input: dict[str, Any]
) -> dict[str, Any]:
    if not _devices(user_input):
        raise SchemaFlowError("no_devices")
    return user_input


async def _validate_settings(
    handler: SchemaCommonFlowHandler, user_input: dict[str, Any]
) -> dict[str, Any]:
    low, high = user_input.get(CONF_MIN_TEMP), user_input.get(CONF_MAX_TEMP)
    if low is not None and high is not None and low >= high:
        raise SchemaFlowError("min_max_temp")
    low, high = user_input.get(CONF_TARGET_TEMP_LOW), user_input.get(CONF_TARGET_TEMP_HIGH)
    if low is not None and high is not None and low > high:
        raise SchemaFlowError("target_range")
    for key in (CONF_MIN_DUR, CONF_KEEP_ALIVE):
        if key in user_input and timedelta(**user_input[key]) <= timedelta(0):
            raise SchemaFlowError("zero_duration")
    return user_input


def _forget_hidden(options: dict[str, Any]) -> None:
    """Drop values the forms no longer show, after devices or heat/cool change.

    They couldn't be seen or cleared any more, and a stale choice (a removed
    device in reverse_cycle, a mode that no longer exists) would fail the form.
    """
    heat_cool = _heat_cool_possible(options) and options.get(CONF_ENABLE_HEAT_COOL)
    hidden = {
        CONF_FAN_BEHAVIOR: not options.get(CONF_FAN),
        CONF_DRYER_BEHAVIOR: not options.get(CONF_DRYER),
        CONF_ENABLE_HEAT_COOL: not _heat_cool_possible(options),
        CONF_TARGET_TEMP_LOW: not heat_cool,
        CONF_TARGET_TEMP_HIGH: not heat_cool,
        CONF_AWAY_TEMP_HEATER: not options.get(CONF_HEATER),
        CONF_AWAY_TEMP_COOLER: not options.get(CONF_COOLER),
        CONF_INITIAL_HVAC_MODE: options.get(CONF_INITIAL_HVAC_MODE)
        not in _available_modes(options),
    }
    for key, drop in hidden.items():
        if drop:
            options.pop(key, None)
    devices = _devices(options)
    reverse_cycle = [key for key in options.get(CONF_REVERSE_CYCLE, []) if key in devices]
    if len(devices) > 1 and reverse_cycle:
        options[CONF_REVERSE_CYCLE] = reverse_cycle
    else:
        options.pop(CONF_REVERSE_CYCLE, None)


async def _after_devices_create(options: dict[str, Any]) -> str:
    return "behavior" if _has_behavior_step(options) else "settings"


# When editing, these get the updated options; nothing is stale when creating.
async def _after_devices_edit(options: dict[str, Any]) -> str | None:
    _forget_hidden(options)
    return "behavior" if _has_behavior_step(options) else None


async def _after_behavior_edit(options: dict[str, Any]) -> None:
    _forget_hidden(options)


async def _menu(handler: SchemaCommonFlowHandler) -> list[str]:
    if _has_behavior_step(handler.options):
        return ["devices", "behavior", "settings", "presets"]
    return ["devices", "settings", "presets"]


CONFIG_FLOW = {
    "user": SchemaFlowFormStep(
        vol.Schema({vol.Required(CONF_NAME): selector.TextSelector(), **DEVICES_SCHEMA}),
        validate_user_input=_validate_devices,
        next_step=_after_devices_create,
    ),
    "behavior": SchemaFlowFormStep(_behavior_schema, next_step="settings"),
    "settings": SchemaFlowFormStep(
        _settings_schema, validate_user_input=_validate_settings, next_step="presets"
    ),
    "presets": SchemaFlowFormStep(_presets_schema),
}

OPTIONS_FLOW = {
    "init": SchemaFlowMenuStep(_menu),
    "devices": SchemaFlowFormStep(
        vol.Schema(DEVICES_SCHEMA),
        validate_user_input=_validate_devices,
        next_step=_after_devices_edit,
    ),
    "behavior": SchemaFlowFormStep(_behavior_schema, next_step=_after_behavior_edit),
    "settings": SchemaFlowFormStep(_settings_schema, validate_user_input=_validate_settings),
    "presets": SchemaFlowFormStep(_presets_schema),
}


class ConfigFlowHandler(SchemaConfigFlowHandler, domain=DOMAIN):
    """Create and edit thermostats from the UI."""

    config_flow = CONFIG_FLOW
    options_flow = OPTIONS_FLOW
    options_flow_reloads = True

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        """Return the entry title."""
        return cast(str, options[CONF_NAME])
