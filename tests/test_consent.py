"""The optional consent entity that pauses the thermostat."""

from homeassistant.components.climate import HVACAction, HVACMode
from homeassistant.core import HomeAssistant

from .common import (
    CONSENT,
    HEATER,
    async_call,
    async_set_temperature,
    async_setup_devices,
    async_setup_thermostat,
    async_toggle,
    devices_on,
    is_on,
    thermostat,
)

CONFIG = {"consent_entity": CONSENT, "target_temp": 22}


async def test_consent_granted(hass: HomeAssistant) -> None:
    """With consent on, the thermostat works normally."""
    await async_setup_devices_with_consent(hass, consent=True)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert is_on(hass, HEATER)


async def test_consent_revoked_and_restored(hass: HomeAssistant) -> None:
    """Revoking consent stops devices but keeps the mode; restoring resumes."""
    await async_setup_devices_with_consent(hass, consent=True)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert is_on(hass, HEATER)

    await async_toggle(hass, CONSENT, False)
    state = thermostat(hass)
    assert devices_on(hass) == set()
    assert state.state == HVACMode.HEAT
    assert state.attributes["hvac_action"] == HVACAction.IDLE

    await async_set_temperature(hass, 15)
    assert devices_on(hass) == set()

    await async_toggle(hass, CONSENT, True)
    assert devices_on(hass) == {"heater"}


async def test_no_consent_blocks_start(hass: HomeAssistant) -> None:
    """Without consent, selecting a mode doesn't start anything."""
    await async_setup_devices_with_consent(hass, consent=False)
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == set()
    assert thermostat(hass).state == HVACMode.HEAT


async def test_missing_consent_entity_blocks(hass: HomeAssistant) -> None:
    """A consent entity that doesn't exist (or is unavailable) means no consent."""
    await async_setup_thermostat(
        hass, temperature=18, consent_entity="binary_sensor.missing", target_temp=22
    )
    await async_call(hass, "set_hvac_mode", hvac_mode="heat")
    assert devices_on(hass) == set()


async def async_setup_devices_with_consent(hass: HomeAssistant, consent: bool) -> None:
    """Set up the thermostat with the consent entity already in a given state."""
    await async_setup_devices(hass)
    await async_toggle(hass, CONSENT, consent)
    await async_setup_thermostat(hass, temperature=18, **CONFIG)
