"""YAML schema and the normalized thermostat configuration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components.climate import PLATFORM_SCHEMA as CLIMATE_PLATFORM_SCHEMA
from homeassistant.components.climate import HVACMode
from homeassistant.const import (
    CONF_NAME,
    CONF_UNIQUE_ID,
    PRECISION_HALVES,
    PRECISION_TENTHS,
    PRECISION_WHOLE,
)
from homeassistant.helpers import config_validation as cv

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
    DEFAULT_NAME,
    DEFAULT_TOLERANCE,
    Behavior,
    Role,
)

_LOGGER = logging.getLogger(__name__)

BEHAVIORS = [behavior.value for behavior in Behavior]
PRECISIONS = [PRECISION_TENTHS, PRECISION_HALVES, PRECISION_WHOLE]

# Shared by YAML and UI-created thermostats. Every key existing YAML
# configurations use since 0.2.x stays valid.
COMMON_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_HEATER): cv.entity_id,
        vol.Optional(CONF_COOLER): cv.entity_id,
        vol.Required(CONF_SENSOR): cv.entity_id,
        vol.Optional(CONF_HUMIDITY_SENSOR): cv.entity_id,
        vol.Optional(CONF_CONSENT_ENTITY): cv.entity_id,
        vol.Optional(CONF_FAN): cv.entity_id,
        vol.Optional(CONF_FAN_BEHAVIOR, default=Behavior.NEUTRAL.value): vol.In(BEHAVIORS),
        vol.Optional(CONF_DRYER): cv.entity_id,
        vol.Optional(CONF_DRYER_BEHAVIOR, default=Behavior.NEUTRAL.value): vol.In(BEHAVIORS),
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
            [
                HVACMode.COOL,
                HVACMode.HEAT,
                HVACMode.FAN_ONLY,
                HVACMode.DRY,
                HVACMode.OFF,
                HVACMode.HEAT_COOL,
            ]
        ),
        vol.Optional(CONF_AWAY_TEMP): vol.Coerce(float),
        vol.Optional(CONF_AWAY_TEMP_HEATER): vol.Coerce(float),
        vol.Optional(CONF_AWAY_TEMP_COOLER): vol.Coerce(float),
        # The UI stores these as strings.
        vol.Optional(CONF_PRECISION): vol.All(vol.Coerce(float), vol.In(PRECISIONS)),
        vol.Optional(CONF_TEMP_STEP): vol.All(vol.Coerce(float), vol.In(PRECISIONS)),
        vol.Optional(CONF_UNIQUE_ID): cv.string,
    }
)

PLATFORM_SCHEMA = CLIMATE_PLATFORM_SCHEMA.extend(COMMON_SCHEMA.schema)


@dataclass(frozen=True, slots=True)
class PresetTemperatures:
    """Temperatures a preset applies; heat/cool fall back to ``single``."""

    single: float | None = None
    heat: float | None = None
    cool: float | None = None

    @property
    def configured(self) -> bool:
        """Return whether any temperature is set."""
        return any(value is not None for value in (self.single, self.heat, self.cool))


@dataclass(frozen=True, slots=True)
class ThermostatConfig:
    """Validated configuration with legacy spellings resolved."""

    name: str
    unique_id: str | None
    sensor: str
    humidity_sensor: str | None
    consent_entity: str | None
    devices: Mapping[Role, str]
    fan_behavior: Behavior
    dryer_behavior: Behavior
    reverse_cycle: frozenset[Role]
    heat_cool_enabled: bool
    min_temp: float | None
    max_temp: float | None
    target_temp: float | None
    target_temp_low: float | None
    target_temp_high: float | None
    cold_tolerance: float
    hot_tolerance: float
    min_cycle_duration: timedelta | None
    keep_alive: timedelta | None
    initial_hvac_mode: HVACMode | None
    away: PresetTemperatures
    precision: float | None
    target_temp_step: float | None

    @classmethod
    def from_yaml(cls, config: Mapping[str, Any]) -> ThermostatConfig:
        """Build from a config validated by PLATFORM_SCHEMA."""
        devices = {
            role: entity_id for role in Role if (entity_id := config.get(role.value)) is not None
        }
        initial = config.get(CONF_INITIAL_HVAC_MODE)
        return cls(
            name=config[CONF_NAME],
            unique_id=config.get(CONF_UNIQUE_ID),
            sensor=config[CONF_SENSOR],
            humidity_sensor=config.get(CONF_HUMIDITY_SENSOR),
            consent_entity=config.get(CONF_CONSENT_ENTITY),
            devices=devices,
            fan_behavior=Behavior(config[CONF_FAN_BEHAVIOR]),
            dryer_behavior=Behavior(config[CONF_DRYER_BEHAVIOR]),
            reverse_cycle=_parse_reverse_cycle(config[CONF_REVERSE_CYCLE]),
            # heat_cool needs both a heater and a cooler.
            heat_cool_enabled=bool(
                config[CONF_ENABLE_HEAT_COOL] and Role.HEATER in devices and Role.COOLER in devices
            ),
            min_temp=config.get(CONF_MIN_TEMP),
            max_temp=config.get(CONF_MAX_TEMP),
            target_temp=config.get(CONF_TARGET_TEMP),
            target_temp_low=config.get(CONF_TARGET_TEMP_LOW),
            target_temp_high=config.get(CONF_TARGET_TEMP_HIGH),
            cold_tolerance=config[CONF_COLD_TOLERANCE],
            hot_tolerance=config[CONF_HOT_TOLERANCE],
            min_cycle_duration=config.get(CONF_MIN_DUR),
            keep_alive=config.get(CONF_KEEP_ALIVE),
            initial_hvac_mode=HVACMode(initial) if initial is not None else None,
            away=PresetTemperatures(
                single=config.get(CONF_AWAY_TEMP),
                heat=config.get(CONF_AWAY_TEMP_HEATER),
                cool=config.get(CONF_AWAY_TEMP_COOLER),
            ),
            precision=config.get(CONF_PRECISION),
            target_temp_step=config.get(CONF_TEMP_STEP),
        )


def _parse_reverse_cycle(values: list[Any]) -> frozenset[Role]:
    """Resolve reverse_cycle, including the legacy true/false form."""
    if True in values:
        _LOGGER.warning(
            "Detected legacy config for 'reverse_cycle'. Please use this in future: "
            "reverse_cycle: heater, cooler"
        )
        return frozenset({Role.HEATER, Role.COOLER})
    if False in values:
        _LOGGER.warning(
            "Detected legacy config for 'reverse_cycle'. Please leave it empty in future"
        )
        return frozenset()
    roles = set()
    for value in values:
        try:
            roles.add(Role(str(value).strip()))
        except ValueError:
            _LOGGER.warning(
                "Ignoring unknown reverse_cycle entry %r; expected heater, cooler, fan or dryer",
                value,
            )
    return frozenset(roles)
