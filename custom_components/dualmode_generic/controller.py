"""Decide what each device should be doing.

This module is pure logic: it sees a snapshot of the thermostat and returns the
desired on/off state of the devices the current mode controls. Applying those
decisions (timing, shared entities, service calls) is the climate entity's job.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum

from homeassistant.components.climate import HVACMode

from .const import Behavior, Role

MODE_ROLES: Mapping[HVACMode, tuple[Role, ...]] = {
    HVACMode.OFF: (),
    HVACMode.HEAT: (Role.HEATER,),
    HVACMode.COOL: (Role.COOLER,),
    HVACMode.FAN_ONLY: (Role.FAN,),
    HVACMode.DRY: (Role.DRYER,),
    HVACMode.HEAT_COOL: (Role.HEATER, Role.COOLER),
}

MODE_FOR_ROLE: Mapping[Role, HVACMode] = {
    Role.HEATER: HVACMode.HEAT,
    Role.COOLER: HVACMode.COOL,
    Role.FAN: HVACMode.FAN_ONLY,
    Role.DRYER: HVACMode.DRY,
}


class Demand(Enum):
    """When a device should run."""

    HEATING = "heating"  # when it's too cold
    COOLING = "cooling"  # when it's too hot
    ALWAYS = "always"  # whenever its mode is selected


_BEHAVIOR_DEMAND = {
    Behavior.HEATER: Demand.HEATING,
    Behavior.COOLER: Demand.COOLING,
    Behavior.NEUTRAL: Demand.ALWAYS,
}


def role_demand(role: Role, fan_behavior: Behavior, dryer_behavior: Behavior) -> Demand:
    """Return when a device runs, given the fan/dryer behaviors."""
    if role is Role.HEATER:
        return Demand.HEATING
    if role is Role.COOLER:
        return Demand.COOLING
    return _BEHAVIOR_DEMAND[fan_behavior if role is Role.FAN else dryer_behavior]


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Everything a decision depends on."""

    mode: HVACMode
    current: float | None
    target: float | None
    target_low: float | None
    target_high: float | None
    cold_tolerance: float
    hot_tolerance: float
    fan_behavior: Behavior
    dryer_behavior: Behavior
    configured: frozenset[Role]
    running: frozenset[Role]
    # (cold, hot) tolerances for a device, overriding the shared ones.
    role_tolerances: Mapping[Role, tuple[float, float]] = field(default_factory=dict)
    # Devices that must stay off whatever the temperature (the water guard).
    blocked: frozenset[Role] = frozenset()

    def tolerances(self, role: Role) -> tuple[float, float]:
        """Return a device's (cold, hot) tolerances."""
        return self.role_tolerances.get(role, (self.cold_tolerance, self.hot_tolerance))


def decide(snapshot: Snapshot) -> dict[Role, bool]:
    """Return the desired state of each configured device the mode controls.

    A device is left out when there isn't enough information to decide (no
    temperature reading or target yet); its current state should be kept.
    """
    desired: dict[Role, bool] = {}
    for role in MODE_ROLES[snapshot.mode]:
        if role not in snapshot.configured:
            continue
        if role in snapshot.blocked:
            desired[role] = False
            continue
        cold_tolerance, hot_tolerance = snapshot.tolerances(role)
        wants = _wants_on(
            role_demand(role, snapshot.fan_behavior, snapshot.dryer_behavior),
            running=role in snapshot.running,
            current=snapshot.current,
            setpoint=_setpoint(role, snapshot),
            cold_tolerance=cold_tolerance,
            hot_tolerance=hot_tolerance,
        )
        if wants is not None:
            desired[role] = wants

    if desired.get(Role.HEATER) and desired.get(Role.COOLER):
        # Only reachable if both were already running (e.g. switched on by hand)
        # or the range is inverted; never run both, keep the more useful one.
        keep = closer_role(snapshot.current, snapshot.target_low, snapshot.target_high)
        desired[Role.COOLER if keep is Role.HEATER else Role.HEATER] = False
    return desired


def closer_role(current: float | None, low: float | None, high: float | None) -> Role:
    """Return which of heater/cooler matters at this temperature in heat_cool."""
    if current is None or low is None or high is None:
        return Role.HEATER
    return Role.HEATER if current <= (low + high) / 2 else Role.COOLER


def _setpoint(role: Role, snapshot: Snapshot) -> float | None:
    if snapshot.mode is HVACMode.HEAT_COOL:
        return snapshot.target_low if role is Role.HEATER else snapshot.target_high
    return snapshot.target


def _wants_on(
    demand: Demand,
    *,
    running: bool,
    current: float | None,
    setpoint: float | None,
    cold_tolerance: float,
    hot_tolerance: float,
) -> bool | None:
    """Hysteresis around one setpoint.

    Heating starts at setpoint - cold_tolerance and stops at setpoint +
    hot_tolerance; cooling is the mirror image. Comparisons are inclusive and
    written exactly as in 0.2.x so thresholds behave identically.
    """
    if demand is Demand.ALWAYS:
        return True
    if current is None or setpoint is None:
        return None
    too_cold = setpoint >= current + cold_tolerance
    too_hot = current >= setpoint + hot_tolerance
    if demand is Demand.HEATING:
        return not too_hot if running else too_cold
    return not too_cold if running else too_hot
