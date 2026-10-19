# Changelog

## 1.0.0b3

New options, all optional and available in the UI and in YAML. Existing configurations don't change.

- **Fan modes (#11).** With `fan_with: heater` (or `cooler`, or both), the thermostat gets a fan mode selector. Auto runs the fan whenever those devices run, plus an optional `fan_off_delay`; On runs it all the time; Off leaves it alone.
- **More presets:** comfort, eco, home, sleep and activity join away. Each takes `<preset>_temp`, plus `_heater` and `_cooler` variants that set the range in Heat/cool, like away does.
- **`max_cycle_duration` and `cycle_cooldown`**, as in the built-in thermostat: stop a device after it has run this long, and let it rest this long before starting again.
- **Separate heater and cooler tolerances (#37):** `heater_cold_tolerance`, `heater_hot_tolerance`, `cooler_cold_tolerance` and `cooler_hot_tolerance` override the shared tolerances for one device. `heater_hot_tolerance: 0` stops heating right at the target, which #83 asked about.
- **`tamper_entity`:** while it's on, everything is kept off, like consent but the other way round. Unavailable doesn't block. Use it for window sensors.
- **Water temperature guard** for hydronic systems: heating waits until the supply water is hot enough, cooling until it's cold enough. Uses the option names from #88, so its users can switch over.

UI:
- A new **Interlocks** step holds consent, tamper and the water guard. **Away and consent** became **Presets**.
- Presets, the separate tolerances and the water guard are collapsible sections.

## 1.0.0b2

**Set up thermostats from the UI.** Go to *Settings → Devices & services → Helpers → Create helper → Multi-Mode Generic Thermostat*. YAML keeps working unchanged alongside it. Existing YAML thermostats aren't imported, so nothing moves unless you recreate it yourself.

- Every YAML option is available in the UI, except `unique_id`, which UI thermostats don't need.
- Fields only appear when they apply: heat/cool needs a heater and a cooler, the behavior choices need a fan or dryer, and so on.
- To change a thermostat later, open it and select **Configure**. The options are split into four sections, and saving one reloads the thermostat.
- Removing a device also clears the settings that only applied to it, such as its away temperature or its `reverse_cycle` entry.
- Renaming the entity ID of a sensor or device updates the thermostat to match.
- UI thermostats can download diagnostics, which show the configuration and the current state of every sensor and device. Please attach them to issues.

Also new:
- Errors from `climate.set_hvac_mode`, `set_temperature` and `set_preset_mode` are translated, and name the modes or presets that are allowed.
- `precision` and `target_temp_step` accept quoted values in YAML, e.g. `"0.5"`.
- The README has been rewritten, with recipes for reverse-cycle units, compressor and valve relays, and schedules.
- The integration has its own icon.

## 1.0.0b1

A rewrite of the control logic with the same YAML configuration. **No configuration changes are needed.** Every option keeps its meaning, entity IDs and unique IDs are unchanged, and the first restart after upgrading restores your mode, targets and preset.

**Requires Home Assistant 2026.4 or newer.** Older installs stay on 0.2.x in HACS.

### Behavior changes

Most of these are bug fixes; the rest are noted as deliberate. If you relied on one of the old behaviors, please open an issue.

**Heat/cool mode**
- The heater and cooler each have their own on/off thresholds. The heater starts at `target_temp_low - cold_tolerance` and stops at `target_temp_low + hot_tolerance`; the cooler mirrors that around `target_temp_high`. Wide ranges behave as before. Narrow ranges (smaller than both tolerances combined) now go idle instead of heating until the cooler takes over. (#83)
- Setting a heat target above the cool target, or a cool target below the heat target, moves the other end of the range instead of inverting it. A `set_temperature` call with `target_temp_low` above `target_temp_high` is rejected.

**Which devices the thermostat considers "running"**
- Only the current mode's device counts. A fan you switch on yourself for circulation no longer stops heat or cool mode from working, and `hvac_action` no longer reports "heating" while only the fan runs. Devices outside the current mode are left alone until you change mode. (#28, #36)
- Switching modes starts the new mode's device straight away. Previously, if another device had been running, nothing happened until the next temperature reading. This is the likely cause of #67.
- When the same entity is configured as both heater and cooler, it is never switched off and on just to change role. `hvac_action` follows the role it's running in.

**`reverse_cycle`**
- On a mode change, a listed device is no longer explicitly turned off only when another listed device takes over in the same step, i.e. the same unit switching modes. It used to be skipped whatever happened, so it could keep running in the new mode and stopped the new mode's device from starting. (#36)
- If a device that isn't listed takes over (say a separate fan), or nothing does yet, the outgoing device is turned off.
- A device that handed over counts as off, even if it still reads on (optimistic template switches do). When it's needed again it is sent "on".
- A device that handed over isn't sent "off" either, since an IR template switch would power the unit off. The exceptions are switching to off and revoking consent.
- Unchanged: `reverse_cycle` only applies to mode changes. In heat/cool, handing heating over to cooling still turns the heater off first. That matters when the heater is a group that shares a relay with the cooler.

**Timing**
- `min_cycle_duration` is tracked separately for each device. In heat/cool the cooler is now protected too.
- `min_cycle_duration` counts from the device's actual state changes. A command the device didn't act on is retried without waiting for it.
- When `min_cycle_duration` holds back a change, the change happens as soon as the duration has passed instead of at the next temperature reading.
- The thermostat never starts the heater while the cooler runs, or the reverse. If `min_cycle_duration` keeps one running, or a command to start it is still on its way, the other waits. This includes one you switched on by hand: in cool mode, the cooler won't start while you run the heater.
- `keep_alive` now re-sends "on" to a running device, which never worked before. In heat/cool it repeats the state of both the heater and the cooler.
- Deliberate change: `keep_alive` respects `min_cycle_duration`. It used to ignore it.

**Commands sent to devices**
- In fan-only or dry mode with `neutral` behavior, `turn_on` is no longer re-sent on every temperature update. IR blasters stop beeping on every reading. These modes also run before the sensor has reported, since they don't use the temperature.
- A command isn't repeated while it's on its way to a device, meaning until the device reports the new state. Other updates from the device don't count. If the device still hasn't changed after 10 seconds, the command is re-sent on the next temperature update.
- Changing the mode, the target or the preset sends a command whenever the device, or a command still on its way to it, disagrees. So a quick change of mind is never lost. What you asked for keeps being re-asserted until the device reports it, without waiting for `min_cycle_duration`.
- Unavailable devices aren't sent commands, `keep_alive` included. They receive the current decision as soon as they come back.
- A device that should have been switched off by a mode change, by switching to off, or by consent being revoked, but missed it, is switched off when it shows up on. Being unavailable at the time counts as missing it. This also happens in off mode, until the device reports off. Coming back as "unknown" doesn't count as reporting off.
- Commands are linked to whatever triggered them, so the logbook shows the cause.

**Turning on, starting up and restoring**
- `climate.turn_on` returns to the last active mode, which is remembered across restarts. Before, it could switch the thermostat off, or do nothing after a restart.
- `initial_hvac_mode` is applied when there is no saved state. Before, it was ignored.
- After a restart, all targets come back: the heat/cool range, the single target (even if the thermostat was in heat/cool), and the targets from before a preset. Choosing fan or dry after a restart in heat/cool no longer fails. (#84)
- A saved mode that's no longer configured, for example after removing the cooler, falls back to `initial_hvac_mode` or off.
- The thermostat waits until Home Assistant has loaded its integrations and is starting up, then acts at once instead of waiting for the next temperature reading.

**Away preset**
- Away now works in heat/cool. `away_temp_heater` sets the low end of the range and `away_temp_cooler` the high end. A plain `away_temp` only lowers the low end. (#54)
- Away follows mode changes: switching from heat to cool while away applies `away_temp_cooler`.
- Leaving away after a restart no longer jumps to `away_temp_cooler`.
- The away preset is offered whenever any away temperature is configured.
- Deliberate change: away also sets the target in fan-only and dry mode when their behavior is `heater` or `cooler`. It uses `away_temp_heater` or `away_temp_cooler` respectively, falling back to `away_temp`. It used to change only heat and cool.

**Default targets**
- In cool mode, and for a fan or dryer with `cooler` behavior, a target that was never set now defaults to `max_temp`, so the device stays off. It used to default to `min_temp`, which ran the device flat out.

**`set_temperature`**
- `set_temperature` with `hvac_mode` applies both together. The target links to the new mode, and devices switch in a single step.

### Unchanged on purpose
- In off mode the thermostat leaves its devices alone, so you can run them by hand. The exceptions are the same as before: switching to off turns everything off, and revoking consent turns everything off in any mode. The only addition is finishing a switch-off a device missed (above).
- Heat, cool, fan-only and dry thresholds compare exactly as before: heating starts at `target - cold_tolerance` and stops at `target + hot_tolerance`, both inclusive.
- If the temperature sensor becomes unavailable, the last reading is kept, as in Home Assistant's built-in generic thermostat.
- Without `consent_entity` granted, all devices are turned off and the mode is kept. This happens at startup too.

### Under the hood
- The control logic now lives in a pure module (`controller.py`), separate from Home Assistant state handling.
- A test suite covers the integration and runs against Home Assistant 2026.4 and the latest release.
- Unknown `reverse_cycle` entries are logged and ignored.
- Humidity sensor updates refresh the displayed humidity without re-running the control logic.
