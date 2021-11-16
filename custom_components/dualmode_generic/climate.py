"""
Adds support for generic thermostat units that have both heating and cooling.

Originally based on the script at this thread:
https://community.home-assistant.io/t/heat-cool-generic-thermostat/76443/2

Modified to better conform to modern Home Assistant custom_component style.
"""
import asyncio
import logging

import voluptuous as vol

from homeassistant.components.climate import PLATFORM_SCHEMA, ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_PRESET_MODE,
    ATTR_TARGET_TEMP_LOW,
    ATTR_TARGET_TEMP_HIGH,
    CURRENT_HVAC_COOL,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_FAN,
    CURRENT_HVAC_DRY,
    CURRENT_HVAC_IDLE,
    CURRENT_HVAC_OFF,
    HVAC_MODE_COOL,
    HVAC_MODE_HEAT,
    HVAC_MODE_FAN_ONLY,
    HVAC_MODE_DRY,
    HVAC_MODE_OFF,
    HVAC_MODE_HEAT_COOL,
    PRESET_AWAY,
    SUPPORT_PRESET_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_TARGET_TEMPERATURE_RANGE,
    PRESET_NONE,
)
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
from homeassistant.core import DOMAIN as HA_DOMAIN, CoreState, callback
from homeassistant.helpers import condition
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.event import (
    async_track_state_change,
    async_track_time_interval,
)
from homeassistant.helpers.reload import async_setup_reload_service
from homeassistant.helpers.restore_state import RestoreEntity

