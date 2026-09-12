"""
Adds support for generic thermostat units that have both heating and cooling.

Originally based on the script at this thread:
https://community.home-assistant.io/t/heat-cool-generic-thermostat/76443/2

Modified to better conform to modern Home Assistant custom_component style.
"""
import asyncio
import collections
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.climate import PLATFORM_SCHEMA, ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_PRESET_MODE,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_STEP,
    PRESET_AWAY,
    PRESET_NONE,
)

from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
)
from homeassistant.components.zwave_js.config_validation import boolean

from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    CONF_NAME,
    CONF_UNIQUE_ID,
    EVENT_HOMEASSISTANT_START,
    PRECISION_HALVES,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_ON,
    STATE_UNKNOWN,
    STATE_UNAVAILABLE,
)
from homeassistant.core import DOMAIN as HA_DOMAIN, CoreState
from homeassistant.helpers import condition
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.core import Event, EventStateChangedData, callback
from homeassistant.helpers.reload import async_setup_reload_service
from homeassistant.helpers.restore_state import RestoreEntity
Callable = collections.abc.Callable

from . import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)

# CONSTANTS from Enum to adhere to the new ClimateEntityFeature
HVAC_MODE_COOL = HVACMode.COOL
HVAC_MODE_HEAT = HVACMode.HEAT
HVAC_MODE_FAN_ONLY = HVACMode.FAN_ONLY
HVAC_MODE_DRY = HVACMode.DRY
HVAC_MODE_OFF = HVACMode.OFF
HVAC_MODE_HEAT_COOL = HVACMode.HEAT_COOL

CURRENT_HVAC_COOL = HVACAction.COOLING
CURRENT_HVAC_HEAT = HVACAction.HEATING
CURRENT_HVAC_FAN = HVACAction.FAN
CURRENT_HVAC_DRY = HVACAction.DRYING
CURRENT_HVAC_IDLE = HVACAction.IDLE
CURRENT_HVAC_OFF = HVACAction.OFF

SUPPORT_TARGET_TEMPERATURE = ClimateEntityFeature.TARGET_TEMPERATURE
SUPPORT_TARGET_TEMPERATURE_RANGE = ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
SUPPORT_PRESET_MODE = ClimateEntityFeature.PRESET_MODE
SUPPORT_TURN_ON = ClimateEntityFeature.TURN_ON
SUPPORT_TURN_OFF = ClimateEntityFeature.TURN_OFF
# END OF CONSTANTS


DEFAULT_TOLERANCE = 0.3
DEFAULT_NAME = "Generic Thermostat"

CONF_HEATER = "heater"
CONF_COOLER = "cooler"
CONF_FAN = "fan"
CONF_FAN_BEHAVIOR = "fan_behavior"
CONF_DRYER = "dryer"
CONF_DRYER_BEHAVIOR = "dryer_behavior"
CONF_REVERSE_CYCLE = "reverse_cycle"
CONF_SENSOR = "target_sensor"
CONF_HUMIDITY_SENSOR = "target_humidity_sensor"
CONF_CONSENT_ENTITY = "consent_entity"  # Optional entity to control thermostat enable/disable
CONF_TAMPER_ENTITY = "tamper_entity"  # Optional entity that, when ON, forces the thermostat inactive (inverse consent)
CONF_COMMAND_CLIMATE = "command_climate"  # Optional physical climate device used as a command panel (on/off + setpoint)
CONF_MIN_HEAT_TEMP = "min_heat_temp"  # Optional lower clamp for heating setpoint synced from command_climate
CONF_MAX_HEAT_TEMP = "max_heat_temp"  # Optional upper clamp for heating setpoint synced from command_climate
CONF_MIN_COOL_TEMP = "min_cool_temp"  # Optional lower clamp for cooling setpoint synced from command_climate
CONF_MAX_COOL_TEMP = "max_cool_temp"  # Optional upper clamp for cooling setpoint synced from command_climate
CONF_WATER_SENSOR = "water_sensor"  # Optional water supply temperature sensor
CONF_WATER_SETPOINT_HEAT = "water_setpoint_heat"  # Fixed water temp setpoint for heating (water must be >= this)
CONF_WATER_SETPOINT_COOL = "water_setpoint_cool"  # Fixed water temp setpoint for cooling (water must be <= this)
CONF_WATER_SETPOINT_HEAT_ENTITY = "water_setpoint_heat_entity"  # Dynamic water setpoint entity for heating
CONF_WATER_SETPOINT_COOL_ENTITY = "water_setpoint_cool_entity"  # Dynamic water setpoint entity for cooling
CONF_WATER_TOLERANCE = "water_tolerance"  # Optional tolerance for water temperature guard
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"
CONF_TARGET_TEMP_HIGH = "target_temp_high"
CONF_TARGET_TEMP_LOW = "target_temp_low"
CONF_TARGET_TEMP = "target_temp"
CONF_MIN_DUR = "min_cycle_duration"
CONF_COLD_TOLERANCE = "cold_tolerance"
CONF_HOT_TOLERANCE = "hot_tolerance"
CONF_KEEP_ALIVE = "keep_alive"
CONF_INITIAL_HVAC_MODE = "initial_hvac_mode"
CONF_AWAY_TEMP = "away_temp"
CONF_AWAY_TEMP_HEATER = "away_temp_heater"
CONF_AWAY_TEMP_COOLER = "away_temp_cooler"
CONF_PRECISION = "precision"
CONF_TEMP_STEP = "target_temp_step"
SUPPORT_FLAGS = SUPPORT_TARGET_TEMPERATURE | SUPPORT_TURN_ON | SUPPORT_TURN_OFF

CONF_ENABLE_HEAT_COOL = "enable_heat_cool"

FAN_MODE_COOL = "cooler"
FAN_MODE_HEAT = "heater"
FAN_MODE_NEUTRAL = "neutral"
DRYER_MODE_COOL = "cooler"
DRYER_MODE_HEAT = "heater"
DRYER_MODE_NEUTRAL = "neutral"

