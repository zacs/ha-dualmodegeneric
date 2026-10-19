# Changelog

## 1.0.0b1

A rewrite of the control logic with the same YAML configuration. **No configuration changes are needed.** Every option keeps its meaning, entity IDs and unique IDs are unchanged, and the first restart after upgrading restores your mode, targets and preset.

**Requires Home Assistant 2026.4 or newer.** Older installs stay on 0.2.x in HACS.

### Behavior changes

These are all bug fixes. If you relied on one of the old behaviors, please open an issue.

**Heat/cool mode**
- The heater and cooler each have their own on/off thresholds. The heater starts at `target_temp_low - cold_tolerance` and stops at `target_temp_low + hot_tolerance`; the cooler mirrors that around `target_temp_high`. Wide ranges behave as before. Narrow ranges (smaller than both tolerances combined) now go idle instead of heating until the cooler takes over. (#83)
- Setting a heat target above the cool target, or a cool target below the heat target, moves the other end of the range instead of inverting it. A `set_temperature` call with `target_temp_low` above `target_temp_high` is rejected.

**Which devices the thermostat considers "running"**
- Only the current mode's device counts. A fan you switch on yourself for circulation no longer stops heat or cool mode from working, and `hvac_action` no longer reports "heating" while only the fan runs. Devices outside the current mode are left alone until you change mode. (#28, #36)
- Switching modes starts the new mode's device straight away. Previously, if another device had been running, nothing happened until the next temperature reading. This is the likely cause of #67.
- When the same entity is configured as both heater and cooler, it is never switched off and on just to change role. `hvac_action` follows the role it's running in.

**`reverse_cycle`**
- A listed device is skipped when turning devices off only if another device takes over in the same step. That covers both a mode change and heat/cool handing heating over to cooling. Previously it could keep running indefinitely in the new mode, and it stopped the new mode's device from starting. (#36)
- If nothing takes over, for example when switching to a mode that doesn't need to run yet, the device is turned off.

**Timing**
- `min_cycle_duration` is tracked separately for each device. In heat/cool the cooler is now protected too.
- When `min_cycle_duration` holds back a change, the change happens as soon as the duration has passed instead of at the next temperature reading.
- `keep_alive` now re-sends "on" to a running device, which never worked before. In heat/cool it repeats the state of both the heater and the cooler.

**Commands sent to devices**
- In fan-only or dry mode with `neutral` behavior, `turn_on` is no longer re-sent on every temperature update. IR blasters stop beeping on every reading. These modes also run before the sensor has reported, since they don't use the temperature.
- A command isn't repeated while a device hasn't reported back yet. If the device still hasn't changed after 10 seconds, the command is sent again.
- Unavailable devices aren't sent commands. They receive the current decision as soon as they come back.
- Commands are linked to whatever triggered them, so the logbook shows the cause.

**Turning on, starting up and restoring**
- `climate.turn_on` returns to the last active mode, which is remembered across restarts. Before, it could switch the thermostat off, or do nothing after a restart.
- `initial_hvac_mode` is applied when there is no saved state. Before, it was ignored.
- After a restart, all targets come back: the heat/cool range, the single target (even if the thermostat was in heat/cool), and the targets from before a preset. Choosing fan or dry after a restart in heat/cool no longer fails. (#84)
- A saved mode that's no longer configured, for example after removing the cooler, falls back to `initial_hvac_mode` or off.
- The thermostat waits for Home Assistant to finish starting, then acts at once instead of waiting for the next temperature reading.

**Away preset**
- Away now works in heat/cool. `away_temp_heater` sets the low end of the range and `away_temp_cooler` the high end. A plain `away_temp` only lowers the low end. (#54)
- Away follows mode changes: switching from heat to cool while away applies `away_temp_cooler`.
- Leaving away after a restart no longer jumps to `away_temp_cooler`.
- The away preset is offered whenever any away temperature is configured.

**Default targets**
- In cool mode, and for a fan or dryer with `cooler` behavior, a target that was never set now defaults to `max_temp`, so the device stays off. It used to default to `min_temp`, which ran the device flat out.

**`set_temperature`**
- `set_temperature` with `hvac_mode` applies both together. The target links to the new mode, and devices switch in a single step.

### Unchanged on purpose
- In off mode the thermostat never touches its devices. Switching to off still turns everything off.
- Heat, cool, fan-only and dry thresholds compare exactly as before: heating starts at `target - cold_tolerance` and stops at `target + hot_tolerance`, both inclusive.
- If the temperature sensor becomes unavailable, the last reading is kept, as in Home Assistant's built-in generic thermostat.
- Without `consent_entity` granted, all devices are turned off and the mode is kept.

### Under the hood
- The control logic now lives in a pure module (`controller.py`), separate from Home Assistant state handling.
- A test suite covers the integration and runs against Home Assistant 2026.4 and the latest release.
- Unknown `reverse_cycle` entries are logged and ignored.
