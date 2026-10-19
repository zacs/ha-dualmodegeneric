"""UI setup for the multi-mode generic thermostat.

YAML setup keeps working unchanged alongside it. Everything is stored in the
config entry's options, in the same shape as YAML, so both run through the same
schema (``schema.COMMON_SCHEMA``). Forms group some options in collapsible
sections; those are flattened again when saved.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from datetime import timedelta
from typing import Any, cast

import voluptuous as vol
from homeassistant.components.climate import HVACMode
from homeassistant.const import CONF_NAME, DEGREE
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaCommonFlowHandler,
    SchemaConfigFlowHandler,
    SchemaFlowError,
    SchemaFlowFormStep,
    SchemaFlowMenuStep,
)

from .const import (
    CONF_COLD_TOLERANCE,
    CONF_CONSENT_ENTITY,
    CONF_COOLDOWN,
    CONF_COOLER,
    CONF_COOLER_COLD_TOLERANCE,
    CONF_COOLER_HOT_TOLERANCE,
    CONF_DRYER,
    CONF_DRYER_BEHAVIOR,
    CONF_ENABLE_HEAT_COOL,
    CONF_FAN,
    CONF_FAN_BEHAVIOR,
    CONF_FAN_OFF_DELAY,
    CONF_FAN_WITH,
    CONF_HEATER,
    CONF_HEATER_COLD_TOLERANCE,
    CONF_HEATER_HOT_TOLERANCE,
    CONF_HOT_TOLERANCE,
    CONF_HUMIDITY_SENSOR,
    CONF_INITIAL_HVAC_MODE,
    CONF_KEEP_ALIVE,
    CONF_MAX_DUR,
    CONF_MAX_TEMP,
    CONF_MIN_DUR,
    CONF_MIN_TEMP,
    CONF_PRECISION,
    CONF_REVERSE_CYCLE,
    CONF_SENSOR,
    CONF_TAMPER_ENTITY,
    CONF_TARGET_TEMP,
    CONF_TARGET_TEMP_HIGH,
    CONF_TARGET_TEMP_LOW,
    CONF_TEMP_STEP,
    CONF_WATER_SENSOR,
    CONF_WATER_SETPOINT_COOL,
    CONF_WATER_SETPOINT_COOL_ENTITY,
    CONF_WATER_SETPOINT_HEAT,
    CONF_WATER_SETPOINT_HEAT_ENTITY,
    CONF_WATER_TOLERANCE,
    DEFAULT_TOLERANCE,
    DOMAIN,
    PRESETS,
    Behavior,
    preset_keys,
)

# Anything homeassistant.turn_on/turn_off can switch and that reports on/off.
# YAML accepts any entity.
DEVICE_DOMAINS = ["switch", "input_boolean", "fan", "light", "group", "humidifier"]
SENSOR_DOMAINS = ["sensor", "input_number"]
SETPOINT_DOMAINS = ["input_number", "number", "sensor"]
DEVICE_KEYS = (CONF_HEATER, CONF_COOLER, CONF_FAN, CONF_DRYER)
STEPS = ["0.1", "0.5", "1.0"]

TOLERANCES_SECTION = "device_tolerances"
WATER_SECTION = "water_guard"
DEVICE_TOLERANCE_KEYS = (
    CONF_HEATER_COLD_TOLERANCE,
    CONF_HEATER_HOT_TOLERANCE,
    CONF_COOLER_COLD_TOLERANCE,
    CONF_COOLER_HOT_TOLERANCE,
)
WATER_HEAT_KEYS = (CONF_WATER_SETPOINT_HEAT, CONF_WATER_SETPOINT_HEAT_ENTITY)
WATER_COOL_KEYS = (CONF_WATER_SETPOINT_COOL, CONF_WATER_SETPOINT_COOL_ENTITY)

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
_SETPOINT = selector.EntitySelector(selector.EntitySelectorConfig(domain=SETPOINT_DOMAINS))
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


def _devices_select(devices: list[str]) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=devices,
            multiple=True,
            mode=selector.SelectSelectorMode.LIST,
            translation_key="device",
        )
    )


def _heat_cool_possible(options: Mapping[str, Any]) -> bool:
    return bool(options.get(CONF_HEATER) and options.get(CONF_COOLER))


def _fan_followable(options: Mapping[str, Any]) -> list[str]:
    """Return the devices the fan could run alongside."""
    if not options.get(CONF_FAN):
        return []
    return [key for key in (CONF_HEATER, CONF_COOLER) if options.get(key)]


def _has_behavior_step(options: Mapping[str, Any]) -> bool:
    """Whether there is anything to choose about how the devices work together."""
    return bool(options.get(CONF_FAN) or options.get(CONF_DRYER) or len(_devices(options)) > 1)


def _does(options: Mapping[str, Any], behavior: Behavior) -> bool:
    """Whether any device heats (or cools), so the water guard applies to it."""
    device = CONF_HEATER if behavior is Behavior.HEATER else CONF_COOLER
    return bool(
        options.get(device)
        or (options.get(CONF_FAN) and options.get(CONF_FAN_BEHAVIOR) == behavior)
        or (options.get(CONF_DRYER) and options.get(CONF_DRYER_BEHAVIOR) == behavior)
    )


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


def _section(fields: dict[vol.Marker, Any], options: Mapping[str, Any]) -> section:
    """Return a collapsible section, open when any of its options is set."""
    keys = [str(key) for key in fields]
    return section(vol.Schema(fields), {"collapsed": not any(key in options for key in keys)})


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
        schema[vol.Optional(CONF_REVERSE_CYCLE)] = _devices_select(devices)
    if followable := _fan_followable(options):
        schema[vol.Optional(CONF_FAN_WITH)] = _devices_select(followable)
        schema[vol.Optional(CONF_FAN_OFF_DELAY)] = _DURATION
    return vol.Schema(schema)


async def _settings_schema(handler: SchemaCommonFlowHandler) -> vol.Schema:
    options = handler.options
    schema: dict[vol.Marker, Any] = {
        vol.Required(CONF_COLD_TOLERANCE, default=DEFAULT_TOLERANCE): _TOLERANCE,
        vol.Required(CONF_HOT_TOLERANCE, default=DEFAULT_TOLERANCE): _TOLERANCE,
    }
    if _heat_cool_possible(options):
        schema[vol.Optional(TOLERANCES_SECTION, default={})] = _section(
            {vol.Optional(key): _TOLERANCE for key in DEVICE_TOLERANCE_KEYS}, options
        )
    schema[vol.Optional(CONF_TARGET_TEMP)] = _TEMPERATURE
    if _heat_cool_possible(options) and options.get(CONF_ENABLE_HEAT_COOL):
        schema[vol.Optional(CONF_TARGET_TEMP_LOW)] = _TEMPERATURE
        schema[vol.Optional(CONF_TARGET_TEMP_HIGH)] = _TEMPERATURE
    schema.update(
        {
            vol.Optional(CONF_MIN_TEMP): _TEMPERATURE,
            vol.Optional(CONF_MAX_TEMP): _TEMPERATURE,
            vol.Optional(CONF_MIN_DUR): _DURATION,
            vol.Optional(CONF_MAX_DUR): _DURATION,
            vol.Optional(CONF_COOLDOWN): _DURATION,
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
    schema: dict[vol.Marker, Any] = {}
    for preset in PRESETS:
        single, heat, cool = preset_keys(preset)
        fields: dict[vol.Marker, Any] = {vol.Optional(single): _TEMPERATURE}
        if options.get(CONF_HEATER):
            fields[vol.Optional(heat)] = _TEMPERATURE
        if options.get(CONF_COOLER):
            fields[vol.Optional(cool)] = _TEMPERATURE
        schema[vol.Optional(preset, default={})] = _section(fields, options)
    return vol.Schema(schema)


async def _interlocks_schema(handler: SchemaCommonFlowHandler) -> vol.Schema:
    options = handler.options
    schema: dict[vol.Marker, Any] = {
        vol.Optional(CONF_CONSENT_ENTITY): selector.EntitySelector(),
        vol.Optional(CONF_TAMPER_ENTITY): selector.EntitySelector(),
    }
    heats, cools = _does(options, Behavior.HEATER), _does(options, Behavior.COOLER)
    if heats or cools:
        fields: dict[vol.Marker, Any] = {vol.Optional(CONF_WATER_SENSOR): _SENSOR}
        if heats:
            fields[vol.Optional(CONF_WATER_SETPOINT_HEAT)] = _TEMPERATURE
            fields[vol.Optional(CONF_WATER_SETPOINT_HEAT_ENTITY)] = _SETPOINT
        if cools:
            fields[vol.Optional(CONF_WATER_SETPOINT_COOL)] = _TEMPERATURE
            fields[vol.Optional(CONF_WATER_SETPOINT_COOL_ENTITY)] = _SETPOINT
        fields[vol.Optional(CONF_WATER_TOLERANCE)] = _TOLERANCE
        schema[vol.Optional(WATER_SECTION, default={})] = _section(fields, options)
    return vol.Schema(schema)


def _check_durations(user_input: Mapping[str, Any], *keys: str) -> None:
    for key in keys:
        if key in user_input and timedelta(**user_input[key]) <= timedelta(0):
            raise SchemaFlowError("zero_duration")


async def _validate_devices(
    handler: SchemaCommonFlowHandler, user_input: dict[str, Any]
) -> dict[str, Any]:
    if not _devices(user_input):
        raise SchemaFlowError("no_devices")
    return user_input


async def _validate_behavior(
    handler: SchemaCommonFlowHandler, user_input: dict[str, Any]
) -> dict[str, Any]:
    if user_input.get(CONF_FAN_WITH) and CONF_FAN in user_input.get(CONF_REVERSE_CYCLE, []):
        raise SchemaFlowError("fan_with_reverse_cycle")
    _check_durations(user_input, CONF_FAN_OFF_DELAY)
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
    _check_durations(user_input, CONF_MIN_DUR, CONF_MAX_DUR, CONF_COOLDOWN, CONF_KEEP_ALIVE)
    if (
        CONF_MIN_DUR in user_input
        and CONF_MAX_DUR in user_input
        and timedelta(**user_input[CONF_MAX_DUR]) <= timedelta(**user_input[CONF_MIN_DUR])
    ):
        raise SchemaFlowError("max_below_min")
    return user_input


async def _validate_interlocks(
    handler: SchemaCommonFlowHandler, user_input: dict[str, Any]
) -> dict[str, Any]:
    if not user_input.get(CONF_WATER_SENSOR) and any(
        key in user_input for key in (*WATER_HEAT_KEYS, *WATER_COOL_KEYS)
    ):
        raise SchemaFlowError("water_needs_sensor")
    return user_input


type _Validator = Callable[[SchemaCommonFlowHandler, dict[str, Any]], Awaitable[dict[str, Any]]]
type _SchemaBuilder = Callable[[SchemaCommonFlowHandler], Awaitable[vol.Schema]]


def _sections(schema: vol.Schema) -> dict[str, section]:
    return {str(key): value for key, value in schema.schema.items() if isinstance(value, section)}


def _with_sections(build: _SchemaBuilder, validate: _Validator | None = None) -> dict[str, Any]:
    """Return form step arguments that keep sectioned options flat.

    The form gets each section's options nested under it as suggested values;
    on submit the sections are flattened, and options a section left empty are
    removed, before ``validate`` sees the input.
    """

    async def suggested_values(handler: SchemaCommonFlowHandler) -> dict[str, Any]:
        suggested = dict(handler.options)
        for name, sub in _sections(await build(handler)).items():
            suggested[name] = {
                str(key): handler.options[str(key)]
                for key in sub.schema.schema
                if str(key) in handler.options
            }
        return suggested

    async def validate_user_input(
        handler: SchemaCommonFlowHandler, user_input: dict[str, Any]
    ) -> dict[str, Any]:
        sections = _sections(await build(handler))
        flat: dict[str, Any] = {}
        for key, value in user_input.items():
            if key in sections:
                flat.update(value)
            else:
                flat[key] = value
        if validate is not None:
            flat = await validate(handler, flat)
        for sub in sections.values():
            for key in sub.schema.schema:
                handler.options.pop(str(key), None)
        return flat

    return {"suggested_values": suggested_values, "validate_user_input": validate_user_input}


def _forget_hidden(options: dict[str, Any]) -> None:
    """Drop values the forms no longer show, after devices or behaviors change.

    They couldn't be seen or cleared any more, and a stale choice (a removed
    device in reverse_cycle, a mode that no longer exists) would fail the form.
    """
    heat_cool = _heat_cool_possible(options) and options.get(CONF_ENABLE_HEAT_COOL)
    heater, cooler = bool(options.get(CONF_HEATER)), bool(options.get(CONF_COOLER))
    heats, cools = _does(options, Behavior.HEATER), _does(options, Behavior.COOLER)
    hidden = {
        CONF_FAN_BEHAVIOR: not options.get(CONF_FAN),
        CONF_DRYER_BEHAVIOR: not options.get(CONF_DRYER),
        CONF_ENABLE_HEAT_COOL: not _heat_cool_possible(options),
        CONF_TARGET_TEMP_LOW: not heat_cool,
        CONF_TARGET_TEMP_HIGH: not heat_cool,
        CONF_INITIAL_HVAC_MODE: options.get(CONF_INITIAL_HVAC_MODE)
        not in _available_modes(options),
        **dict.fromkeys(DEVICE_TOLERANCE_KEYS, not _heat_cool_possible(options)),
        **{preset_keys(preset)[1]: not heater for preset in PRESETS},
        **{preset_keys(preset)[2]: not cooler for preset in PRESETS},
        **dict.fromkeys(WATER_HEAT_KEYS, not heats),
        **dict.fromkeys(WATER_COOL_KEYS, not cools),
        **dict.fromkeys((CONF_WATER_SENSOR, CONF_WATER_TOLERANCE), not (heats or cools)),
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
    followable = _fan_followable(options)
    if fan_with := [key for key in options.get(CONF_FAN_WITH, []) if key in followable]:
        options[CONF_FAN_WITH] = fan_with
    else:
        options.pop(CONF_FAN_WITH, None)
        options.pop(CONF_FAN_OFF_DELAY, None)


async def _after_devices_create(options: dict[str, Any]) -> str:
    return "behavior" if _has_behavior_step(options) else "settings"


# When editing, these get the updated options; nothing is stale when creating.
async def _after_devices_edit(options: dict[str, Any]) -> str | None:
    _forget_hidden(options)
    return "behavior" if _has_behavior_step(options) else None


async def _after_behavior_edit(options: dict[str, Any]) -> None:
    _forget_hidden(options)


async def _menu(handler: SchemaCommonFlowHandler) -> list[str]:
    steps = ["devices", "behavior", "settings", "presets", "interlocks"]
    if not _has_behavior_step(handler.options):
        steps.remove("behavior")
    return steps


CONFIG_FLOW = {
    "user": SchemaFlowFormStep(
        vol.Schema({vol.Required(CONF_NAME): selector.TextSelector(), **DEVICES_SCHEMA}),
        validate_user_input=_validate_devices,
        next_step=_after_devices_create,
    ),
    "behavior": SchemaFlowFormStep(
        _behavior_schema, validate_user_input=_validate_behavior, next_step="settings"
    ),
    "settings": SchemaFlowFormStep(
        _settings_schema,
        next_step="presets",
        **_with_sections(_settings_schema, _validate_settings),
    ),
    "presets": SchemaFlowFormStep(
        _presets_schema, next_step="interlocks", **_with_sections(_presets_schema)
    ),
    "interlocks": SchemaFlowFormStep(
        _interlocks_schema, **_with_sections(_interlocks_schema, _validate_interlocks)
    ),
}

OPTIONS_FLOW = {
    "init": SchemaFlowMenuStep(_menu),
    "devices": SchemaFlowFormStep(
        vol.Schema(DEVICES_SCHEMA),
        validate_user_input=_validate_devices,
        next_step=_after_devices_edit,
    ),
    "behavior": SchemaFlowFormStep(
        _behavior_schema, validate_user_input=_validate_behavior, next_step=_after_behavior_edit
    ),
    "settings": SchemaFlowFormStep(
        _settings_schema, **_with_sections(_settings_schema, _validate_settings)
    ),
    "presets": SchemaFlowFormStep(_presets_schema, **_with_sections(_presets_schema)),
    "interlocks": SchemaFlowFormStep(
        _interlocks_schema, **_with_sections(_interlocks_schema, _validate_interlocks)
    ),
}


class ConfigFlowHandler(SchemaConfigFlowHandler, domain=DOMAIN):
    """Create and edit thermostats from the UI."""

    config_flow = CONFIG_FLOW
    options_flow = OPTIONS_FLOW
    options_flow_reloads = True

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        """Return the entry title."""
        return cast(str, options[CONF_NAME])
