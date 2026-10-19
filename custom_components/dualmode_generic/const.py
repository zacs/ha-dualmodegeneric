"""Constants for the dualmode_generic integration."""

from enum import StrEnum

from homeassistant.components.climate import (
    PRESET_ACTIVITY,
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_HOME,
    PRESET_SLEEP,
)
from homeassistant.const import Platform

DOMAIN = "dualmode_generic"
PLATFORMS = [Platform.CLIMATE]

DEFAULT_NAME = "Generic Thermostat"
DEFAULT_TOLERANCE = 0.3
# When heat_cool is entered with only a single target known, the range is
# derived as target +/- this offset.
DEFAULT_RANGE_OFFSET = 0.5

CONF_HEATER = "heater"
CONF_COOLER = "cooler"
CONF_FAN = "fan"
CONF_FAN_BEHAVIOR = "fan_behavior"
CONF_DRYER = "dryer"
CONF_DRYER_BEHAVIOR = "dryer_behavior"
CONF_REVERSE_CYCLE = "reverse_cycle"
CONF_SENSOR = "target_sensor"
CONF_HUMIDITY_SENSOR = "target_humidity_sensor"
CONF_CONSENT_ENTITY = "consent_entity"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"
CONF_TARGET_TEMP = "target_temp"
CONF_TARGET_TEMP_HIGH = "target_temp_high"
CONF_TARGET_TEMP_LOW = "target_temp_low"
CONF_MIN_DUR = "min_cycle_duration"
CONF_COLD_TOLERANCE = "cold_tolerance"
CONF_HOT_TOLERANCE = "hot_tolerance"
CONF_KEEP_ALIVE = "keep_alive"
CONF_INITIAL_HVAC_MODE = "initial_hvac_mode"
CONF_PRECISION = "precision"
CONF_TEMP_STEP = "target_temp_step"
CONF_ENABLE_HEAT_COOL = "enable_heat_cool"
CONF_HEATER_COLD_TOLERANCE = "heater_cold_tolerance"
CONF_HEATER_HOT_TOLERANCE = "heater_hot_tolerance"
CONF_COOLER_COLD_TOLERANCE = "cooler_cold_tolerance"
CONF_COOLER_HOT_TOLERANCE = "cooler_hot_tolerance"
CONF_MAX_DUR = "max_cycle_duration"
CONF_COOLDOWN = "cycle_cooldown"
CONF_FAN_WITH = "fan_with"
CONF_FAN_OFF_DELAY = "fan_off_delay"
CONF_TAMPER_ENTITY = "tamper_entity"
# The water guard's option names match PR #88, so its users can switch over.
CONF_WATER_SENSOR = "water_sensor"
CONF_WATER_SETPOINT_HEAT = "water_setpoint_heat"
CONF_WATER_SETPOINT_COOL = "water_setpoint_cool"
CONF_WATER_SETPOINT_HEAT_ENTITY = "water_setpoint_heat_entity"
CONF_WATER_SETPOINT_COOL_ENTITY = "water_setpoint_cool_entity"
CONF_WATER_TOLERANCE = "water_tolerance"

# Presets in display order, as in the built-in generic thermostat. Each takes
# <preset>_temp, plus <preset>_temp_heater and <preset>_temp_cooler.
PRESETS = (PRESET_AWAY, PRESET_COMFORT, PRESET_ECO, PRESET_HOME, PRESET_SLEEP, PRESET_ACTIVITY)


def preset_keys(preset: str) -> tuple[str, str, str]:
    """Return the options for a preset: its temperature, for heating, for cooling."""
    return f"{preset}_temp", f"{preset}_temp_heater", f"{preset}_temp_cooler"


class Role(StrEnum):
    """A device the thermostat controls."""

    HEATER = "heater"
    COOLER = "cooler"
    FAN = "fan"
    DRYER = "dryer"


class Behavior(StrEnum):
    """How a fan or dryer responds to temperature.

    The values are also the accepted spellings for ``fan_behavior``,
    ``dryer_behavior`` and ``reverse_cycle`` entries in YAML.
    """

    COOLER = "cooler"  # runs when too hot, like a cooler
    HEATER = "heater"  # runs when too cold, like a heater
    NEUTRAL = "neutral"  # runs whenever its mode is selected
