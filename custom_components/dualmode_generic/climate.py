"""Multi-mode generic thermostat.

Controls up to four toggleable devices (heater, cooler, fan, dryer) from one
temperature sensor. The decisions live in ``controller.py``; this module turns
them into service calls and handles Home Assistant state, timing and restore.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Self

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    PRESET_AWAY,
    PRESET_NONE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Context,
    Event,
    EventStateChangedData,
    HassJob,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.core import (
    DOMAIN as HOMEASSISTANT_DOMAIN,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.reload import async_setup_reload_service
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.helpers.start import async_at_start
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import dt as dt_util

from . import schema
from .const import DEFAULT_RANGE_OFFSET, DOMAIN, PLATFORMS, Role
from .controller import MODE_ROLES, Demand, Snapshot, closer_role, decide, role_demand
from .schema import PresetTemperatures, ThermostatConfig

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = schema.PLATFORM_SCHEMA

# Display order of modes; only modes with a configured device are offered.
HVAC_MODE_ORDER = (
    HVACMode.COOL,
    HVACMode.HEAT,
    HVACMode.DRY,
    HVACMode.FAN_ONLY,
    HVACMode.OFF,
    HVACMode.HEAT_COOL,
)
# Preference when climate.turn_on has no previous mode to go back to.
TURN_ON_FALLBACK = (
    HVACMode.HEAT_COOL,
    HVACMode.HEAT,
    HVACMode.COOL,
    HVACMode.FAN_ONLY,
    HVACMode.DRY,
)
ROLE_ACTION = {
    Role.HEATER: HVACAction.HEATING,
    Role.COOLER: HVACAction.COOLING,
    Role.FAN: HVACAction.FAN,
    Role.DRYER: HVACAction.DRYING,
}
# A command we sent counts as in flight (so it isn't repeated) for this long.
PENDING_TIMEOUT = timedelta(seconds=10)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up a thermostat from YAML."""
    await async_setup_reload_service(hass, DOMAIN, PLATFORMS)
    async_add_entities(
        [
            DualModeGenericThermostat(
                ThermostatConfig.from_yaml(config), hass.config.units.temperature_unit
            )
        ]
    )


@dataclass(slots=True)
class ThermostatExtraData(ExtraStoredData):
    """State restored across restarts that isn't visible in the attributes."""

    target_temp: float | None
    target_temp_low: float | None
    target_temp_high: float | None
    # Targets from before a preset was selected, put back when it's cleared.
    saved_targets: dict[str, float | None] | None = None
    last_active_hvac_mode: str | None = None
    # Which role last turned on an entity shared by several roles.
    owners: dict[str, str] = field(default_factory=dict)
    version: int = 1

    def as_dict(self) -> dict[str, Any]:
        """Return a dict representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self | None:
        """Build from a stored dict, or None if it isn't ours."""
        try:
            return cls(
                target_temp=data["target_temp"],
                target_temp_low=data["target_temp_low"],
                target_temp_high=data["target_temp_high"],
                saved_targets=data.get("saved_targets"),
                last_active_hvac_mode=data.get("last_active_hvac_mode"),
                owners=dict(data.get("owners") or {}),
                version=data.get("version", 1),
            )
        except KeyError, TypeError:
            return None


