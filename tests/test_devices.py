"""How commands reach devices: sharing, reverse_cycle, availability, contexts."""

from datetime import timedelta

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.climate import HVACAction
from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.core import Context, Event, HomeAssistant, callback

from .common import (
    COOLER,
    ENTITY,
    FAN,
    HEATER,
    ServiceCallRecorder,
    async_call,
    async_set_temperature,
    async_setup_thermostat,
    async_toggle,
    devices_on,
    is_on,
    thermostat,
)

# A device with no integration behind it: commands are sent, but its state
# only changes when the test says so (like an IR blaster or a lossy RF switch).
IR_HEATER = "switch.ir_heater"


@pytest.mark.parametrize(
    ("reverse_cycle", "expected"),
    [
        # Normally the outgoing device is turned off before the new one starts.
        ([], [("turn_off", COOLER), ("turn_on", HEATER)]),
        # A reverse-cycle unit switches over by itself when the heater turns on.
        ("cooler, heater", [("turn_on", HEATER)]),
    ],
)
async def test_mode_change_handover(
    hass: HomeAssistant, reverse_cycle: list | str, expected: list
) -> None:
    """Cooling -> heating in one step, with and without reverse_cycle."""
    await async_setup_thermostat(hass, temperature=26, target_temp=22, reverse_cycle=reverse_cycle)
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    assert is_on(hass, COOLER)
    recorder = ServiceCallRecorder(hass)
    await async_call(hass, "set_temperature", temperature=28, hvac_mode="heat")
    assert recorder.calls == expected
    assert thermostat(hass).attributes["temperature"] == 28


@pytest.mark.parametrize("reverse_cycle", [[], "cooler, heater"])
async def test_heat_cool_handover_turns_off_first(
    hass: HomeAssistant, reverse_cycle: list | str
) -> None:
    """heat_cool handing heat over to cool turns the heater off first, as in 0.2.x.

    reverse_cycle only spans mode changes: with a heater wired as a relay group
    (heat valve + compressor), keeping it on would keep the valve in heat.
    """
    await async_setup_thermostat(
        hass,
        temperature=19,
        enable_heat_cool=True,
        target_temp_low=20,
        target_temp_high=24,
        reverse_cycle=reverse_cycle,
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    assert is_on(hass, HEATER)
    recorder = ServiceCallRecorder(hass)
    await async_set_temperature(hass, 25)
    assert recorder.calls == [("turn_off", HEATER), ("turn_on", COOLER)]


async def test_shared_heater_and_cooler_entity(hass: HomeAssistant) -> None:
    """One entity used as heater and cooler is never cycled off and on to switch roles."""
    await async_setup_thermostat(
        hass,
        temperature=19,
        cooler=HEATER,
        enable_heat_cool=True,
        target_temp_low=20,
        target_temp_high=24,
        cold_tolerance=0.5,
        hot_tolerance=0.5,
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat_cool")
    assert is_on(hass, HEATER)
    assert thermostat(hass).attributes["hvac_action"] == HVACAction.HEATING

    recorder = ServiceCallRecorder(hass)
    await async_set_temperature(hass, 25)  # overshoot: heating hands over to cooling
    assert recorder.calls == []
    assert is_on(hass, HEATER)
    assert thermostat(hass).attributes["hvac_action"] == HVACAction.COOLING

    await async_set_temperature(hass, 23.5)
    assert recorder.calls == [("turn_off", HEATER)]
    assert thermostat(hass).attributes["hvac_action"] == HVACAction.IDLE


async def test_manual_fan_left_alone_until_mode_changes(hass: HomeAssistant) -> None:
    """#28: a fan run by hand keeps running while heat mode cycles the heater."""
    await async_setup_thermostat(hass, temperature=21, fan=FAN, target_temp=22)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_toggle(hass, FAN, True)
    for reading in (23, 21, 23):
        await async_set_temperature(hass, reading)
        assert is_on(hass, FAN)
    # Choosing a mode still turns off devices that aren't part of it.
    await async_call(hass, "set_hvac_mode", hvac_mode="cool")
    assert devices_on(hass) == {"cooler"}


async def test_no_repeat_while_command_in_flight(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    """A device that hasn't reported back yet isn't sent the same command again."""
    hass.states.async_set(IR_HEATER, "off")
    await async_setup_thermostat(hass, temperature=21, heater=IR_HEATER, target_temp=22)
    recorder = ServiceCallRecorder(hass)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_set_temperature(hass, 20.9)
    await async_set_temperature(hass, 20.8)
    assert recorder.calls == [("turn_on", IR_HEATER)]

    # If it still hasn't switched after a while, the command is retried.
    freezer.tick(timedelta(seconds=11))
    await async_set_temperature(hass, 20.7)
    assert recorder.calls == [("turn_on", IR_HEATER)] * 2


async def test_unavailable_device_is_not_commanded(hass: HomeAssistant) -> None:
    """Commands wait until the device is back, then are sent straight away."""
    hass.states.async_set(IR_HEATER, "unavailable")
    await async_setup_thermostat(hass, temperature=21, heater=IR_HEATER, target_temp=22)
    recorder = ServiceCallRecorder(hass)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    await async_set_temperature(hass, 20.5)
    assert recorder.calls == []

    hass.states.async_set(IR_HEATER, "off")
    await hass.async_block_till_done()
    assert recorder.calls == [("turn_on", IR_HEATER)]


async def test_commands_carry_the_triggering_context(hass: HomeAssistant) -> None:
    """Device commands are children of the call that caused them (for the logbook)."""
    await async_setup_thermostat(hass, temperature=21, target_temp=22)
    contexts: list[Context] = []

    @callback
    def record(event: Event) -> None:
        if event.data["domain"] == "homeassistant":
            contexts.append(event.context)

    hass.bus.async_listen(EVENT_CALL_SERVICE, record)
    context = Context()
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": ENTITY, "hvac_mode": "heat"},
        blocking=True,
        context=context,
    )
    await hass.async_block_till_done()
    assert [c.parent_id for c in contexts] == [context.id]
