"""Constants for the dualmode_generic integration."""

from enum import StrEnum

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
CONF_AWAY_TEMP = "away_temp"
CONF_AWAY_TEMP_HEATER = "away_temp_heater"
CONF_AWAY_TEMP_COOLER = "away_temp_cooler"
CONF_PRECISION = "precision"
CONF_TEMP_STEP = "target_temp_step"
CONF_ENABLE_HEAT_COOL = "enable_heat_cool"


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
