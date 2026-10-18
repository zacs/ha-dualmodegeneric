"""Helpers shared by the dualmode_generic tests.

Devices are real ``input_boolean`` entities, so turning one on or off genuinely
changes its state and the thermostat sees the same events it would in production.
"""

from __future__ import annotations

from typing import Any

from homeassistant.const import (
    EVENT_CALL_SERVICE,
    EVENT_HOMEASSISTANT_START,
    STATE_ON,
)
from homeassistant.core import CoreState, Event, HomeAssistant, State
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import mock_restore_cache

DOMAIN = "dualmode_generic"
ENTITY = "climate.test"
HEATER = "input_boolean.heater"
COOLER = "input_boolean.cooler"
FAN = "input_boolean.fan"
DRYER = "input_boolean.dryer"
CONSENT = "input_boolean.consent"
SENSOR = "sensor.temperature"
HUMIDITY = "sensor.humidity"


def thermostat_config(**overrides: Any) -> dict[str, Any]:
    """Return a YAML-style platform config; a value of None drops the key."""
    config: dict[str, Any] = {
        "platform": DOMAIN,
        "name": "test",
        "heater": HEATER,
        "cooler": COOLER,
        "target_sensor": SENSOR,
    }
    config.update(overrides)
    return {key: value for key, value in config.items() if value is not None}


async def async_setup_devices(hass: HomeAssistant) -> None:
    """Create the toggleable devices and HA's turn_on/turn_off services."""
    await async_setup_component(hass, "homeassistant", {})
    await async_setup_component(
        hass,
        "input_boolean",
        {"input_boolean": {name: None for name in ("heater", "cooler", "fan", "dryer", "consent")}},
    )


async def async_setup_thermostat(
    hass: HomeAssistant, temperature: float | str | None = 20, **overrides: Any
) -> None:
    """Set up devices, the temperature sensor and one thermostat."""
    await async_setup_devices(hass)
    if temperature is not None:
        hass.states.async_set(SENSOR, str(temperature))
    assert await async_setup_component(hass, "climate", {"climate": thermostat_config(**overrides)})
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY) is not None, "thermostat was not created"


async def async_setup_restored(
    hass: HomeAssistant,
    state: str,
    attributes: dict[str, Any] | None = None,
    temperature: float | str | None = 20,
    **overrides: Any,
) -> None:
    """Set up a thermostat as if HA restarted with ``state`` saved."""
    mock_restore_cache(hass, [State(ENTITY, state, attributes or {})])
    hass.set_state(CoreState.starting)
    await async_setup_thermostat(hass, temperature, **overrides)
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_START)
    await hass.async_block_till_done()


async def async_call(hass: HomeAssistant, service: str, **data: Any) -> None:
    """Call a climate service on the test thermostat and settle."""
    await hass.services.async_call("climate", service, {"entity_id": ENTITY, **data}, blocking=True)
    await hass.async_block_till_done()


async def async_set_temperature(hass: HomeAssistant, value: float | str) -> None:
    """Report a new reading from the temperature sensor."""
    hass.states.async_set(SENSOR, str(value))
    await hass.async_block_till_done()


async def async_toggle(hass: HomeAssistant, entity_id: str, on: bool) -> None:
    """Toggle a device directly, as a user or another automation would."""
    await hass.services.async_call(
        "input_boolean",
        "turn_on" if on else "turn_off",
        {"entity_id": entity_id},
        blocking=True,
    )
    await hass.async_block_till_done()


def is_on(hass: HomeAssistant, entity_id: str) -> bool:
    """Return whether a device is on."""
    return hass.states.is_state(entity_id, STATE_ON)


def devices_on(hass: HomeAssistant) -> set[str]:
    """Return the short names of every device that is currently on."""
    return {
        entity_id.split(".")[1]
        for entity_id in (HEATER, COOLER, FAN, DRYER)
        if is_on(hass, entity_id)
    }


def thermostat(hass: HomeAssistant) -> State:
    """Return the thermostat's current state."""
    state = hass.states.get(ENTITY)
    assert state is not None
    return state


class ServiceCallRecorder:
    """Record the homeassistant.turn_on/turn_off calls the thermostat makes."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Start listening."""
        self.calls: list[tuple[str, str]] = []
        self._unsub = hass.bus.async_listen(EVENT_CALL_SERVICE, self._record)

    def _record(self, event: Event) -> None:
        if event.data["domain"] != "homeassistant":
            return
        entity_id = event.data["service_data"]["entity_id"]
        self.calls.append((event.data["service"], entity_id))

    def clear(self) -> None:
        """Forget calls recorded so far."""
        self.calls.clear()