REVERSE_CYCLE_IS_HEATER = "heater"
REVERSE_CYCLE_IS_COOLER = "cooler"
REVERSE_CYCLE_IS_FAN = "fan"
REVERSE_CYCLE_IS_DRYER = "dryer"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_HEATER): cv.entity_id,
        vol.Optional(CONF_COOLER): cv.entity_id,
        vol.Optional(CONF_SENSOR): cv.entity_id,
        vol.Optional(CONF_HUMIDITY_SENSOR): cv.entity_id,
        vol.Optional(CONF_CONSENT_ENTITY): cv.entity_id,
        vol.Optional(CONF_TAMPER_ENTITY): cv.entity_id,
        vol.Optional(CONF_COMMAND_CLIMATE): cv.entity_id,
        vol.Optional(CONF_MIN_HEAT_TEMP): vol.Coerce(float),
        vol.Optional(CONF_MAX_HEAT_TEMP): vol.Coerce(float),
        vol.Optional(CONF_MIN_COOL_TEMP): vol.Coerce(float),
        vol.Optional(CONF_MAX_COOL_TEMP): vol.Coerce(float),
        vol.Optional(CONF_FAN): cv.entity_id,
        vol.Optional(CONF_FAN_BEHAVIOR, default=FAN_MODE_NEUTRAL): vol.In(
            [FAN_MODE_COOL, FAN_MODE_HEAT, FAN_MODE_NEUTRAL]),
        vol.Optional(CONF_DRYER): cv.entity_id,
        vol.Optional(CONF_DRYER_BEHAVIOR, default=DRYER_MODE_NEUTRAL): vol.In(
            [DRYER_MODE_COOL, DRYER_MODE_HEAT, DRYER_MODE_NEUTRAL]),
        vol.Optional(CONF_MAX_TEMP): vol.Coerce(float),
        vol.Optional(CONF_MIN_DUR): vol.All(cv.time_period, cv.positive_timedelta),
        vol.Optional(CONF_MIN_TEMP): vol.Coerce(float),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_REVERSE_CYCLE, default=[]): cv.ensure_list_csv,
        vol.Optional(CONF_COLD_TOLERANCE, default=DEFAULT_TOLERANCE): vol.Coerce(float),
        vol.Optional(CONF_HOT_TOLERANCE, default=DEFAULT_TOLERANCE): vol.Coerce(float),
        vol.Optional(CONF_TARGET_TEMP): vol.Coerce(float),
        vol.Optional(CONF_TARGET_TEMP_HIGH): vol.Coerce(float),
        vol.Optional(CONF_TARGET_TEMP_LOW): vol.Coerce(float),
        vol.Optional(CONF_KEEP_ALIVE): vol.All(cv.time_period, cv.positive_timedelta),
        vol.Optional(CONF_ENABLE_HEAT_COOL, default=False): vol.Boolean(),
        vol.Optional(CONF_INITIAL_HVAC_MODE): vol.In(
            [HVAC_MODE_COOL, HVAC_MODE_HEAT, HVAC_MODE_FAN_ONLY, HVAC_MODE_DRY, HVAC_MODE_OFF, HVAC_MODE_HEAT_COOL]
        ),
        vol.Optional(CONF_AWAY_TEMP): vol.Coerce(float),
        vol.Optional(CONF_AWAY_TEMP_HEATER): vol.Coerce(float),
        vol.Optional(CONF_AWAY_TEMP_COOLER): vol.Coerce(float),
        vol.Optional(CONF_PRECISION): vol.In(
            [PRECISION_TENTHS, PRECISION_HALVES, PRECISION_WHOLE]
        ),
        vol.Optional(CONF_TEMP_STEP): vol.In(
            [PRECISION_TENTHS, PRECISION_HALVES, PRECISION_WHOLE]
        ),
        vol.Optional(CONF_UNIQUE_ID): cv.string,
        vol.Optional(CONF_WATER_SENSOR): cv.entity_id,
        vol.Optional(CONF_WATER_SETPOINT_HEAT): vol.Coerce(float),
        vol.Optional(CONF_WATER_SETPOINT_COOL): vol.Coerce(float),
        vol.Optional(CONF_WATER_SETPOINT_HEAT_ENTITY): cv.entity_id,
        vol.Optional(CONF_WATER_SETPOINT_COOL_ENTITY): cv.entity_id,
        vol.Optional(CONF_WATER_TOLERANCE, default=DEFAULT_TOLERANCE): vol.Coerce(float),
    }
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the dual mode generic thermostat platform."""

    await async_setup_reload_service(hass, DOMAIN, PLATFORMS)

    name = config.get(CONF_NAME)
    heater_entity_id = config.get(CONF_HEATER)
    cooler_entity_id = config.get(CONF_COOLER)
    sensor_entity_id = config.get(CONF_SENSOR)
    fan_entity_id = config.get(CONF_FAN)
    fan_behavior = config.get(CONF_FAN_BEHAVIOR)
    dryer_entity_id = config.get(CONF_DRYER)
    dryer_behavior = config.get(CONF_DRYER_BEHAVIOR)
    reverse_cycle = config.get(CONF_REVERSE_CYCLE)
    min_temp = config.get(CONF_MIN_TEMP)
    max_temp = config.get(CONF_MAX_TEMP)
    target_temp = config.get(CONF_TARGET_TEMP)
    target_temp_high = config.get(CONF_TARGET_TEMP_HIGH)
    target_temp_low = config.get(CONF_TARGET_TEMP_LOW)
    min_cycle_duration = config.get(CONF_MIN_DUR)
    cold_tolerance = config.get(CONF_COLD_TOLERANCE)
    hot_tolerance = config.get(CONF_HOT_TOLERANCE)
    keep_alive = config.get(CONF_KEEP_ALIVE)
    initial_hvac_mode = config.get(CONF_INITIAL_HVAC_MODE)
    away_temp = config.get(CONF_AWAY_TEMP)
    away_temp_heater = config.get(CONF_AWAY_TEMP_HEATER)
    away_temp_cooler = config.get(CONF_AWAY_TEMP_COOLER)
    precision = config.get(CONF_PRECISION)
    target_temperature_step = config.get(CONF_TEMP_STEP)
    enable_heat_cool = config.get(CONF_ENABLE_HEAT_COOL)
    unit = hass.config.units.temperature_unit
    unique_id = config.get(CONF_UNIQUE_ID)
    humidity_sensor_entity_id = config.get(CONF_HUMIDITY_SENSOR)
    consent_entity_id = config.get(CONF_CONSENT_ENTITY)
    tamper_entity_id = config.get(CONF_TAMPER_ENTITY)
    command_climate_entity_id = config.get(CONF_COMMAND_CLIMATE)
    min_heat_temp = config.get(CONF_MIN_HEAT_TEMP)
    max_heat_temp = config.get(CONF_MAX_HEAT_TEMP)
    min_cool_temp = config.get(CONF_MIN_COOL_TEMP)
    max_cool_temp = config.get(CONF_MAX_COOL_TEMP)
    water_sensor_entity_id = config.get(CONF_WATER_SENSOR)
    water_setpoint_heat = config.get(CONF_WATER_SETPOINT_HEAT)
    water_setpoint_cool = config.get(CONF_WATER_SETPOINT_COOL)
    water_setpoint_heat_entity_id = config.get(CONF_WATER_SETPOINT_HEAT_ENTITY)
    water_setpoint_cool_entity_id = config.get(CONF_WATER_SETPOINT_COOL_ENTITY)
    water_tolerance = config.get(CONF_WATER_TOLERANCE)

    async_add_entities(
        [
            DualModeGenericThermostat(
                name,
                heater_entity_id,
                cooler_entity_id,
                sensor_entity_id,
                fan_entity_id,
                fan_behavior,
                dryer_entity_id,
                dryer_behavior,
                reverse_cycle,
                min_temp,
                max_temp,
                target_temp,
                target_temp_high,
                target_temp_low,
                min_cycle_duration,
                cold_tolerance,
                hot_tolerance,
                keep_alive,
                initial_hvac_mode,
                away_temp,
                away_temp_heater,
                away_temp_cooler,
                precision,
                target_temperature_step,
                enable_heat_cool,
                unit,
                unique_id,
                humidity_sensor_entity_id,
                consent_entity_id,
                water_sensor_entity_id,
                water_setpoint_heat,
                water_setpoint_cool,
                water_setpoint_heat_entity_id,
                water_setpoint_cool_entity_id,
                water_tolerance,
                tamper_entity_id,
                command_climate_entity_id,
                min_heat_temp,
                max_heat_temp,
                min_cool_temp,
                max_cool_temp,
            )
        ]
    )


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the dual mode generic thermostat from a config entry (UI-based)."""
    # Merge data and options — options take priority for fields that can be changed
    config = {**config_entry.data, **config_entry.options}

    unit = hass.config.units.temperature_unit

    # Parse duration fields from dict format (DurationSelector returns {"hours":0,"minutes":5,"seconds":0})
    def parse_duration(value):
        """Convert duration dict or timedelta to timedelta, or None."""
        if value is None:
            return None
        if isinstance(value, dict):
            import datetime
            return datetime.timedelta(
                hours=value.get("hours", 0),
                minutes=value.get("minutes", 0),
                seconds=value.get("seconds", 0),
            )
        return value

    # Parse precision from string to float
    def parse_precision(value):
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    min_cycle_duration = parse_duration(config.get("min_cycle_duration"))
    keep_alive = parse_duration(config.get("keep_alive"))

    async_add_entities(
        [
            DualModeGenericThermostat(
                config.get("name", "Generic Thermostat"),
                config.get("heater"),
                config.get("cooler"),
                config.get("target_sensor"),
                config.get("fan"),
                config.get("fan_behavior", "neutral"),
                config.get("dryer"),
                config.get("dryer_behavior", "neutral"),
                config.get("reverse_cycle", []),
                config.get("min_temp"),
                config.get("max_temp"),
                config.get("target_temp"),
                config.get("target_temp_high"),
                config.get("target_temp_low"),
                min_cycle_duration,
                config.get("cold_tolerance", 0.3),
                config.get("hot_tolerance", 0.3),
                keep_alive,
                config.get("initial_hvac_mode"),
                config.get("away_temp"),
                config.get("away_temp_heater"),
                config.get("away_temp_cooler"),
                parse_precision(config.get("precision")),
                parse_precision(config.get("target_temp_step")),
                config.get("enable_heat_cool", False),
                unit,
                config.get("unique_id"),
                config.get("target_humidity_sensor"),
                config.get("consent_entity"),
                config.get("water_sensor"),
                config.get("water_setpoint_heat"),
                config.get("water_setpoint_cool"),
                config.get("water_setpoint_heat_entity"),
                config.get("water_setpoint_cool_entity"),
                config.get("water_tolerance", 0.3),
                config.get("tamper_entity"),
                config.get("command_climate"),
                config.get("min_heat_temp"),
                config.get("max_heat_temp"),
                config.get("min_cool_temp"),
                config.get("max_cool_temp"),
            )
        ]
    )


