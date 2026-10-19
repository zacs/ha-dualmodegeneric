"""Unit tests for the pure decision logic (no Home Assistant instance needed)."""

from dataclasses import replace

import pytest
from homeassistant.components.climate import HVACMode

from custom_components.dualmode_generic.const import Behavior, Role
from custom_components.dualmode_generic.controller import (
    Demand,
    Snapshot,
    closer_role,
    decide,
    role_demand,
)

ALL_ROLES = frozenset(Role)
BASE = Snapshot(
    mode=HVACMode.HEAT,
    current=22,
    target=22,
    target_low=20,
    target_high=24,
    cold_tolerance=0.5,
    hot_tolerance=0.5,
    fan_behavior=Behavior.NEUTRAL,
    dryer_behavior=Behavior.NEUTRAL,
    configured=ALL_ROLES,
    running=frozenset(),
)


def snap(**changes) -> Snapshot:
    return replace(BASE, **changes)


@pytest.mark.parametrize(
    ("role", "fan", "dryer", "demand"),
    [
        (Role.HEATER, Behavior.COOLER, Behavior.COOLER, Demand.HEATING),
        (Role.COOLER, Behavior.HEATER, Behavior.HEATER, Demand.COOLING),
        (Role.FAN, Behavior.NEUTRAL, Behavior.HEATER, Demand.ALWAYS),
        (Role.FAN, Behavior.COOLER, Behavior.NEUTRAL, Demand.COOLING),
        (Role.FAN, Behavior.HEATER, Behavior.NEUTRAL, Demand.HEATING),
        (Role.DRYER, Behavior.HEATER, Behavior.NEUTRAL, Demand.ALWAYS),
        (Role.DRYER, Behavior.NEUTRAL, Behavior.COOLER, Demand.COOLING),
        (Role.DRYER, Behavior.NEUTRAL, Behavior.HEATER, Demand.HEATING),
    ],
)
def test_role_demand(role: Role, fan: Behavior, dryer: Behavior, demand: Demand) -> None:
    assert role_demand(role, fan, dryer) is demand


@pytest.mark.parametrize(
    ("current", "running", "expected"),
    [
        (21.6, False, False),
        (21.5, False, True),  # inclusive: target - cold_tolerance starts heating
        (22.4, True, True),
        (22.5, True, False),  # inclusive: target + hot_tolerance stops heating
        (22.0, True, True),
        (22.0, False, False),
    ],
)
def test_heat_hysteresis(current: float, running: bool, expected: bool) -> None:
    running_roles = frozenset({Role.HEATER}) if running else frozenset()
    assert decide(snap(current=current, running=running_roles)) == {Role.HEATER: expected}


@pytest.mark.parametrize(
    ("current", "running", "expected"),
    [
        (22.4, False, False),
        (22.5, False, True),
        (21.6, True, True),
        (21.5, True, False),
    ],
)
def test_cool_hysteresis(current: float, running: bool, expected: bool) -> None:
    running_roles = frozenset({Role.COOLER}) if running else frozenset()
    result = decide(snap(mode=HVACMode.COOL, current=current, running=running_roles))
    assert result == {Role.COOLER: expected}


@pytest.mark.parametrize(
    ("mode", "role"),
    [(HVACMode.FAN_ONLY, Role.FAN), (HVACMode.DRY, Role.DRYER)],
)
def test_neutral_needs_no_temperature(mode: HVACMode, role: Role) -> None:
    assert decide(snap(mode=mode, current=None, target=None)) == {role: True}


@pytest.mark.parametrize("mode", [HVACMode.HEAT, HVACMode.COOL])
def test_unknown_temperature_leaves_device_alone(mode: HVACMode) -> None:
    assert decide(snap(mode=mode, current=None)) == {}
    assert decide(snap(mode=mode, target=None)) == {}


def test_off_controls_nothing() -> None:
    assert decide(snap(mode=HVACMode.OFF)) == {}


def test_only_configured_roles_are_decided() -> None:
    assert decide(snap(configured=frozenset({Role.COOLER}))) == {}


def test_modes_only_decide_their_own_devices() -> None:
    """A running fan isn't the thermostat's business in heat mode."""
    result = decide(snap(current=21, running=frozenset({Role.FAN})))
    assert result == {Role.HEATER: True}


@pytest.mark.parametrize(
    ("current", "running", "expected"),
    [
        (22, frozenset(), {Role.HEATER: False, Role.COOLER: False}),
        (19.5, frozenset(), {Role.HEATER: True, Role.COOLER: False}),
        (20.4, frozenset({Role.HEATER}), {Role.HEATER: True, Role.COOLER: False}),
        (20.5, frozenset({Role.HEATER}), {Role.HEATER: False, Role.COOLER: False}),
        (24.5, frozenset(), {Role.HEATER: False, Role.COOLER: True}),
        (23.6, frozenset({Role.COOLER}), {Role.HEATER: False, Role.COOLER: True}),
        (23.5, frozenset({Role.COOLER}), {Role.HEATER: False, Role.COOLER: False}),
        # An overshoot hands over from heating straight to cooling.
        (25, frozenset({Role.HEATER}), {Role.HEATER: False, Role.COOLER: True}),
    ],
)
def test_heat_cool(current: float, running: frozenset[Role], expected: dict) -> None:
    result = decide(snap(mode=HVACMode.HEAT_COOL, current=current, running=running))
    assert result == expected


@pytest.mark.parametrize("current", [23.3, 23.5, 23.6, 23.7, 23.9])
def test_narrow_heat_cool_range_still_idles(current: float) -> None:
    """#83: a range narrower than both tolerances stops heating at low + hot."""
    result = decide(
        snap(
            mode=HVACMode.HEAT_COOL,
            current=current,
            target_low=23.3,
            target_high=23.7,
            cold_tolerance=0.3,
            hot_tolerance=0.3,
            running=frozenset({Role.HEATER}),
        )
    )
    assert result[Role.COOLER] is False
    assert result[Role.HEATER] is (current < 23.6)


@pytest.mark.parametrize(
    ("current", "kept"),
    [(21, Role.HEATER), (23, Role.COOLER)],
)
def test_never_both(current: float, kept: Role) -> None:
    """If both somehow run, only the one that fits the temperature stays on."""
    result = decide(
        snap(
            mode=HVACMode.HEAT_COOL,
            current=current,
            target_low=22,
            target_high=22,
            cold_tolerance=2,
            hot_tolerance=2,
            running=frozenset({Role.HEATER, Role.COOLER}),
        )
    )
    assert [role for role, on in result.items() if on] == [kept]


@pytest.mark.parametrize(
    ("behavior_key", "behavior", "current", "expected"),
    [
        ("fan_behavior", Behavior.COOLER, 22.5, True),
        ("fan_behavior", Behavior.COOLER, 21.5, False),
        ("fan_behavior", Behavior.HEATER, 21.5, True),
        ("fan_behavior", Behavior.HEATER, 22.5, False),
    ],
)
def test_fan_behaviors(
    behavior_key: str, behavior: Behavior, current: float, expected: bool
) -> None:
    result = decide(snap(mode=HVACMode.FAN_ONLY, current=current, **{behavior_key: behavior}))
    assert result == {Role.FAN: expected}


def test_closer_role() -> None:
    assert closer_role(21, 20, 24) is Role.HEATER
    assert closer_role(23, 20, 24) is Role.COOLER
    assert closer_role(None, 20, 24) is Role.HEATER