class DualModeGenericThermostat(ClimateEntity, RestoreEntity):
    """A thermostat driving separate heater, cooler, fan and dryer devices."""

    _attr_should_poll = False

    def __init__(self, config: ThermostatConfig, unit: str) -> None:
        """Initialize the thermostat."""
        self._config = config
        self._attr_name = config.name
        self._attr_unique_id = config.unique_id
        self._attr_temperature_unit = unit

        self._devices: dict[Role, str] = dict(config.devices)
        self._entity_roles: dict[str, tuple[Role, ...]] = {}
        for role, entity_id in self._devices.items():
            self._entity_roles[entity_id] = (*self._entity_roles.get(entity_id, ()), role)

        self._attr_hvac_modes = [
            mode
            for mode in HVAC_MODE_ORDER
            if mode is HVACMode.OFF
            or (mode is HVACMode.HEAT_COOL and config.heat_cool_enabled)
            or (mode is not HVACMode.HEAT_COOL and MODE_ROLES[mode][0] in self._devices)
        ]

        self._presets: dict[str, PresetTemperatures] = {}
        if config.away.configured:
            self._presets[PRESET_AWAY] = config.away

        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        if config.heat_cool_enabled:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        if self._presets:
            features |= ClimateEntityFeature.PRESET_MODE
            self._attr_preset_modes = [PRESET_NONE, *self._presets]
        self._attr_supported_features = features

        self._hvac_mode = HVACMode.OFF
        self._last_active_mode: HVACMode | None = None
        self._preset = PRESET_NONE
        self._target = config.target_temp
        self._low = config.target_temp_low
        self._high = config.target_temp_high
        self._saved_targets: dict[str, float | None] | None = None
        self._cur_temp: float | None = None
        self._cur_humidity: float | None = None
        self._consent = config.consent_entity is None

        self._lock = asyncio.Lock()
        self._started = False
        self._owners: dict[str, Role] = {}
        self._pending: dict[str, tuple[bool, datetime]] = {}
        self._last_toggled: dict[str, datetime] = {}
        # Devices a mode change or lack of consent turned off (or tried to) that
        # haven't reported off yet; turned off whenever they show up on.
        self._off_owed: set[str] = set()
        # reverse_cycle devices that another device took over from: they switch
        # over by themselves, so they count as off even while still reading on.
        self._replaced: set[str] = set()
        self._recheck_job = HassJob(
            self._async_recheck, "dualmode_generic min_cycle recheck", cancel_on_shutdown=True
        )
        self._recheck_unsub: CALLBACK_TYPE | None = None
        self._recheck_at: datetime | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Subscribe to sources, restore state and start controlling."""
        await super().async_added_to_hass()
        config = self._config

        self.async_on_remove(
            async_track_state_change_event(self.hass, [config.sensor], self._async_sensor_changed)
        )
        if config.humidity_sensor:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [config.humidity_sensor], self._async_humidity_changed
                )
            )
        if config.consent_entity:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [config.consent_entity], self._async_consent_changed
                )
            )
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, list(self._entity_roles), self._async_device_changed
            )
        )
        if config.keep_alive:
            self.async_on_remove(
                async_track_time_interval(
                    self.hass, self._async_keep_alive, config.keep_alive, cancel_on_shutdown=True
                )
            )
        self.async_on_remove(self._cancel_recheck)

        await self._async_restore()
        self.async_on_remove(async_at_start(self.hass, self._async_startup))

    async def _async_startup(self, _hass: HomeAssistant) -> None:
        """Read the current state of every source and act on it.

        Runs once Home Assistant is starting, or straight away if it already is.
        """
        config = self._config
        if (state := self.hass.states.get(config.sensor)) and _is_known(state):
            self._async_update_temp(state)
        if (
            config.humidity_sensor
            and (state := self.hass.states.get(config.humidity_sensor))
            and _is_known(state)
        ):
            self._async_update_humidity(state)
        if config.consent_entity:
            self._consent = _consent_from(self.hass.states.get(config.consent_entity))
        for entity_id in self._entity_roles:
            if state := self.hass.states.get(entity_id):
                self._last_toggled[entity_id] = state.last_changed
        self._started = True
        # Without consent everything starts off, whatever the mode (as in 0.2.x).
        await self._async_control(gate_changed=not self._consent)
        self.async_write_ha_state()

    async def _async_restore(self) -> None:
        """Restore mode, targets and preset from the last run."""
        config = self._config
        initial = self._valid_mode(config.initial_hvac_mode)
        old_state = await self.async_get_last_state()
        if old_state is None:
            self._hvac_mode = initial or HVACMode.OFF
        else:
            mode = self._valid_mode(old_state.state)
            if mode is None:
                if old_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                    _LOGGER.warning(
                        "%s: saved mode %s isn't available with the current configuration;"
                        " starting in %s",
                        self.entity_id,
                        old_state.state,
                        initial or HVACMode.OFF,
                    )
                mode = initial or HVACMode.OFF
            self._hvac_mode = mode

            extra = await self.async_get_last_extra_data()
            data = ThermostatExtraData.from_dict(extra.as_dict()) if extra else None
            if data is not None:
                self._restore_extra(data)
            else:
                self._restore_legacy(old_state)

            preset = old_state.attributes.get(ATTR_PRESET_MODE)
            if preset in self._presets:
                self._preset = preset

        if self._hvac_mode is not HVACMode.OFF:
            self._last_active_mode = self._hvac_mode

    def _restore_extra(self, data: ThermostatExtraData) -> None:
        self._target = data.target_temp
        self._low = data.target_temp_low
        self._high = data.target_temp_high
        self._saved_targets = data.saved_targets
        self._last_active_mode = self._valid_mode(data.last_active_hvac_mode)
        for entity_id, value in data.owners.items():
            try:
                role = Role(value)
            except ValueError:
                continue
            if role in self._entity_roles.get(entity_id, ()):
                self._owners[entity_id] = role

    def _restore_legacy(self, old_state: State) -> None:
        """Restore from state saved by 0.2.x, which only kept visible attributes."""
        attributes = old_state.attributes
        if old_state.state == HVACMode.HEAT_COOL:
            low = attributes.get(ATTR_TARGET_TEMP_LOW)
            high = attributes.get(ATTR_TARGET_TEMP_HIGH)
            if low is not None and high is not None:
                self._low, self._high = float(low), float(high)
        elif (temperature := attributes.get(ATTR_TEMPERATURE)) is not None:
            self._target = float(temperature)

    @property
    def extra_restore_state_data(self) -> ThermostatExtraData:
        """Return state to keep across restarts."""
        return ThermostatExtraData(
            target_temp=self._target,
            target_temp_low=self._low,
            target_temp_high=self._high,
            saved_targets=self._saved_targets,
            last_active_hvac_mode=self._last_active_mode,
            owners={entity_id: role.value for entity_id, role in self._owners.items()},
        )

    # ------------------------------------------------------------------
    # Climate entity properties
    # ------------------------------------------------------------------

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current mode."""
        return self._hvac_mode

    @property
    def hvac_action(self) -> HVACAction:
        """Return what the thermostat's devices are actually doing."""
        if self._hvac_mode is HVACMode.OFF:
            return HVACAction.OFF
        if not self._consent:
            return HVACAction.IDLE
        for role in MODE_ROLES[self._hvac_mode]:
            if role in self._devices and self._role_running(role, actual=True):
                return ROLE_ACTION[role]
        return HVACAction.IDLE

    @property
    def current_temperature(self) -> float | None:
        """Return the sensor temperature."""
        return self._cur_temp

    @property
    def current_humidity(self) -> float | None:
        """Return the sensor humidity."""
        return self._cur_humidity

    @property
    def target_temperature(self) -> float | None:
        """Return the single target, when the mode uses one."""
        mode = self._hvac_mode
        if mode is HVACMode.HEAT_COOL:
            return None
        if mode in (HVACMode.FAN_ONLY, HVACMode.DRY) and self._mode_demand(mode) is Demand.ALWAYS:
            return None
        return self._effective_target(mode)

    @property
    def target_temperature_low(self) -> float | None:
        """Return the low end of the range in heat_cool."""
        return self._effective_range()[0] if self._hvac_mode is HVACMode.HEAT_COOL else None

    @property
    def target_temperature_high(self) -> float | None:
        """Return the high end of the range in heat_cool."""
        return self._effective_range()[1] if self._hvac_mode is HVACMode.HEAT_COOL else None

    @property
    def preset_mode(self) -> str | None:
        """Return the current preset."""
        return self._preset if self._presets else None

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        if self._config.min_temp is not None:
            return self._config.min_temp
        return super().min_temp

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        if self._config.max_temp is not None:
            return self._config.max_temp
        return super().max_temp

    @property
    def precision(self) -> float:
        """Return the display precision."""
        if self._config.precision is not None:
            return self._config.precision
        return super().precision

    @property
    def target_temperature_step(self) -> float:
        """Return the target step, defaulting to the precision."""
        if self._config.target_temp_step is not None:
            return self._config.target_temp_step
        return self.precision

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    async def async_set_hvac_mode(self, hvac_mode: HVACMode | str) -> None:
        """Change the mode and act on it right away."""
        previous = self._enter_mode(hvac_mode)
        await self._async_control(force=True, leaving=previous)
        self.async_write_ha_state()

    def _enter_mode(self, hvac_mode: HVACMode | str) -> HVACMode:
        """Switch modes without acting yet; return the previous mode."""
        mode = self._valid_mode(hvac_mode)
        if mode is None:
            raise ServiceValidationError(
                f"{self.entity_id} doesn't support hvac mode {hvac_mode}; "
                f"supported: {', '.join(self.hvac_modes)}"
            )
        previous = self._hvac_mode
        self._hvac_mode = mode
        if mode is not HVACMode.OFF:
            self._last_active_mode = mode
        # Without a single target of its own, heat/cool start from the range ends.
        if mode is HVACMode.HEAT and self._target is None:
            self._target = self._low
        elif mode is HVACMode.COOL and self._target is None:
            self._target = self._high
        elif mode is HVACMode.HEAT_COOL:
            self._low, self._high = self._effective_range()
        if self._preset != PRESET_NONE:
            self._apply_preset(self._presets[self._preset])
        return previous

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target, the range, or both; optionally with a new mode."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        low = kwargs.get(ATTR_TARGET_TEMP_LOW)
        high = kwargs.get(ATTR_TARGET_TEMP_HIGH)
        if low is not None and high is not None and low > high:
            raise ServiceValidationError(
                f"target_temp_low ({low}) must not be above target_temp_high ({high})"
            )
        # A mode given with the temperature takes effect first, so the target
        # links to the new mode, and both are acted on together.
        leaving = None
        if (requested := kwargs.get(ATTR_HVAC_MODE)) is not None:
            leaving = self._enter_mode(requested)

        mode = self._hvac_mode
        low_moved = False
        # The single target and the range are linked: in heat mode the target
        # is the range's low end, in cool mode its high end.
        if temperature is not None:
            if mode is HVACMode.HEAT:
                self._low, low_moved = temperature, True
            elif mode is HVACMode.COOL:
                self._high = temperature
            elif self._low is not None and self._low == self._target:
                self._low, low_moved = temperature, True
            elif self._high is not None and self._high == self._target:
                self._high = temperature
            self._target = temperature
        if low is not None:
            if mode is HVACMode.HEAT or self._low == self._target:
                self._target = low
            self._low, low_moved = low, True
        if high is not None:
            if mode is HVACMode.COOL or self._high == self._target:
                self._target = high
            self._high = high
        if self._low is not None and self._high is not None and self._low > self._high:
            if low_moved:
                self._high = self._low
            else:
                self._low = self._high

        await self._async_control(force=True, leaving=leaving)
        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Select a preset, or return to the saved targets with 'none'."""
        if preset_mode != PRESET_NONE and preset_mode not in self._presets:
            raise ServiceValidationError(
                f"{self.entity_id} doesn't support preset {preset_mode}; "
                f"supported: {', '.join(self.preset_modes or [])}"
            )
        if preset_mode == self._preset:
            return
        if preset_mode == PRESET_NONE:
            if self._saved_targets is not None:
                self._target = self._saved_targets.get("target_temp")
                self._low = self._saved_targets.get("target_temp_low")
                self._high = self._saved_targets.get("target_temp_high")
            self._saved_targets = None
        else:
            if self._preset == PRESET_NONE:
                self._saved_targets = {
                    "target_temp": self._target,
                    "target_temp_low": self._low,
                    "target_temp_high": self._high,
                }
            self._apply_preset(self._presets[preset_mode])
        self._preset = preset_mode

        await self._async_control(force=True)
        self.async_write_ha_state()

    async def async_turn_on(self) -> None:
        """Return to the last active mode."""
        if self._hvac_mode is not HVACMode.OFF:
            return
        mode = self._last_active_mode or next(
            (mode for mode in TURN_ON_FALLBACK if mode in self.hvac_modes), None
        )
        if mode is not None:
            await self.async_set_hvac_mode(mode)

    async def async_turn_off(self) -> None:
        """Switch to off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _async_sensor_changed(self, event: Event[EventStateChangedData]) -> None:
        new_state = event.data["new_state"]
        if new_state is None or not _is_known(new_state):
            return
        self.async_set_context(event.context)
        self._async_update_temp(new_state)
        if self._started:  # before startup, the startup pass acts on it
            await self._async_control()
        self.async_write_ha_state()

    @callback
    def _async_humidity_changed(self, event: Event[EventStateChangedData]) -> None:
        new_state = event.data["new_state"]
        if new_state is None or not _is_known(new_state):
            return
        self._async_update_humidity(new_state)
        self.async_write_ha_state()

    async def _async_consent_changed(self, event: Event[EventStateChangedData]) -> None:
        granted = _consent_from(event.data["new_state"])
        if granted == self._consent:
            return
        self._consent = granted
        if self._started:
            self.async_set_context(event.context)
            # Revoking stops every device at once, in any mode; granting acts
            # right away.
            await self._async_control(force=True, gate_changed=True)
        self.async_write_ha_state()

    @callback
    def _async_device_changed(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        new_state = event.data["new_state"]
        old_state = event.data["old_state"]
        if new_state is None:
            return
        self._pending.pop(entity_id, None)
        if old_state is None or old_state.state != new_state.state:
            self._replaced.discard(entity_id)
            # min_cycle_duration counts from real changes, not from commands,
            # so a command the device never acted on is retried promptly.
            if new_state.state in (STATE_ON, STATE_OFF):
                self._last_toggled[entity_id] = new_state.last_changed
            if new_state.state == STATE_OFF:
                self._owners.pop(entity_id, None)
                self._off_owed.discard(entity_id)
        # A device that (re)appears gets the thermostat's current decision, and
        # one that should be off but shows up on is turned off.
        came_back = (old_state is None or not _is_known(old_state)) and new_state.state in (
            STATE_ON,
            STATE_OFF,
        )
        owed_off = entity_id in self._off_owed and new_state.state == STATE_ON
        if (came_back or owed_off) and self._started:
            self.hass.async_create_task(self._async_control_and_write(), eager_start=True)
        self.async_write_ha_state()

    async def _async_keep_alive(self, _now: datetime) -> None:
        self.async_set_context(Context())
        await self._async_control(keepalive=True)
        self.async_write_ha_state()

    async def _async_recheck(self, _now: datetime) -> None:
        self._recheck_unsub = None
        self._recheck_at = None
        self.async_set_context(Context())
        await self._async_control_and_write()

    async def _async_control_and_write(self) -> None:
        await self._async_control()
        self.async_write_ha_state()

    @callback
    def _async_update_temp(self, state: State) -> None:
        try:
            value = float(state.state)
            if not math.isfinite(value):
                raise ValueError(f"Sensor has illegal state {state.state}")
        except ValueError as ex:
            _LOGGER.error("Unable to update from sensor: %s", ex)
        else:
            self._cur_temp = value

    @callback
    def _async_update_humidity(self, state: State) -> None:
        try:
            self._cur_humidity = float(state.state)
        except ValueError as ex:
            _LOGGER.error("Unable to update from humidity sensor: %s", ex)

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    async def _async_control(
        self,
        *,
        force: bool = False,
        keepalive: bool = False,
        leaving: HVACMode | None = None,
        gate_changed: bool = False,
    ) -> None:
        """Bring the devices in line with the mode and temperatures.

        ``force`` skips min_cycle_duration and compares with the devices' real
        state (user actions). ``keepalive`` repeats commands for the mode's
        devices. ``leaving`` is the previous mode when the mode just changed:
        devices outside the new mode are then turned off. Otherwise only the
        current mode's devices are touched, so a fan switched on by hand for
        circulation is left alone; in off mode nothing is touched except to
        finish switching devices off. ``gate_changed`` marks a consent change.
        """
        async with self._lock:
            mode = self._hvac_mode
            switching = leaving is not None
            replaceable: frozenset[Role] = frozenset()
            desired: dict[Role, bool] = {}
            if not self._consent and (mode is not HVACMode.OFF or switching or gate_changed):
                # No consent: everything off, whatever the mode (as in 0.2.x).
                desired = dict.fromkeys(self._devices, False)
                force = switching = True
            elif mode is not HVACMode.OFF or switching:
                if switching:
                    mode_entities = self._mode_entities()
                    desired = {
                        role: False
                        for role, entity_id in self._devices.items()
                        if role not in MODE_ROLES[mode] and entity_id not in mode_entities
                    }
                    # reverse_cycle only spans a mode change; heat_cool's own
                    # handover turns the heater off first, as in 0.2.x.
                    if mode is not HVACMode.OFF:
                        replaceable = self._config.reverse_cycle
                if mode is not HVACMode.OFF:
                    desired.update(decide(self._snapshot()))
            await self._async_apply(
                desired,
                force=force,
                keepalive=keepalive,
                owe_offs=switching,
                replaceable=replaceable,
            )

    def _snapshot(self) -> Snapshot:
        mode = self._hvac_mode
        low, high = self._effective_range()
        return Snapshot(
            mode=mode,
            current=self._cur_temp,
            target=self._effective_target(mode),
            target_low=low,
            target_high=high,
            cold_tolerance=self._config.cold_tolerance,
            hot_tolerance=self._config.hot_tolerance,
            fan_behavior=self._config.fan_behavior,
            dryer_behavior=self._config.dryer_behavior,
            configured=frozenset(self._devices),
            running=frozenset(
                role
                for role in MODE_ROLES[mode]
                if role in self._devices and self._role_running(role)
            ),
        )

    async def _async_apply(
        self,
        desired: Mapping[Role, bool],
        *,
        force: bool,
        keepalive: bool,
        owe_offs: bool,
        replaceable: frozenset[Role],
    ) -> None:
        """Send only the commands needed to reach the desired device states."""
        now = dt_util.utcnow()
        mode_entities = self._mode_entities()

        # Several roles can share one entity; it's on if any of them wants it.
        wanted: dict[str, Role | None] = {}
        for role, on in desired.items():
            entity_id = self._devices[role]
            if on:
                wanted[entity_id] = role
            else:
                wanted.setdefault(entity_id, None)
        # Finish switch-offs still owed from earlier, unless the current mode
        # now decides for that device.
        self._off_owed -= mode_entities
        for entity_id in self._off_owed:
            wanted.setdefault(entity_id, None)

        turn_on: list[str] = []
        turn_off: list[str] = []
        resend: list[tuple[str, bool]] = []
        for entity_id, role in wanted.items():
            on = role is not None
            if on:
                self._owners[entity_id] = role
                self._off_owed.discard(entity_id)
            available = self._entity_available(entity_id)
            # User actions compare with the real state; otherwise a command
            # still in flight counts as done, so it isn't repeated.
            current = self._entity_on(entity_id, actual=force)
            if on and entity_id in self._replaced:
                current = False  # it may still read on after handing over
            if not on and owe_offs and (current or not available):
                self._off_owed.add(entity_id)
            if not available:
                if current != on:
                    _LOGGER.debug(
                        "%s: %s is unavailable, not switching it", self.entity_id, entity_id
                    )
                continue
            if current == on:
                if keepalive and entity_id in mode_entities:
                    resend.append((entity_id, on))
                continue
            owed = entity_id in self._off_owed
            if not (force or owed) and (wait := self._cycle_remaining(entity_id, now)) is not None:
                _LOGGER.debug(
                    "%s: min_cycle_duration keeps %s %s for %s more",
                    self.entity_id,
                    entity_id,
                    "off" if on else "on",
                    wait,
                )
                self._schedule_recheck(wait)
                continue
            (turn_on if on else turn_off).append(entity_id)

        # reverse_cycle: when one reverse-cycle device takes over from another
        # (the same unit, switching mode), the outgoing one switches over by
        # itself, so it isn't turned off explicitly.
        if replaceable and any(replaceable.intersection(self._entity_roles[e]) for e in turn_on):
            kept = []
            for entity_id in turn_off:
                if replaceable.intersection(self._entity_roles[entity_id]):
                    self._replaced.add(entity_id)
                    self._off_owed.discard(entity_id)
                else:
                    kept.append(entity_id)
            turn_off = kept

        # Never run a heater and a cooler together: if one's switch-off is held
        # back (min_cycle_duration), the other waits too.
        heater = self._devices.get(Role.HEATER)
        cooler = self._devices.get(Role.COOLER)
        if heater and cooler and heater != cooler:

            def on_after(entity_id: str) -> bool:
                return entity_id in turn_on or (
                    entity_id not in turn_off
                    and entity_id not in self._replaced
                    and self._entity_on(entity_id, actual=True)
                )

            if on_after(heater) and on_after(cooler):
                _LOGGER.debug("%s: holding back start until the other device stops", self.entity_id)
                turn_on = [e for e in turn_on if e not in (heater, cooler)]

        # Break before make.
        for entity_id in turn_off:
            await self._async_switch(entity_id, False)
        for entity_id in turn_on:
            await self._async_switch(entity_id, True)
        for entity_id, on in resend:
            await self._async_switch(entity_id, on, keepalive=True)

    async def _async_switch(self, entity_id: str, on: bool, *, keepalive: bool = False) -> None:
        if keepalive:
            _LOGGER.debug(
                "%s: keep-alive, turning %s %s", self.entity_id, entity_id, "on" if on else "off"
            )
        else:
            _LOGGER.info("%s: turning %s %s", self.entity_id, entity_id, "on" if on else "off")
            self._pending[entity_id] = (on, dt_util.utcnow())
            self._replaced.discard(entity_id)
            if not on:
                self._owners.pop(entity_id, None)
        parent = self._context
        await self.hass.services.async_call(
            HOMEASSISTANT_DOMAIN,
            SERVICE_TURN_ON if on else SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: entity_id},
            context=Context(parent_id=parent.id if parent else None),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _role_running(self, role: Role, *, actual: bool = False) -> bool:
        """Return whether a device is running in this role.

        ``actual`` ignores commands still in flight, for reporting.
        """
        entity_id = self._devices[role]
        if not self._entity_on(entity_id, actual=actual) or entity_id in self._replaced:
            return False
        sharers = self._entity_roles[entity_id]
        if len(sharers) == 1:
            return True
        if (owner := self._owners.get(entity_id)) is not None:
            return owner is role
        # Shared and switched on by someone else: attribute it to the mode.
        in_mode = [r for r in sharers if r in MODE_ROLES[self._hvac_mode]]
        if len(in_mode) == 1:
            return in_mode[0] is role
        if not in_mode:
            return False
        return closer_role(self._cur_temp, *self._effective_range()) is role

    def _entity_on(self, entity_id: str, *, actual: bool = False) -> bool:
        if not actual and (pending := self._pending.get(entity_id)) is not None:
            on, since = pending
            if dt_util.utcnow() - since < PENDING_TIMEOUT:
                return on
            del self._pending[entity_id]
        return self.hass.states.is_state(entity_id, STATE_ON)

    def _mode_entities(self) -> set[str]:
        """Return the entities the current mode controls."""
        return {
            self._devices[role] for role in MODE_ROLES[self._hvac_mode] if role in self._devices
        }

    def _entity_available(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return state is not None and state.state != STATE_UNAVAILABLE

    def _cycle_remaining(self, entity_id: str, now: datetime) -> timedelta | None:
        if not (min_cycle := self._config.min_cycle_duration):
            return None
        if (last := self._last_toggled.get(entity_id)) is None:
            return None
        remaining = last + min_cycle - now
        return remaining if remaining > timedelta(0) else None

    @callback
    def _schedule_recheck(self, delay: timedelta) -> None:
        when = dt_util.utcnow() + delay
        if self._recheck_at is not None and self._recheck_at <= when:
            return
        self._cancel_recheck()
        self._recheck_at = when
        self._recheck_unsub = async_call_later(self.hass, delay, self._recheck_job)

    @callback
    def _cancel_recheck(self) -> None:
        if self._recheck_unsub is not None:
            self._recheck_unsub()
        self._recheck_unsub = None
        self._recheck_at = None

    def _valid_mode(self, value: HVACMode | str | None) -> HVACMode | None:
        try:
            mode = HVACMode(value)
        except ValueError:
            return None
        return mode if mode in self._attr_hvac_modes else None

    def _mode_demand(self, mode: HVACMode) -> Demand | None:
        roles = MODE_ROLES[mode]
        if len(roles) != 1:
            return None
        return role_demand(roles[0], self._config.fan_behavior, self._config.dryer_behavior)

    def _effective_target(self, mode: HVACMode) -> float:
        """Return the single target, defaulting to a value that won't run the device."""
        if self._target is not None:
            return self._target
        return self.max_temp if self._mode_demand(mode) is Demand.COOLING else self.min_temp

    def _effective_range(self) -> tuple[float, float]:
        """Return the heat_cool range, deriving any unknown end."""
        low, high = self._low, self._high
        if self._target is not None:
            low = self._target - DEFAULT_RANGE_OFFSET if low is None else low
            high = self._target + DEFAULT_RANGE_OFFSET if high is None else high
        else:
            low = self.min_temp if low is None else low
            high = self.max_temp if high is None else high
        return low, max(low, high)

    def _apply_preset(self, temps: PresetTemperatures) -> None:
        """Apply a preset's temperatures for the current mode."""
        heat = temps.heat if temps.heat is not None else temps.single
        cool = temps.cool if temps.cool is not None else temps.single
        mode = self._hvac_mode
        if mode is HVACMode.HEAT_COOL:
            # A plain away_temp only lowers the heating end.
            low = heat if heat is not None else self._low
            high = temps.cool if temps.cool is not None else self._high
            if low is not None and high is not None and high < low:
                high = low
            self._low, self._high = low, high
            return
        demand = self._mode_demand(mode)
        value = {Demand.HEATING: heat, Demand.COOLING: cool}.get(demand) if demand else None
        if value is not None:
            self._target = value


def _is_known(state: State) -> bool:
    return state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN)


def _consent_from(state: State | None) -> bool:
    """Consent is granted only while the entity is on."""
    return state is not None and state.state == STATE_ON