class DualModeGenericThermostat(ClimateEntity, RestoreEntity):
    """Representation of a Generic Thermostat device."""

    def __init__(
            self,
            name,
            heater_entity_id,
            cooler_entity_id,
            sensor_entity_id,
            fan_entity_id,
            fan_behavior,
            dryer_entity_id,
            dryer_behavior,
            reverse_cycle,
            min_temp,
            max_temp,
            target_temp,
            target_temp_high,
            target_temp_low,
            min_cycle_duration,
            cold_tolerance,
            hot_tolerance,
            keep_alive,
            initial_hvac_mode,
            away_temp,
            away_temp_heater,
            away_temp_cooler,
            precision,
            target_temperature_step,
            enable_heat_cool,
            unit,
            unique_id,
            humidity_sensor_entity_id,
            consent_entity_id,
            water_sensor_entity_id=None,
            water_setpoint_heat=None,
            water_setpoint_cool=None,
            water_setpoint_heat_entity_id=None,
            water_setpoint_cool_entity_id=None,
            water_tolerance=DEFAULT_TOLERANCE,
            tamper_entity_id=None,
            command_climate_entity_id=None,
            min_heat_temp=None,
            max_heat_temp=None,
            min_cool_temp=None,
            max_cool_temp=None,
    ):
        """Initialize the thermostat."""
        self._name = name
        self.heater_entity_id = heater_entity_id
        self.cooler_entity_id = cooler_entity_id
        self.sensor_entity_id = sensor_entity_id
        self.humidity_sensor_entity_id = humidity_sensor_entity_id
        self.fan_entity_id = fan_entity_id
        self.fan_behavior = fan_behavior
        self.dryer_entity_id = dryer_entity_id
        self.dryer_behavior = dryer_behavior
        self.consent_entity_id = consent_entity_id
        # When no consent entity is configured, consent is always granted
        self._consent_granted = consent_entity_id is None

        # Tamper entity (inverse consent)
        # When the tamper entity is ON, the thermostat is forced inactive (all devices off),
        # while retaining the previously selected HVAC mode. Mirrors consent_entity but inverted.
        # When no tamper entity is configured, tamper is never active.
        self.tamper_entity_id = tamper_entity_id
        self._tamper_active = False

        # Physical command-panel climate device (e.g. Sonoff TP-WGZBA)
        # The device's relay is not wired to anything; it is used purely as an input:
        #   - its system_mode (off / non-off) drives the dual_mode on/off
        #   - its setpoint is clamped into the heat/cool limits and applied as the target temp
        # Actuation stays with heater/cooler switches. running_state is ignored.
        self.command_climate_entity_id = command_climate_entity_id
        # On/off of the command panel acts as an additional consent (does not change mode).
        # Granted by default (and when no command device is configured).
        self._command_climate_granted = True
        self._min_heat_temp = min_heat_temp
        self._max_heat_temp = max_heat_temp
        self._min_cool_temp = min_cool_temp
        self._max_cool_temp = max_cool_temp

        # Water temperature guard
        # water_sensor: optional sensor that reads the water supply temperature
        # water_setpoint_heat / water_setpoint_heat_entity: threshold for heating mode
        #   heating allowed when water_temp >= setpoint_heat (water is hot enough)
        # water_setpoint_cool / water_setpoint_cool_entity: threshold for cooling mode
        #   cooling allowed when water_temp <= setpoint_cool (water is cold enough)
        # If no water sensor is configured, the guard is always satisfied.
        self.water_sensor_entity_id = water_sensor_entity_id
        self.water_setpoint_heat_entity_id = water_setpoint_heat_entity_id
        self.water_setpoint_cool_entity_id = water_setpoint_cool_entity_id
        self._water_setpoint_heat_fixed = water_setpoint_heat    # fixed YAML value for heating (e.g. 30)
        self._water_setpoint_cool_fixed = water_setpoint_cool    # fixed YAML value for cooling (e.g. 15)
        self._water_setpoint_heat_entity_value = None            # live value from heating setpoint entity
        self._water_setpoint_cool_entity_value = None            # live value from cooling setpoint entity
        self._water_tolerance = water_tolerance
        self._cur_water_temp = None                              # current water temperature

        # Tell Home Assistant that this integration is migrated
        self._enable_turn_on_off_backwards_compatibility = False

        # This part allows previous users of the integration to update seamlessly #
        if True in reverse_cycle:
            self.reverse_cycle = [REVERSE_CYCLE_IS_HEATER, REVERSE_CYCLE_IS_COOLER]
            _LOGGER.warning(
                "Detected legacy config for 'reverse_cycle' | "
                "Please use this in future: "
                "reverse_cycle: heater, cooler"
            )
        elif False in reverse_cycle:
            self.reverse_cycle = []
            _LOGGER.warning(
                "Detected legacy config for 'reverse_cycle' | "
                "Please leave it empty in future"
            )
        else:
            self.reverse_cycle = reverse_cycle
        # This part allows previous users of the integration to update seamlessly #

        self.min_cycle_duration = min_cycle_duration
        self._cold_tolerance = cold_tolerance
        self._hot_tolerance = hot_tolerance
        self._keep_alive = keep_alive
        self._hvac_mode = initial_hvac_mode
        self._initial_hvac_mode = initial_hvac_mode
        self.startup_hvac_mode = initial_hvac_mode
        self._saved_target_temp = target_temp or away_temp or (away_temp_heater and away_temp_cooler)
        self._temp_precision = precision
        self._temp_target_temperature_step = target_temperature_step

        # This part of the code checks whether both cooler and heater are defined and deactivates heat_cool
        # mode if necessary.
        self._enable_heat_cool = self.cooler_entity_id and self.heater_entity_id and enable_heat_cool

        if self._enable_heat_cool:
            self._support_flags = SUPPORT_FLAGS | SUPPORT_TARGET_TEMPERATURE_RANGE
        else:
            self._support_flags = SUPPORT_FLAGS

        # This list contains all supported HVAC_MODES
        self._hvac_list = [HVAC_MODE_COOL, HVAC_MODE_HEAT,
                           HVAC_MODE_DRY, HVAC_MODE_FAN_ONLY,
                           HVAC_MODE_OFF, HVAC_MODE_HEAT_COOL]

        # Removes unsupported modes based on whats available from the config
        if self.cooler_entity_id is None:
            self._hvac_list.remove(HVAC_MODE_COOL)
        if self.heater_entity_id is None:
            self._hvac_list.remove(HVAC_MODE_HEAT)
        if self.fan_entity_id is None:
            self._hvac_list.remove(HVAC_MODE_FAN_ONLY)
        if self.dryer_entity_id is None:
            self._hvac_list.remove(HVAC_MODE_DRY)
        if not self._enable_heat_cool:
            self._hvac_list.remove(HVAC_MODE_HEAT_COOL)

        self._active = False
        self._cur_temp = None
        self._cur_humidity = None
        self._temp_lock = asyncio.Lock()
        self._min_temp = min_temp
        self._max_temp = max_temp
        self._target_temp_high = target_temp_high
        self._target_temp_low = target_temp_low
        self._target_temp = target_temp
        self._unit = unit
        self._unique_id = unique_id
        if away_temp or (away_temp_heater and away_temp_cooler):
            self._support_flags = self._support_flags | SUPPORT_PRESET_MODE
        self._away_temp = away_temp
        self._away_temp_heater = away_temp_heater
        self._away_temp_cooler = away_temp_cooler
        self._is_away = False

    def register_event_listener(self, entity_id: str, func: Callable[[Event[EventStateChangedData]], Any]):
        """Adds a listener with a Callable if the entity is defined"""
        if entity_id:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, entity_id, func)
            )

    async def async_added_to_hass(self):
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        # Sensors
        self.register_event_listener(self.sensor_entity_id, self._async_sensor_changed)
        self.register_event_listener(self.humidity_sensor_entity_id, self._async_humidity_sensor_changed)

        # Switches
        self.register_event_listener(self.heater_entity_id, self._async_switch_changed)
        self.register_event_listener(self.cooler_entity_id, self._async_switch_changed)
        self.register_event_listener(self.fan_entity_id, self._async_switch_changed)
        self.register_event_listener(self.dryer_entity_id, self._async_switch_changed)
        self.register_event_listener(self.consent_entity_id, self._async_consent_entity_changed)

        # Water temperature guard listeners
        self.register_event_listener(self.water_sensor_entity_id, self._async_water_sensor_changed)
        self.register_event_listener(self.water_setpoint_heat_entity_id, self._async_water_setpoint_entity_changed)
        self.register_event_listener(self.water_setpoint_cool_entity_id, self._async_water_setpoint_entity_changed)

        # Tamper entity listener (inverse consent)
        self.register_event_listener(self.tamper_entity_id, self._async_tamper_entity_changed)

        # Command-panel climate device listener
        self.register_event_listener(self.command_climate_entity_id, self._async_command_climate_changed)

        if self.consent_entity_id:
            consent_state = self.hass.states.get(self.consent_entity_id)
            self._consent_granted = self._extract_consent_from_state(consent_state)
            if not self._consent_granted:
                await self._async_turn_off_all_devices()

        if self.tamper_entity_id:
            tamper_state = self.hass.states.get(self.tamper_entity_id)
            self._tamper_active = self._extract_tamper_from_state(tamper_state)
            if self._tamper_active:
                await self._async_turn_off_all_devices()

        if self.command_climate_entity_id:
            command_state = self.hass.states.get(self.command_climate_entity_id)
            self._command_climate_granted = self._extract_command_grant_from_state(command_state)
            if not self._command_climate_granted:
                await self._async_turn_off_all_devices()
            # If no explicit target_sensor is configured, seed the current temperature
            # from the command climate's own reading.
            if self.sensor_entity_id is None and command_state and command_state.state not in (
                    STATE_UNAVAILABLE,
                    STATE_UNKNOWN,
            ):
                self._async_update_temp_from_command_climate(command_state)

        if self._keep_alive:
            self.async_on_remove(
                async_track_time_interval(
                    self.hass, self._async_control_heating, self._keep_alive
                )
            )

        def fallback_to_default_target_temp():
            if self._hvac_mode == HVAC_MODE_COOL:
                self._target_temp = self.max_temp
            elif self._hvac_mode == HVAC_MODE_HEAT:
                self._target_temp = self.min_temp
            elif self._hvac_mode == HVAC_MODE_FAN_ONLY and self.fan_behavior == FAN_MODE_COOL:
                self._target_temp = self.max_temp
            elif self._hvac_mode == HVAC_MODE_FAN_ONLY:
                self._target_temp = self.min_temp
            elif self._hvac_mode == HVAC_MODE_DRY and self.fan_behavior == FAN_MODE_COOL:
                self._target_temp = self.max_temp
            elif self._hvac_mode == HVAC_MODE_DRY:
                self._target_temp = self.min_temp
            else:
                self._target_temp = self.min_temp

        def fallback_to_default_target_temp_high_low():
            self._target_temp_low = self.min_temp
            self._target_temp_high = self.max_temp

        # We want to restore the old state if there is one
        # otherwise we fall back to default values
        old_state = await self.async_get_last_state()
        if old_state is None:
            # No previous state, try and restore defaults
            if self._target_temp is None:
                fallback_to_default_target_temp()
            if self._target_temp_low is None or self._target_temp_high is None:
                fallback_to_default_target_temp_high_low()
            _LOGGER.warning(
                "No previously saved temperature, setting to %s", self._target_temp
            )
            self._hvac_mode = HVAC_MODE_OFF
        else:
            # Override current hvac mode with old state
            self._hvac_mode = old_state.state
            # Check if target_temp is not set and we are not in HEAT_COOL mode
            if self._hvac_mode != HVAC_MODE_HEAT_COOL:
                # If we have a previously saved temperature
                if old_state.attributes.get(ATTR_TEMPERATURE) is None:
                    fallback_to_default_target_temp()
                    _LOGGER.warning(
                        "Undefined target temperature," "falling back to %s",
                        self._target_temp,
                    )
                else:
                    self._target_temp = float(old_state.attributes[ATTR_TEMPERATURE])
            else:
                # If we have a previously saved min and max temperatures
                if (old_state.attributes.get(ATTR_TARGET_TEMP_LOW) is None or
                        old_state.attributes.get(ATTR_TARGET_TEMP_HIGH) is None):
                    fallback_to_default_target_temp_high_low()
                    _LOGGER.warning(
                        "Undefined target temperature range," "falling back to %s to %s",
                        self._min_temp,
                        self._max_temp,
                    )
                else:
                    self._target_temp_low = float(old_state.attributes[ATTR_TARGET_TEMP_LOW])
                    self._target_temp_high = float(old_state.attributes[ATTR_TARGET_TEMP_HIGH])

            if old_state.attributes.get(ATTR_PRESET_MODE) == PRESET_AWAY:
                self._is_away = True

        # We only want to update the sensors again if the state has already been restored
        @callback
        def _async_startup(event=None):
            """Init on startup."""
            if self.sensor_entity_id:
                temp_sensor_state = self.hass.states.get(self.sensor_entity_id)
                if temp_sensor_state and temp_sensor_state.state not in (
                        STATE_UNAVAILABLE,
                        STATE_UNKNOWN,
                ):
                    self._async_update_temp(temp_sensor_state)

            if self.humidity_sensor_entity_id:
                humidity_sensor_state = self.hass.states.get(self.humidity_sensor_entity_id)
                if humidity_sensor_state and humidity_sensor_state.state not in (
                        STATE_UNAVAILABLE,
                        STATE_UNKNOWN,
                ):
                    self._async_update_humidity(humidity_sensor_state)

            if self.water_sensor_entity_id:
                water_sensor_state = self.hass.states.get(self.water_sensor_entity_id)
                if water_sensor_state and water_sensor_state.state not in (
                        STATE_UNAVAILABLE,
                        STATE_UNKNOWN,
                ):
                    self._async_update_water_temp(water_sensor_state)

            if self.water_setpoint_heat_entity_id:
                water_sp_heat_state = self.hass.states.get(self.water_setpoint_heat_entity_id)
                if water_sp_heat_state and water_sp_heat_state.state not in (
                        STATE_UNAVAILABLE,
                        STATE_UNKNOWN,
                ):
                    self._async_update_water_setpoint_heat(water_sp_heat_state)

            if self.water_setpoint_cool_entity_id:
                water_sp_cool_state = self.hass.states.get(self.water_setpoint_cool_entity_id)
                if water_sp_cool_state and water_sp_cool_state.state not in (
                        STATE_UNAVAILABLE,
                        STATE_UNKNOWN,
                ):
                    self._async_update_water_setpoint_cool(water_sp_cool_state)

        if self.hass.state == CoreState.running:
            _async_startup()
        else:
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, _async_startup)

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def name(self):
        """Return the name of the thermostat."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique id of this thermostat."""
        return self._unique_id

    @property
    def precision(self):
        """Return the precision of the system."""
        if self._temp_precision is not None:
            return self._temp_precision
        return super().precision

    @property
    def target_temperature_step(self):
        """Return the supported step of target temperature."""
        if self._temp_target_temperature_step is not None:
            return self._temp_target_temperature_step
        # if a target_temperature_step is not defined, fallback to equal the precision
        return self.precision

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def current_temperature(self):
        """Return the sensor temperature."""
        return self._cur_temp

    @property
    def current_humidity(self):
        """Return the sensor temperature."""
        return self._cur_humidity

    @property
    def hvac_mode(self):
        """Return current operation."""
        return self._hvac_mode

    @property
    def hvac_action(self):
        """Return the current running hvac operation if supported.

        Need to be one of CURRENT_HVAC_*.
        """
        if self._hvac_mode == HVAC_MODE_OFF:
            return CURRENT_HVAC_OFF
        if not self._consent_granted:
            return CURRENT_HVAC_IDLE
        if self._tamper_active:
            return CURRENT_HVAC_IDLE
        if not self._command_climate_granted:
            return CURRENT_HVAC_IDLE
        if self._is_water_guard_blocked:
            return CURRENT_HVAC_IDLE
        if not self._is_device_active:
            return CURRENT_HVAC_IDLE
        elif self._hvac_mode == HVAC_MODE_COOL:
            return CURRENT_HVAC_COOL
        elif self._hvac_mode == HVAC_MODE_HEAT:
            return CURRENT_HVAC_HEAT
        elif self._hvac_mode == HVAC_MODE_FAN_ONLY:
            return CURRENT_HVAC_FAN
        elif self._hvac_mode == HVAC_MODE_DRY:
            return CURRENT_HVAC_DRY
        elif self._hvac_mode == HVAC_MODE_HEAT_COOL:
            # Check if heater and cooler are the same entity (reverse cycle)
            if self.heater_entity_id == self.cooler_entity_id:
                # For reverse cycle, determine action based on current temperature
                if self._cur_temp >= self._target_temp_high + self._hot_tolerance:
                    return CURRENT_HVAC_COOL
                elif self._cur_temp <= self._target_temp_low - self._cold_tolerance:
                    return CURRENT_HVAC_HEAT
                else:
                    return CURRENT_HVAC_IDLE
            else:
                # Original logic for separate heater/cooler
                if self.hass.states.is_state(self.heater_entity_id, STATE_ON):
                    return CURRENT_HVAC_HEAT
                elif self.hass.states.is_state(self.cooler_entity_id, STATE_ON):
                    return CURRENT_HVAC_COOL
                else:
                    return CURRENT_HVAC_IDLE
        else:
            return CURRENT_HVAC_IDLE

    @property
    def target_temperature(self):
        """
        Return the temperature we try to reach.

        We return None in modes where we either need high and low target temperatures
        or when we are in fan only mode with neutral fan behavior. As in such a case the single target temperature
        is not needed and only clutters the UI.
        """
        if self._hvac_mode == HVAC_MODE_FAN_ONLY and self.fan_behavior == FAN_MODE_NEUTRAL:
            return None
        if self._hvac_mode == HVAC_MODE_DRY and self.dryer_behavior == DRYER_MODE_NEUTRAL:
            return None
        if self._hvac_mode != HVAC_MODE_HEAT_COOL:
            return self._target_temp
        else:
            return None

    @property
    def target_temperature_high(self):
        """
        Return the upper temperature we try to reach when in range mode.

        We return None in modes where we don't need high and low target temperatures.
        """
        if self._hvac_mode == HVAC_MODE_HEAT_COOL:
            return self._target_temp_high
        else:
            return None

    @property
    def target_temperature_low(self):
        """
        Return the lower temperature we try to reach when in range mode.

        We return None in modes where we don't need high and low target temperatures.
        """
        if self._hvac_mode == HVAC_MODE_HEAT_COOL:
            return self._target_temp_low
        else:
            return None

    @property
    def hvac_modes(self):
        """List of available operation modes."""
        return self._hvac_list

    @property
    def preset_mode(self):
        """Return the current preset mode, e.g., home, away, temp."""
        return PRESET_AWAY if self._is_away else PRESET_NONE

    @property
    def preset_modes(self):
        """Return a list of available preset modes or PRESET_NONE if _away_temp or (_away_temp_heater and _away_temp_cooler) are undefined."""
        return [PRESET_NONE, PRESET_AWAY] if (
                self._away_temp or (self._away_temp_heater and self._away_temp_cooler)) else PRESET_NONE

    async def async_set_hvac_mode(self, hvac_mode):
        """Set hvac mode."""

        # Save the current mode so that we can restore it later when calling turn_on
        prev_hvac_mode = self.hvac_mode
        if hvac_mode != HVAC_MODE_OFF:
            self.startup_hvac_mode = self.hvac_mode
        else:
            self.startup_hvac_mode = self._hvac_mode

        # Take action according to selected HVAC_MODE
        if hvac_mode == HVAC_MODE_HEAT:
            if self._target_temp_low is not None and self._target_temp is None:
                self._target_temp = self._target_temp_low
            self._hvac_mode = HVAC_MODE_HEAT
            if self._is_device_active:
                if REVERSE_CYCLE_IS_COOLER not in self.reverse_cycle:
                    await self._async_cooler_turn_off()
                if REVERSE_CYCLE_IS_FAN not in self.reverse_cycle:
                    await self._async_fan_turn_off()
                if REVERSE_CYCLE_IS_DRYER not in self.reverse_cycle:
                    await self._async_dryer_turn_off()
            await self._async_control_heating(force=True, previous_mode=prev_hvac_mode)
        elif hvac_mode == HVAC_MODE_COOL:
            if self._target_temp_high is not None and self._target_temp is None:
                self._target_temp = self._target_temp_high
            self._hvac_mode = HVAC_MODE_COOL
            if self._is_device_active:
                if REVERSE_CYCLE_IS_HEATER not in self.reverse_cycle:
                    await self._async_heater_turn_off()
                if REVERSE_CYCLE_IS_FAN not in self.reverse_cycle:
                    await self._async_fan_turn_off()
                if REVERSE_CYCLE_IS_DRYER not in self.reverse_cycle:
                    await self._async_dryer_turn_off()
            await self._async_control_heating(force=True, previous_mode=prev_hvac_mode)
        elif hvac_mode == HVAC_MODE_FAN_ONLY:
            self._hvac_mode = HVAC_MODE_FAN_ONLY
            if self._is_device_active:
                if REVERSE_CYCLE_IS_COOLER not in self.reverse_cycle:
                    await self._async_cooler_turn_off()
                if REVERSE_CYCLE_IS_HEATER not in self.reverse_cycle:
                    await self._async_heater_turn_off()
                if REVERSE_CYCLE_IS_DRYER not in self.reverse_cycle:
                    await self._async_dryer_turn_off()
            await self._async_control_heating(force=True, previous_mode=prev_hvac_mode)
        elif hvac_mode == HVAC_MODE_DRY:
            self._hvac_mode = HVAC_MODE_DRY
            if self._is_device_active:
                if REVERSE_CYCLE_IS_COOLER not in self.reverse_cycle:
                    await self._async_cooler_turn_off()
                if REVERSE_CYCLE_IS_HEATER not in self.reverse_cycle:
                    await self._async_heater_turn_off()
                if REVERSE_CYCLE_IS_FAN not in self.reverse_cycle:
                    await self._async_fan_turn_off()
            await self._async_control_heating(force=True, previous_mode=prev_hvac_mode)
        elif hvac_mode == HVAC_MODE_HEAT_COOL:
            if self._target_temp_low is None:
                if self._target_temp is not None:
                    self._target_temp_low = self._target_temp - 0.5
            if self._target_temp_high is None:
                if self._target_temp is not None:
                    self._target_temp_high = self._target_temp + 0.5
            self._hvac_mode = HVAC_MODE_HEAT_COOL
            if self._is_device_active:
                if REVERSE_CYCLE_IS_FAN not in self.reverse_cycle:
                    await self._async_fan_turn_off()
                if REVERSE_CYCLE_IS_DRYER not in self.reverse_cycle:
                    await self._async_dryer_turn_off()
            await self._async_control_heating(force=True, previous_mode=prev_hvac_mode)
        elif hvac_mode == HVAC_MODE_OFF:
            self._hvac_mode = HVAC_MODE_OFF
            if self._is_device_active:
                await self._async_heater_turn_off()
                await self._async_cooler_turn_off()
                await self._async_fan_turn_off()
                await self._async_dryer_turn_off()
        else:
            _LOGGER.error("Unrecognized hvac mode: %s", hvac_mode)
            return
        # Ensure we update the current operation after changing the mode
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        temp_low = kwargs.get(ATTR_TARGET_TEMP_LOW)
        temp_high = kwargs.get(ATTR_TARGET_TEMP_HIGH)
        if temperature is not None:
            if self._hvac_mode == HVAC_MODE_HEAT:
                self._target_temp_low = temperature
            elif self._hvac_mode == HVAC_MODE_COOL:
                self._target_temp_high = temperature
            elif self._target_temp_low == self._target_temp:
                self._target_temp_low = temperature
            elif self._target_temp_high == self._target_temp:
                self._target_temp_high = temperature
            self._target_temp = temperature
        if temp_low is not None:
            if self._hvac_mode == HVAC_MODE_HEAT:
                self._target_temp = temp_low
            elif self._target_temp_low == self._target_temp:
                self._target_temp = temp_low
            self._target_temp_low = temp_low
        if temp_high is not None:
            if self._hvac_mode == HVAC_MODE_COOL:
                self._target_temp = temp_high
            elif self._target_temp_high == self._target_temp:
                self._target_temp = temp_high
            self._target_temp_high = temp_high
        await self._async_control_heating(force=True)
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Turn on."""
        await self.async_set_hvac_mode(self.startup_hvac_mode)

    async def async_turn_off(self) -> None:
        """Turn off."""
        await self.async_set_hvac_mode(HVAC_MODE_OFF)

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        if self._min_temp is not None:
            return self._min_temp

        # get default temp from super class
        return super().min_temp

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        if self._max_temp is not None:
            return self._max_temp

        # Get default temp from super class
        return super().max_temp



    # async def _async_sensor_changed(self, entity_id, old_state, new_state):
    @callback
    async def _async_sensor_changed(self, event: Event[EventStateChangedData]):
        """Handle temperature changes."""
        new_state = event.data["new_state"]
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        self._async_update_temp(new_state)
        await self._async_control_heating()
        self.async_write_ha_state()

    @callback
    async def _async_humidity_sensor_changed(self, event: Event[EventStateChangedData]):
        """Handle temperature changes."""
        new_state = event.data["new_state"]
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        self._async_update_humidity(new_state)
        await self._async_control_heating()
        self.async_write_ha_state()

    @callback
    def _async_switch_changed(self, event: Event[EventStateChangedData]):
        """Handle heater switch state changes."""
        if event.data["new_state"] is None:
            return
        self.async_write_ha_state()

    @callback
    def _async_update_temp(self, state):
        """Update thermostat with latest state from sensor."""
        try:
            self._cur_temp = float(state.state)
        except ValueError as ex:
            _LOGGER.error("Unable to update from sensor: %s", ex)

    @callback
    def _async_update_humidity(self, state):
        """Update thermostat with latest state from sensor."""
        try:
            self._cur_humidity = float(state.state)
        except ValueError as ex:
            _LOGGER.error("Unable to update from sensor: %s", ex)

    def _extract_consent_from_state(self, state):
        """Return True if the consent entity grants permission."""
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return False
        return state.state == STATE_ON

    @callback
    async def _async_consent_entity_changed(self, event: Event[EventStateChangedData]):
        """Handle consent entity state changes."""
        new_state = event.data.get("new_state")
        previous = self._consent_granted
        self._consent_granted = self._extract_consent_from_state(new_state)
        if previous != self._consent_granted:
            if not self._consent_granted:
                await self._async_turn_off_all_devices()
            else:
                await self._async_control_heating(force=True)
        self.async_write_ha_state()

    # ---------------------------------------------------------------------------
    # Tamper entity — inverse consent (ON => thermostat inactive)
    # ---------------------------------------------------------------------------

    def _extract_tamper_from_state(self, state):
        """Return True if the tamper entity is active (ON)."""
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            # Unavailable/unknown tamper is treated as inactive (don't block operation)
            return False
        return state.state == STATE_ON

    @callback
    async def _async_tamper_entity_changed(self, event: Event[EventStateChangedData]):
        """Handle tamper entity state changes.

        When the tamper becomes active, turn off all devices (keeping the HVAC mode).
        When it clears, resume normal control. Mirrors consent handling but inverted.
        """
        new_state = event.data.get("new_state")
        previous = self._tamper_active
        self._tamper_active = self._extract_tamper_from_state(new_state)
        if previous != self._tamper_active:
            if self._tamper_active:
                await self._async_turn_off_all_devices()
            else:
                await self._async_control_heating(force=True)
        self.async_write_ha_state()

    # ---------------------------------------------------------------------------
    # Command-panel climate device — read-only input (system_mode + setpoint)
    # ---------------------------------------------------------------------------

    def _clamp_command_setpoint(self, value):
        """Clamp a setpoint read from the command climate into the configured limits.

        Uses heat limits when the dual_mode is in HEAT, cool limits when in COOL.
        Falls back to the global min/max_temp when the mode-specific limits are unset.
        """
        if value is None:
            return None
        if self._hvac_mode == HVAC_MODE_HEAT:
            low = self._min_heat_temp if self._min_heat_temp is not None else self._min_temp
            high = self._max_heat_temp if self._max_heat_temp is not None else self._max_temp
        elif self._hvac_mode == HVAC_MODE_COOL:
            low = self._min_cool_temp if self._min_cool_temp is not None else self._min_temp
            high = self._max_cool_temp if self._max_cool_temp is not None else self._max_temp
        else:
            low = self._min_temp
            high = self._max_temp
        if low is not None and value < low:
            return low
        if high is not None and value > high:
            return high
        return value

    @callback
    def _async_update_temp_from_command_climate(self, state):
        """Update the current temperature from the command climate's own reading.

        Reads the climate entity's `current_temperature` attribute (e.g. the device's
        local_temperature). Used only when no explicit target_sensor is configured.
        """
        current = state.attributes.get("current_temperature")
        if current is None:
            return
        try:
            self._cur_temp = float(current)
        except (ValueError, TypeError) as ex:
            _LOGGER.error("Unable to read temperature from command climate: %s", ex)

    def _extract_command_grant_from_state(self, state):
        """Return True if the command climate grants operation (system_mode != off).

        Unavailable/unknown is treated as "granted" so the thermostat keeps working
        from the UI when the physical panel is offline.
        """
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return True
        return state.state != HVAC_MODE_OFF

    @callback
    async def _async_command_climate_changed(self, event: Event[EventStateChangedData]):
        """Handle changes on the physical command-panel climate device.

        The device acts as a pure input, treated as an additional consent (like
        consent_entity) rather than a mode controller:
          - system_mode off      -> command grant OFF -> thermostat goes inactive
                                     (devices off), WITHOUT changing the dual_mode HVAC mode
          - system_mode non-off  -> command grant ON  -> normal control resumes
          - setpoint             -> clamped into heat/cool limits and applied as target
        The device is ignored when unavailable/unknown (thermostat keeps working via UI).
        running_state is ignored (the device relay is not wired to anything).
        """
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            # Ignore unavailable device — keep last known state and keep working via UI
            return

        # 1) On/off acts as consent — never touches the dual_mode HVAC mode
        previous = self._command_climate_granted
        self._command_climate_granted = self._extract_command_grant_from_state(new_state)
        if previous != self._command_climate_granted and not self._command_climate_granted:
            if self._is_device_active:
                await self._async_turn_off_all_devices()

        # 1b) Use the device's own temperature as the current temperature,
        # but ONLY when no explicit target_sensor is configured (target_sensor wins,
        # so the user can e.g. average it with another sensor).
        if self.sensor_entity_id is None:
            self._async_update_temp_from_command_climate(new_state)

        # 2) Sync the setpoint from the device, clamped into the configured limits
        device_setpoint = new_state.attributes.get(ATTR_TEMPERATURE)
        if device_setpoint is not None and self._hvac_mode in (HVAC_MODE_HEAT, HVAC_MODE_COOL):
            try:
                clamped = self._clamp_command_setpoint(float(device_setpoint))
            except (ValueError, TypeError):
                clamped = None
            if clamped is not None and clamped != self._target_temp:
                self._target_temp = clamped

        # Re-run control (handles both resume-on-grant and setpoint change)
        await self._async_control_heating(force=True)
        self.async_write_ha_state()

    # ---------------------------------------------------------------------------
    # Water temperature guard — callbacks, helpers and property
    # ---------------------------------------------------------------------------

    @callback
    async def _async_water_sensor_changed(self, event: Event[EventStateChangedData]):
        """Handle water supply temperature sensor changes."""
        new_state = event.data["new_state"]
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        self._async_update_water_temp(new_state)
        await self._async_control_heating()
        self.async_write_ha_state()

    @callback
    async def _async_water_setpoint_entity_changed(self, event: Event[EventStateChangedData]):
        """Handle dynamic water setpoint entity changes (heat or cool)."""
        new_state = event.data["new_state"]
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return
        entity_id = event.data.get("entity_id")
        if entity_id == self.water_setpoint_heat_entity_id:
            self._async_update_water_setpoint_heat(new_state)
        elif entity_id == self.water_setpoint_cool_entity_id:
            self._async_update_water_setpoint_cool(new_state)
        await self._async_control_heating()
        self.async_write_ha_state()

    @callback
    def _async_update_water_temp(self, state):
        """Update cached water temperature from sensor state."""
        try:
            self._cur_water_temp = float(state.state)
        except ValueError as ex:
            _LOGGER.error("Unable to update water temperature from sensor: %s", ex)

    @callback
    def _async_update_water_setpoint_heat(self, state):
        """Update cached heating water setpoint from entity state."""
        try:
            self._water_setpoint_heat_entity_value = float(state.state)
        except ValueError as ex:
            _LOGGER.error("Unable to update water heating setpoint from entity: %s", ex)

    @callback
    def _async_update_water_setpoint_cool(self, state):
        """Update cached cooling water setpoint from entity state."""
        try:
            self._water_setpoint_cool_entity_value = float(state.state)
        except ValueError as ex:
            _LOGGER.error("Unable to update water cooling setpoint from entity: %s", ex)

    @property
    def _effective_water_setpoint_heat(self):
        """Return the active water setpoint for heating.

        Entity value takes priority over fixed YAML value.
        Returns None if neither is configured.
        """
        if self._water_setpoint_heat_entity_value is not None:
            return self._water_setpoint_heat_entity_value
        return self._water_setpoint_heat_fixed

    @property
    def _effective_water_setpoint_cool(self):
        """Return the active water setpoint for cooling.

        Entity value takes priority over fixed YAML value.
        Returns None if neither is configured.
        """
        if self._water_setpoint_cool_entity_value is not None:
            return self._water_setpoint_cool_entity_value
        return self._water_setpoint_cool_fixed

    def _is_water_guard_satisfied_for_heat(self):
        """Return True if water is hot enough to allow heating.

        Condition: cur_water_temp >= setpoint_heat - tolerance
        """
        if self.water_sensor_entity_id is None:
            return True
        setpoint = self._effective_water_setpoint_heat
        if setpoint is None or self._cur_water_temp is None:
            # Guard not fully configured or sensor unavailable — allow operation
            return True
        return self._cur_water_temp >= setpoint - self._water_tolerance

    def _is_water_guard_satisfied_for_cool(self):
        """Return True if water is cold enough to allow cooling.

        Condition: cur_water_temp <= setpoint_cool + tolerance
        """
        if self.water_sensor_entity_id is None:
            return True
        setpoint = self._effective_water_setpoint_cool
        if setpoint is None or self._cur_water_temp is None:
            return True
        return self._cur_water_temp <= setpoint + self._water_tolerance

    def _is_water_guard_satisfied(self, for_heat: bool) -> bool:
        """Return True if the water guard allows the requested operation."""
        if for_heat:
            return self._is_water_guard_satisfied_for_heat()
        return self._is_water_guard_satisfied_for_cool()

    async def _async_control_heating(self, time=None, force=False, previous_mode: HVACMode=None):
        """Check if we need to turn heating on or off."""
        async with self._temp_lock:
            if not self._active and self._cur_temp is not None:
                if self._target_temp is not None or None not in (self._target_temp_high, self._target_temp_low):
                    self._active = True
                    _LOGGER.info(
                        "Obtained current and target temperature(s). "
                        "Generic Multi-mode thermostat active. Current: %s, Target: %s, Low: %s, High: %s",
                        self._cur_temp,
                        self._target_temp,
                        self._target_temp_low,
                        self._target_temp_high
                    )

            if not self._active or self._hvac_mode == HVAC_MODE_OFF:
                return

            if not self._consent_granted:
                if self._is_device_active:
                    await self._async_turn_off_all_devices()
                return

            # Tamper guard — when active, force inactive (mirror of consent but inverted)
            if self._tamper_active:
                if self._is_device_active:
                    await self._async_turn_off_all_devices()
                return

            # Command panel consent — device system_mode off forces inactive (mode unchanged)
            if not self._command_climate_granted:
                if self._is_device_active:
                    await self._async_turn_off_all_devices()
                return

            # Water temperature guard check
            # In HEAT_COOL mode the guard is evaluated per-device in the main logic below.
            # In single-mode (HEAT / COOL / FAN / DRY) we check here and block entirely if unsatisfied.
            if self.water_sensor_entity_id and self._hvac_mode not in (HVAC_MODE_HEAT_COOL, HVAC_MODE_OFF):
                # Determine whether the current mode acts as heating or cooling for guard purposes
                is_heat_action = (
                    self._hvac_mode == HVAC_MODE_HEAT or
                    (self._hvac_mode == HVAC_MODE_FAN_ONLY and self.fan_behavior == FAN_MODE_HEAT) or
                    (self._hvac_mode == HVAC_MODE_DRY and self.dryer_behavior == DRYER_MODE_HEAT)
                )
                is_cool_action = (
                    self._hvac_mode == HVAC_MODE_COOL or
                    (self._hvac_mode == HVAC_MODE_FAN_ONLY and self.fan_behavior == FAN_MODE_COOL) or
                    (self._hvac_mode == HVAC_MODE_DRY and self.dryer_behavior == DRYER_MODE_COOL)
                )
                if is_heat_action and not self._is_water_guard_satisfied(for_heat=True):
                    _LOGGER.debug(
                        "Water guard blocks heating: water_temp=%s, setpoint_heat=%s",
                        self._cur_water_temp, self._effective_water_setpoint_heat
                    )
                    if self._is_device_active:
                        await self._async_turn_off_all_devices()
                    return
                if is_cool_action and not self._is_water_guard_satisfied(for_heat=False):
                    _LOGGER.debug(
                        "Water guard blocks cooling: water_temp=%s, setpoint_cool=%s",
                        self._cur_water_temp, self._effective_water_setpoint_cool
                    )
                    if self._is_device_active:
                        await self._async_turn_off_all_devices()
                    return

            # This check sets the active entity outside of the checks below to make it available for keep-alive logic
            def determine_active_entity():
                if self._hvac_mode == HVAC_MODE_COOL:
                    return self.cooler_entity_id
                if self._hvac_mode == HVAC_MODE_HEAT:
                    return self.heater_entity_id
                if self._hvac_mode == HVAC_MODE_FAN_ONLY:
                    return self.fan_entity_id
                if self._hvac_mode == HVAC_MODE_DRY:
                    return self.dryer_entity_id
                if self._hvac_mode == HVAC_MODE_HEAT_COOL:
                    if self.hass.states.is_state(self.cooler_entity_id, STATE_ON):
                        return self.cooler_entity_id
                    else:
                        return self.heater_entity_id

            # This variable is used for the long_enough condition and for the LOG Messages
            active_entity = determine_active_entity()
            if not force and time is None:
                # If the `force` argument is True, we
                # ignore `min_cycle_duration`.
                # If the `time` argument is not none, we were invoked for
                # keep-alive purposes, and `min_cycle_duration` is irrelevant.
                if self.min_cycle_duration:
                    if self._is_device_active:
                        current_state = STATE_ON
                    else:
                        current_state = HVAC_MODE_OFF
                    long_enough = condition.state(
                        self.hass,
                        active_entity,
                        current_state,
                        self.min_cycle_duration,
                    )
                    if not long_enough:
                        return

            # Check new mode against previous HVAC mode and
            if previous_mode is not None and previous_mode != self._hvac_mode:
                if previous_mode == HVAC_MODE_COOL and REVERSE_CYCLE_IS_COOLER not in self.reverse_cycle:
                    await self._async_cooler_turn_off()
                elif previous_mode == HVAC_MODE_HEAT and REVERSE_CYCLE_IS_HEATER not in self.reverse_cycle:
                    await self._async_heater_turn_off()
                elif previous_mode == HVAC_MODE_FAN_ONLY and REVERSE_CYCLE_IS_FAN not in self.reverse_cycle:
                    await self._async_fan_turn_off()
                elif previous_mode == HVAC_MODE_DRY and REVERSE_CYCLE_IS_DRYER not in self.reverse_cycle:
                    await self._async_dryer_turn_off()
                elif previous_mode == HVAC_MODE_HEAT_COOL:
                    if self._hvac_mode == HVAC_MODE_COOL and REVERSE_CYCLE_IS_HEATER not in self.reverse_cycle:
                        await self._async_heater_turn_off()
                    elif self._hvac_mode == HVAC_MODE_HEAT and REVERSE_CYCLE_IS_COOLER not in self.reverse_cycle:
                        await self._async_cooler_turn_off()

            # Thermostat is running and in HEAT_COOL mode
            if self._is_device_active and self._hvac_mode == HVAC_MODE_HEAT_COOL:  # when to turn off (or switch modes)
                is_comfortable = self._is_within_range_deactivate()
                too_cold_overshot = self._is_too_cold_activate()
                too_hot_overshot = self._is_too_hot_activate()
                if is_comfortable:
                    _LOGGER.info("Just right! Turning off heater %s", self.heater_entity_id)
                    await self._async_heater_turn_off()
                    _LOGGER.info("Just right! Turning off cooler %s", self.cooler_entity_id)
                    await self._async_cooler_turn_off()
                elif too_cold_overshot:
                    _LOGGER.info(
                        "Overshot lower bound! Turning off cooler %s and turning on heater %s",
                        self.cooler_entity_id,
                        self.heater_entity_id,
                    )
                    await self._async_cooler_turn_off()
                    if self._is_water_guard_satisfied(for_heat=True):
                        await self._async_heater_turn_on()
                    else:
                        _LOGGER.debug("Water guard blocks heater in HEAT_COOL: water_temp=%s", self._cur_water_temp)
                        await self._async_heater_turn_off()
                elif too_hot_overshot:
                    _LOGGER.info(
                        "Overshot upper bound! Turning on cooler %s and turning off heater %s",
                        self.cooler_entity_id,
                        self.heater_entity_id,
                    )
                    await self._async_heater_turn_off()
                    if self._is_water_guard_satisfied(for_heat=False):
                        await self._async_cooler_turn_on()
                    else:
                        _LOGGER.debug("Water guard blocks cooler in HEAT_COOL: water_temp=%s", self._cur_water_temp)
                        await self._async_cooler_turn_off()
                elif time is not None:
                    _LOGGER.info("Keep-alive - Turning on %s", active_entity)
                    if self.hass.states.is_state(self.heater_entity_id, STATE_ON):
                        await self._async_heater_turn_on()
                    elif self.hass.states.is_state(self.cooler_entity_id, STATE_ON):
                        await self._async_cooler_turn_on()

            # Thermostat is running and NOT in HEAT_COOL mode
            if self._is_device_active and self._hvac_mode != HVAC_MODE_HEAT_COOL:
                too_cold = self._is_too_cold_deactivate()
                too_hot = self._is_too_hot_deactivate()
                if self._hvac_mode == HVAC_MODE_COOL:
                    if too_cold:
                        _LOGGER.info("Too cold! Turning off cooler %s", self.cooler_entity_id)
                        await self._async_cooler_turn_off()
                elif self._hvac_mode == HVAC_MODE_HEAT:
                    if too_hot:
                        _LOGGER.info("Too hot! Turning off heater %s", self.heater_entity_id)
                        await self._async_heater_turn_off()
                elif self._hvac_mode == HVAC_MODE_FAN_ONLY:
                    if (
                        (too_cold and self.fan_behavior == FAN_MODE_COOL) or
                            (too_hot and self.fan_behavior == FAN_MODE_HEAT)
                    ):
                        _LOGGER.info("Turning off fan %s", self.fan_entity_id)
                        await self._async_fan_turn_off()
                elif self._hvac_mode == HVAC_MODE_DRY:
                    if (
                        (too_cold and self.dryer_behavior == DRYER_MODE_COOL) or
                            (too_hot and self.dryer_behavior == DRYER_MODE_HEAT)
                    ):
                        _LOGGER.info("Turning off dehumidifier %s", self.dryer_entity_id)
                        await self._async_dryer_turn_off()
                elif time is not None:
                # The time argument is passed only in keep-alive case
                    _LOGGER.info("Keep-alive - Turning on %s", active_entity)
                    if self._hvac_mode == HVAC_MODE_COOL:
                        await self._async_cooler_turn_on()
                    elif self._hvac_mode == HVAC_MODE_HEAT:
                        await self._async_heater_turn_on()
                    elif self._hvac_mode == HVAC_MODE_FAN_ONLY:
                        await self._async_fan_turn_on()
                    elif self._hvac_mode == HVAC_MODE_DRY:
                        await self._async_dryer_turn_on()

            # Thermostat is inactive
            if not self._is_device_active:
                too_cold = self._is_too_cold_activate()
                too_hot = self._is_too_hot_activate()
                if too_hot and self._hvac_mode in [HVAC_MODE_COOL, HVAC_MODE_HEAT_COOL]:
                    if self._is_water_guard_satisfied(for_heat=False):
                        _LOGGER.info("Turning on cooler %s", self.cooler_entity_id)
                        await self._async_cooler_turn_on()
                    else:
                        _LOGGER.debug("Water guard blocks cooler activation: water_temp=%s", self._cur_water_temp)
                elif too_cold and self._hvac_mode in [HVAC_MODE_HEAT, HVAC_MODE_HEAT_COOL]:
                    if self._is_water_guard_satisfied(for_heat=True):
                        _LOGGER.info("Turning on heater %s", self.heater_entity_id)
                        await self._async_heater_turn_on()
                    else:
                        _LOGGER.debug("Water guard blocks heater activation: water_temp=%s", self._cur_water_temp)
                elif self._hvac_mode == HVAC_MODE_FAN_ONLY:
                    if (
                        (too_hot and self.fan_behavior == FAN_MODE_COOL)
                        or (too_cold and self.fan_behavior == FAN_MODE_HEAT)
                    ):
                        _LOGGER.info("Turning on fan %s", self.fan_entity_id)
                        await self._async_fan_turn_on()
                elif self._hvac_mode == HVAC_MODE_DRY:
                    if (
                        (too_hot and self.dryer_behavior == DRYER_MODE_COOL)
                        or (too_cold and self.dryer_behavior == DRYER_MODE_HEAT)
                    ):
                        _LOGGER.info("Turning on dehumidifier %s", self.dryer_entity_id)
                        await self._async_dryer_turn_on()
                elif time is not None:
                    # The time argument is passed only in keep-alive case
                    _LOGGER.info("Keep-alive - Turning off %s", active_entity)
                    if self._hvac_mode == HVAC_MODE_COOL:
                        await self._async_cooler_turn_off()
                    elif self._hvac_mode == HVAC_MODE_HEAT:
                        await self._async_heater_turn_off()
                    elif self._hvac_mode == HVAC_MODE_FAN_ONLY:
                        await self._async_fan_turn_off()
                    elif self._hvac_mode == HVAC_MODE_DRY:
                        await self._async_dryer_turn_off()
                    elif self._hvac_mode == HVAC_MODE_HEAT_COOL:
                        if self.hass.states.is_state(self.heater_entity_id, STATE_ON):
                            await self._async_heater_turn_off()
                        elif self.hass.states.is_state(self.cooler_entity_id, STATE_ON):
                            await self._async_cooler_turn_off()

            if self.fan_behavior == FAN_MODE_NEUTRAL and self._hvac_mode == HVAC_MODE_FAN_ONLY:
                await self._async_fan_turn_on()
            if self.dryer_behavior == DRYER_MODE_NEUTRAL and self._hvac_mode == HVAC_MODE_DRY:
                await self._async_dryer_turn_on()

    @property
    def _is_device_active(self):
        """If the toggleable device is currently active."""
        devices = [] + \
                  ([self.cooler_entity_id] if self.cooler_entity_id else []) + \
                  ([self.heater_entity_id] if self.heater_entity_id else []) + \
                  ([self.fan_entity_id] if self.fan_entity_id else []) + \
                  ([self.dryer_entity_id] if self.dryer_entity_id else [])
        device_states = [self.hass.states.is_state(dev, STATE_ON) for dev in devices]
        return next((state for state in device_states if state), False)

    @property
    def _is_water_guard_blocked(self):
        """Return True if the water guard is currently blocking operation.

        This is a summary view for hvac_action and extra_state_attributes.
        In HEAT_COOL mode the guard may block one device but not the other,
        so we return True only when both relevant checks fail.
        """
        if self.water_sensor_entity_id is None:
            return False
        if self._hvac_mode == HVAC_MODE_HEAT:
            return not self._is_water_guard_satisfied(for_heat=True)
        if self._hvac_mode == HVAC_MODE_COOL:
            return not self._is_water_guard_satisfied(for_heat=False)
        if self._hvac_mode in (HVAC_MODE_FAN_ONLY, HVAC_MODE_DRY):
            is_heat_action = (
                (self._hvac_mode == HVAC_MODE_FAN_ONLY and self.fan_behavior == FAN_MODE_HEAT) or
                (self._hvac_mode == HVAC_MODE_DRY and self.dryer_behavior == DRYER_MODE_HEAT)
            )
            if is_heat_action:
                return not self._is_water_guard_satisfied(for_heat=True)
            is_cool_action = (
                (self._hvac_mode == HVAC_MODE_FAN_ONLY and self.fan_behavior == FAN_MODE_COOL) or
                (self._hvac_mode == HVAC_MODE_DRY and self.dryer_behavior == DRYER_MODE_COOL)
            )
            if is_cool_action:
                return not self._is_water_guard_satisfied(for_heat=False)
        # HEAT_COOL: blocked only if both heater and cooler are blocked
        if self._hvac_mode == HVAC_MODE_HEAT_COOL:
            return (not self._is_water_guard_satisfied(for_heat=True) and
                    not self._is_water_guard_satisfied(for_heat=False))
        return False

    @property
    def extra_state_attributes(self):
        """Return additional state attributes for the water temperature guard."""
        attrs = {}
        if self.water_sensor_entity_id:
            attrs["water_temperature"] = self._cur_water_temp
            attrs["water_setpoint_heat"] = self._effective_water_setpoint_heat
            attrs["water_setpoint_cool"] = self._effective_water_setpoint_cool
            attrs["water_guard_active"] = self._is_water_guard_blocked
        return attrs

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return self._support_flags

    # activate at the edges of the desired range
    def _is_too_cold_activate(self):
        if self._hvac_mode == HVAC_MODE_HEAT_COOL:
            return self._target_temp_low >= self._cur_temp + self._cold_tolerance
        else:
            return self._target_temp >= self._cur_temp + self._cold_tolerance

    def _is_too_hot_activate(self):
        if self._hvac_mode == HVAC_MODE_HEAT_COOL:
            return self._cur_temp >= self._target_temp_high + self._hot_tolerance
        else:
            return self._cur_temp >= self._target_temp + self._hot_tolerance

    # deactivate at the extremes of the desired range, plus/minus tolerance
    def _is_too_cold_deactivate(self):
        if self._hvac_mode == HVAC_MODE_HEAT_COOL:
            # Use the midpoint in the set range as our target temp when in range mode
            # return ((self._target_temp_low + self._target_temp_high)/2) >= self._cur_temp + self._cold_tolerance
            too_cold = self._target_temp_high >= self._cur_temp + self._cold_tolerance
            _LOGGER.info(
                "_is_too_cold_deactivate: %s| %s,%s,%s",
                too_cold, self._target_temp_high, self._cur_temp, self._cold_tolerance
            )
            return too_cold
        else:
            return self._target_temp >= self._cur_temp + self._cold_tolerance

    def _is_too_hot_deactivate(self):
        if self._hvac_mode == HVAC_MODE_HEAT_COOL:
            too_hot = self._cur_temp >= self._target_temp_low + self._hot_tolerance
            _LOGGER.info(
                "_is_too_hot_deactivate: %s| %s,%s,%s",
                too_hot, self._cur_temp, self._target_temp_low, self._hot_tolerance
            )
            return too_hot
        else:
            return self._cur_temp >= self._target_temp + self._hot_tolerance

    def _is_within_range_deactivate(self):
        return self._is_too_cold_deactivate() and self._is_too_hot_deactivate()

    async def _async_heater_turn_on(self):
        """Turn heater toggleable device on."""
        if self.heater_entity_id is not None:
            data = {ATTR_ENTITY_ID: self.heater_entity_id}
            await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_ON, data)

    async def _async_heater_turn_off(self):
        """Turn heater toggleable device off."""
        if self.heater_entity_id is not None:
            data = {ATTR_ENTITY_ID: self.heater_entity_id}
            await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_OFF, data)

    async def _async_cooler_turn_on(self):
        """Turn cooler toggleable device on."""
        if self.cooler_entity_id is not None:
            data = {ATTR_ENTITY_ID: self.cooler_entity_id}
            await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_ON, data)

    async def _async_cooler_turn_off(self):
        """Turn cooler toggleable device off."""
        if self.cooler_entity_id is not None:
            data = {ATTR_ENTITY_ID: self.cooler_entity_id}
            await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_OFF, data)

    async def _async_fan_turn_on(self):
        """Turn cooler toggleable device on."""
        if self.fan_entity_id is not None:
            data = {ATTR_ENTITY_ID: self.fan_entity_id}
            await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_ON, data)

    async def _async_fan_turn_off(self):
        """Turn fan toggleable device off."""
        if self.fan_entity_id is not None:
            data = {ATTR_ENTITY_ID: self.fan_entity_id}
            await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_OFF, data)

    async def _async_dryer_turn_on(self):
        """Turn cooler toggleable device on."""
        if self.dryer_entity_id is not None:
            data = {ATTR_ENTITY_ID: self.dryer_entity_id}
            await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_ON, data)

    async def _async_dryer_turn_off(self):
        """Turn fan toggleable device off."""
        if self.dryer_entity_id is not None:
            data = {ATTR_ENTITY_ID: self.dryer_entity_id}
            await self.hass.services.async_call(HA_DOMAIN, SERVICE_TURN_OFF, data)

    async def async_set_preset_mode(self, preset_mode: str):
        """Set new preset mode."""
        if preset_mode == PRESET_AWAY and not self._is_away:
            self._is_away = True
            self._saved_target_temp = self._target_temp
            if self._hvac_mode == HVAC_MODE_COOL:
                if self._away_temp_cooler:
                    self._target_temp = self._away_temp_cooler
                else:
                    self._target_temp = self._away_temp
            elif self._hvac_mode == HVAC_MODE_HEAT:
                if self._away_temp_heater:
                    self._target_temp = self._away_temp_heater
                else:
                    self._target_temp = self._away_temp
            await self._async_control_heating(force=True)
        elif preset_mode == PRESET_NONE and self._is_away:
            self._is_away = False
            self._target_temp = self._saved_target_temp
            await self._async_control_heating(force=True)

        self.async_write_ha_state()

    async def _async_turn_off_all_devices(self):
        """Turn off all controlled devices (heater, cooler, fan, dryer)."""
        await self._async_heater_turn_off()
        await self._async_cooler_turn_off()
        await self._async_fan_turn_off()
        await self._async_dryer_turn_off()