from . import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)

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
SUPPORT_FLAGS = SUPPORT_TARGET_TEMPERATURE

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
        vol.Required(CONF_SENSOR): cv.entity_id,
        vol.Optional(CONF_HUMIDITY_SENSOR): cv.entity_id,
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
        vol.Optional(CONF_UNIQUE_ID): cv.string,
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
    enable_heat_cool = config.get(CONF_ENABLE_HEAT_COOL)
    unit = hass.config.units.temperature_unit
    unique_id = config.get(CONF_UNIQUE_ID)
    humidity_sensor_entity_id = config.get(CONF_HUMIDITY_SENSOR)

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
                enable_heat_cool,
                unit,
                unique_id,
                humidity_sensor_entity_id,
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
            enable_heat_cool,
            unit,
            unique_id,
            humidity_sensor_entity_id,
    ):
        """Initialize the thermostat."""
        self._name = name
        self.heater_entity_id = heater_entity_id
        self.cooler_entity_id = cooler_entity_id
        self.sensor_entity_id = sensor_entity_id
        self.fan_entity_id = fan_entity_id
        self.fan_behavior = fan_behavior
        self.dryer_entity_id = dryer_entity_id
        self.dryer_behavior = dryer_behavior

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
        self._saved_target_temp = target_temp or away_temp or (away_temp_heater and away_temp_cooler)
        self._temp_precision = precision

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
        self.humidity_sensor_entity_id = humidity_sensor_entity_id

    async def async_added_to_hass(self):
        """Run when entity about to be added."""
        await super().async_added_to_hass()

        # Add listener
        # Temp
        self.async_on_remove(
            async_track_state_change(
                self.hass, self.sensor_entity_id, self._async_sensor_changed
            )
        )
        # Humidity
        if self.humidity_sensor_entity_id:
            self.async_on_remove(
                async_track_state_change(
                    self.hass, self.humidity_sensor_entity_id, self._async_sensor_changed
                )
            )
        # Heater
        if self.heater_entity_id:
            self.async_on_remove(
                async_track_state_change(
                    self.hass, self.heater_entity_id, self._async_switch_changed
                )
            )
        # Cooler
        if self.cooler_entity_id:
            self.async_on_remove(
                async_track_state_change(
                    self.hass, self.cooler_entity_id, self._async_switch_changed
                )
            )
        # Fan
        if self.fan_entity_id:
            self.async_on_remove(
                async_track_state_change(
                    self.hass, self.fan_entity_id, self._async_switch_changed
                )
            )
        # Dryer
        if self.dryer_entity_id:
            self.async_on_remove(
                async_track_state_change(
                    self.hass, self.dryer_entity_id, self._async_switch_changed
                )
            )

        if self._keep_alive:
            self.async_on_remove(
                async_track_time_interval(
                    self.hass, self._async_control_heating, self._keep_alive
                )
            )

        @callback
        def _async_startup():
            """Init on startup."""
            sensor_state = self.hass.states.get(self.sensor_entity_id)
            if sensor_state and sensor_state.state not in (
                    STATE_UNAVAILABLE,
                    STATE_UNKNOWN,
            ):
                self._async_update_temp(sensor_state)

            if self.humidity_sensor_entity_id:
                humidity_sensor_state = self.hass.states.get(self.humidity_sensor_entity_id)
                if humidity_sensor_state and humidity_sensor_state.state not in (
                        STATE_UNAVAILABLE,
                        STATE_UNKNOWN,
                ):
                    self._async_update_temp(humidity_sensor_state)

        if self.hass.state == CoreState.running:
            _async_startup()
        else:
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, _async_startup)

        # Check If we have an old state
        old_state = await self.async_get_last_state()
        if old_state is not None:
            # If we have no initial temperature, restore
            if self._target_temp is None:
                # If we have a previously saved temperature
                if old_state.attributes.get(ATTR_TEMPERATURE) is None:
                    if self._hvac_mode == HVAC_MODE_COOL:
                        self._target_temp = self.max_temp
                    elif self._hvac_mode == HVAC_MODE_FAN_ONLY:
                        self._target_temp = self.max_temp
                    elif self._hvac_mode == HVAC_MODE_HEAT:
                        self._target_temp = self.min_temp
                    elif self._hvac_mode == HVAC_MODE_DRY:
                        self._target_temp = self._min_temp
                    elif self._hvac_mode == HVAC_MODE_HEAT_COOL:
                        self._target_temp_high = self.max_temp
                        self._target_temp_low = self.min_temp
                    else:
                        self._target_temp = self.min_temp
                    if self._support_flags & SUPPORT_TARGET_TEMPERATURE_RANGE == SUPPORT_TARGET_TEMPERATURE_RANGE:
                        self._target_temp_high = self.max_temp
                        self._target_temp_low = self.min_temp
                    _LOGGER.warning(
                        "Undefined target temperature," "falling back to %s",
                        self._target_temp,
                    )
                else:
                    self._target_temp = float(old_state.attributes[ATTR_TEMPERATURE])
            if self._target_temp_low is None:
                if old_state.attributes.get(ATTR_TARGET_TEMP_LOW) is None:
                    self._target_temp_low = self.min_temp
                else:
                    self._target_temp_low = float(old_state.attributes[ATTR_TARGET_TEMP_LOW])
            if self._target_temp_high is None:
                if old_state.attributes.get(ATTR_TARGET_TEMP_HIGH) is None:
                    self._target_temp_high = self.max_temp
                else:
                    self._target_temp_high = float(old_state.attributes[ATTR_TARGET_TEMP_HIGH])
            if old_state.attributes.get(ATTR_PRESET_MODE) == PRESET_AWAY:
                self._is_away = True
            if not self._hvac_mode and old_state.state:
                self._hvac_mode = old_state.state

        else:
            # No previous state, try and restore defaults
            if self._target_temp is None:
                if self._hvac_mode == HVAC_MODE_COOL:
                    self._target_temp = self.max_temp
                elif self._hvac_mode == HVAC_MODE_FAN_ONLY:
                    self._target_temp = self.max_temp
                elif self._hvac_mode == HVAC_MODE_HEAT:
                    self._target_temp = self.min_temp
                elif self._hvac_mode == HVAC_MODE_DRY:
                    self._target_temp = self.min_temp
                elif self._hvac_mode == HVAC_MODE_HEAT_COOL:
                    self._target_temp_high = self.max_temp
                    self._target_temp_low = self.min_temp
                else:
                    self._target_temp = self.min_temp
            if self._target_temp_low is None:
                self._target_temp_low = self.min_temp
            if self._target_temp_high is None:
                self._target_temp_high = self.max_temp
            _LOGGER.warning(
                "No previously saved temperature, setting to %s", self._target_temp
            )

        # Set default state to off
        if not self._hvac_mode:
            self._hvac_mode = HVAC_MODE_OFF

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
        # Since this integration does not yet have a step size parameter
        # we have to re-use the precision as the step size for now.
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
        if not self._is_device_active:
            return CURRENT_HVAC_IDLE
        if self._hvac_mode == HVAC_MODE_COOL:
            return CURRENT_HVAC_COOL
        if self._hvac_mode == HVAC_MODE_HEAT:
            return CURRENT_HVAC_HEAT
        if self._hvac_mode == HVAC_MODE_FAN_ONLY:
            return CURRENT_HVAC_FAN
        if self._hvac_mode == HVAC_MODE_DRY:
            return CURRENT_HVAC_DRY
        if self._hvac_mode == HVAC_MODE_HEAT_COOL:
            if self.hass.states.is_state(self.heater_entity_id, STATE_ON):
                return CURRENT_HVAC_HEAT
            elif self.hass.states.is_state(self.cooler_entity_id, STATE_ON):
                return CURRENT_HVAC_COOL
            else:
                return CURRENT_HVAC_IDLE
        return CURRENT_HVAC_IDLE

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._target_temp

    @property
    def target_temperature_high(self):
        """Return the upper temperature we try to reach when in range mode."""
        return self._target_temp_high

    @property
    def target_temperature_low(self):
        """Return the lower temperature we try to reach when in range mode."""
        return self._target_temp_low

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
        return [PRESET_NONE, PRESET_AWAY] if (self._away_temp or (self._away_temp_heater and self._away_temp_cooler)) else PRESET_NONE

    async def async_set_hvac_mode(self, hvac_mode):
        """Set hvac mode."""
        if hvac_mode == HVAC_MODE_HEAT:
            self._hvac_mode = HVAC_MODE_HEAT
            if self._is_device_active:
                if REVERSE_CYCLE_IS_COOLER not in self.reverse_cycle:
                    await self._async_cooler_turn_off()
                if REVERSE_CYCLE_IS_FAN not in self.reverse_cycle:
                    await self._async_fan_turn_off()
                if REVERSE_CYCLE_IS_DRYER not in self.reverse_cycle:
                    await self._async_dryer_turn_off()
            await self._async_control_heating(force=True)
        elif hvac_mode == HVAC_MODE_COOL:
            self._hvac_mode = HVAC_MODE_COOL
            if self._is_device_active:
                if REVERSE_CYCLE_IS_HEATER not in self.reverse_cycle:
                    await self._async_heater_turn_off()
                if REVERSE_CYCLE_IS_FAN not in self.reverse_cycle:
                    await self._async_fan_turn_off()
                if REVERSE_CYCLE_IS_DRYER not in self.reverse_cycle:
                    await self._async_dryer_turn_off()
            await self._async_control_heating(force=True)
        elif hvac_mode == HVAC_MODE_FAN_ONLY:
            self._hvac_mode = HVAC_MODE_FAN_ONLY
            if self._is_device_active:
                if REVERSE_CYCLE_IS_COOLER not in self.reverse_cycle:
                    await self._async_cooler_turn_off()
                if REVERSE_CYCLE_IS_HEATER not in self.reverse_cycle:
                    await self._async_heater_turn_off()
                if REVERSE_CYCLE_IS_DRYER not in self.reverse_cycle:
                    await self._async_dryer_turn_off()
            await self._async_control_heating(force=True)
        elif hvac_mode == HVAC_MODE_DRY:
            self._hvac_mode = HVAC_MODE_DRY
            if self._is_device_active:
                if REVERSE_CYCLE_IS_COOLER not in self.reverse_cycle:
                    await self._async_cooler_turn_off()
                if REVERSE_CYCLE_IS_HEATER not in self.reverse_cycle:
                    await self._async_heater_turn_off()
                if REVERSE_CYCLE_IS_FAN not in self.reverse_cycle:
                    await self._async_fan_turn_off()
            await self._async_control_heating(force=True)
        elif hvac_mode == HVAC_MODE_HEAT_COOL:
            self._hvac_mode = HVAC_MODE_HEAT_COOL
            if self._is_device_active:
                if REVERSE_CYCLE_IS_FAN not in self.reverse_cycle:
                    await self._async_fan_turn_off()
                if REVERSE_CYCLE_IS_DRYER not in self.reverse_cycle:
                    await self._async_dryer_turn_off()
            await self._async_control_heating(force=True)
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
            self._target_temp = temperature
        if temp_low is not None:
            self._target_temp_low = temp_low
        if temp_high is not None:
            self._target_temp_high = temp_high
        await self._async_control_heating(force=True)
        self.async_write_ha_state()

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

    async def _async_sensor_changed(self, entity_id, old_state, new_state):
        """Handle temperature changes."""
        if new_state is None or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        self._async_update_temp(new_state)
        await self._async_control_heating()
        self.async_write_ha_state()

    @callback
    def _async_switch_changed(self, entity_id, old_state, new_state):
        """Handle heater switch state changes."""
        if new_state is None:
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

    async def _async_control_heating(self, time=None, force=False):
        """Check if we need to turn heating on or off."""
        async with self._temp_lock:
            if not self._active and None not in (self._cur_temp, self._target_temp):
                self._active = True
                _LOGGER.info(
                    "Obtained current and target temperature. "
                    "Generic Dual-mode thermostat active. %s, %s",
                    self._cur_temp,
                    self._target_temp,
                )

            if not self._active or self._hvac_mode == HVAC_MODE_OFF:
                return

            # This check sets the active entity outside of the checks below to make it available for keep-alive logic
            if self._hvac_mode == HVAC_MODE_COOL:
                active_entity = self.cooler_entity_id
            if self._hvac_mode == HVAC_MODE_HEAT:
                active_entity = self.heater_entity_id
            if self._hvac_mode == HVAC_MODE_FAN_ONLY:
                active_entity = self.fan_entity_id
            if self._hvac_mode == HVAC_MODE_DRY:
                active_entity = self.dryer_entity_id
            if self._hvac_mode == HVAC_MODE_HEAT_COOL:
                if self.hass.states.is_state(self.cooler_entity_id, STATE_ON):
                    active_entity = self.cooler_entity_id
                else:
                    active_entity = self.heater_entity_id

            # This variable is used for the long_enough condition and for the LOG Messages
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

            if self._is_device_active:  # when to turn off
                too_cold = self._is_too_cold_deactivate()
                too_hot = self._is_too_hot_deactivate()
                is_comfortable = self._is_within_range_deactivate()
                if too_cold and (self._hvac_mode == HVAC_MODE_COOL):
                    _LOGGER.info("Too cold! Turning off cooler %s", self.cooler_entity_id)
                    await self._async_cooler_turn_off()
                elif too_hot and (self._hvac_mode == HVAC_MODE_HEAT):
                    _LOGGER.info("Too hot! Turning off heater %s", self.heater_entity_id)
                    await self._async_heater_turn_off()
                elif is_comfortable and (self._hvac_mode == HVAC_MODE_HEAT_COOL):
                    _LOGGER.info("Just right! Turning off heater %s", self.heater_entity_id)
                    await self._async_heater_turn_off()
                    _LOGGER.info("Just right! Turning off cooler %s", self.cooler_entity_id)
                    await self._async_cooler_turn_off()
                elif self._hvac_mode == HVAC_MODE_FAN_ONLY:
                    if too_cold and self.fan_behavior == FAN_MODE_COOL:
                        _LOGGER.info("Turning off fan %s", self.fan_entity_id)
                        await self._async_fan_turn_off()
                    elif too_hot and self.fan_behavior == FAN_MODE_HEAT:
                        _LOGGER.info("Turning off fan %s", self.fan_entity_id)
                        await self._async_fan_turn_off()
                elif self._hvac_mode == HVAC_MODE_DRY:
                    if too_cold and self.dryer_behavior == DRYER_MODE_COOL:
                        _LOGGER.info("Turning off dehumidifier %s", self.dryer_entity_id)
                        await self._async_dryer_turn_off()
                    elif too_hot and self.dryer_behavior == DRYER_MODE_HEAT:
                        _LOGGER.info("Turning off dehumidifier %s", self.dryer_entity_id)
                        await self._async_dryer_turn_off()
                elif time is not None:
                    # The time argument is passed only in keep-alive case
                    _LOGGER.info(
                        "Keep-alive - Turning on %s", active_entity
                    )
                    if self._hvac_mode == HVAC_MODE_COOL:
                        await self._async_cooler_turn_on()
                    elif self._hvac_mode == HVAC_MODE_HEAT:
                        await self._async_heater_turn_on()
                    elif self._hvac_mode == HVAC_MODE_FAN_ONLY:
                        await self._async_fan_turn_on()
                    elif self._hvac_mode == HVAC_MODE_DRY:
                        await self._async_dryer_turn_on()
                    elif self._hvac_mode == HVAC_MODE_HEAT_COOL:
                        if self.hass.states.is_state(self.heater_entity_id, STATE_ON):
                            await self._async_heater_turn_on()
                        elif self.hass.states.is_state(self.cooler_entity_id, STATE_ON):
                            await self._async_cooler_turn_on()
            else:  # when to turn on
                too_cold = self._is_too_cold_activate()
                too_hot = self._is_too_hot_activate()
                if too_hot and (self._hvac_mode == HVAC_MODE_COOL or self._hvac_mode == HVAC_MODE_HEAT_COOL):
                    _LOGGER.info("Turning on cooler %s", self.cooler_entity_id)
                    await self._async_cooler_turn_on()
                elif too_cold and (self._hvac_mode == HVAC_MODE_HEAT or self._hvac_mode == HVAC_MODE_HEAT_COOL):
                    _LOGGER.info("Turning on heater %s", self.heater_entity_id)
                    await self._async_heater_turn_on()
                elif self._hvac_mode == HVAC_MODE_FAN_ONLY:
                    if too_hot and self.fan_behavior == FAN_MODE_COOL:
                        _LOGGER.info("Turning on fan %s", self.fan_entity_id)
                        await self._async_fan_turn_on()
                    elif too_cold and self.fan_behavior == FAN_MODE_HEAT:
                        _LOGGER.info("Turning on fan %s", self.fan_entity_id)
                        await self._async_fan_turn_on()
                elif self._hvac_mode == HVAC_MODE_DRY:
                    if too_hot and self.dryer_behavior == DRYER_MODE_COOL:
                        _LOGGER.info("Turning on dehumidifier %s", self.dryer_entity_id)
                        await self._async_dryer_turn_on()
                    elif too_cold and self.dryer_behavior == DRYER_MODE_HEAT:
                        _LOGGER.info("Turning on dehumidifier %s", self.dryer_entity_id)
                        await self._async_dryer_turn_on()
                elif time is not None:
                    # The time argument is passed only in keep-alive case
                    _LOGGER.info(
                        "Keep-alive - Turning off %s", active_entity
                    )
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
