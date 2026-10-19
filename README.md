# Multi-Mode Generic Thermostat for Home Assistant

One thermostat for up to four separate devices: a **heater**, a **cooler**, a **fan** and a **dryer**. Each can be any switch-like entity: relays, smart plugs, template switches driving an IR blaster or another climate entity, groups, and so on. It began as a fork of Home Assistant's built-in [`generic_thermostat`](https://www.home-assistant.io/integrations/generic_thermostat/), which only drives a single device.

- Each device adds a mode: a heater adds Heat, a cooler adds Cool, a fan adds Fan only and a dryer adds Dry.
- A heater and a cooler together can also offer **Heat/cool**, which keeps the temperature within a range.
- The fan can also run alongside the heater or cooler, with Auto and On fan modes.
- Presets, run-time limits, consent and tamper entities, and a water temperature guard for hydronic systems.
- Set it up from the UI or in YAML.

Requires **Home Assistant 2026.4** or newer. See [CHANGELOG.md](CHANGELOG.md) for what's new.

> Thanks to [shandoosheri](https://community.home-assistant.io/t/heat-cool-generic-thermostat/76443) for the original idea, and to everyone who has contributed since.

## Installation

**HACS (recommended):**
1. Install [HACS](https://hacs.xyz/).
2. Add `https://github.com/zacs/ha-dualmodegeneric` as a custom repository of type *Integration*.
3. Install **Multi-Mode Generic Thermostat** and restart Home Assistant.

**Manual:** copy `custom_components/dualmode_generic` into your `<config>/custom_components/` folder and restart Home Assistant.

## Setup

### From the UI
Go to **Settings → Devices & services → Helpers → Create helper → Multi-Mode Generic Thermostat**. The steps are:
1. **Sensor and devices:** the temperature sensor and the devices to control. Devices can be switches, input booleans, fans, lights, groups or dehumidifiers.
2. **How the devices work:** heat/cool mode, fan and dryer behavior, reverse-cycle devices, and running the fan alongside the heater or cooler. This step only appears when it applies.
3. **Temperatures and timing:** tolerances, limits, run times and keep-alive.
4. **Presets.**
5. **Interlocks:** consent, tamper and the water temperature guard.

To change anything later, open the helper and select **Configure**.

### In YAML
```yaml
climate:
  - platform: dualmode_generic
    name: Living room
    unique_id: living_room_thermostat
    target_sensor: sensor.living_room_temperature
    heater: switch.heater
    cooler: switch.air_conditioner
    fan: switch.fan
    enable_heat_cool: true
    cold_tolerance: 0.3
    hot_tolerance: 0.3
    min_cycle_duration:
      minutes: 5
    away_temp_heater: 16
    away_temp_cooler: 28
```
After editing YAML, call the `dualmode_generic.reload` action to apply changes without restarting. Configurations written for 0.2.x work unchanged.

## Options

| Option | Default | What it does |
| --- | --- | --- |
| `target_sensor` | required | Temperature sensor the thermostat acts on. |
| `heater`, `cooler`, `fan`, `dryer` | – | Devices to control. At least one is needed. Each adds its mode. |
| `name` | Generic Thermostat | |
| `unique_id` | – | YAML only. Lets you manage the entity in the UI. |
| `enable_heat_cool` | `false` | Adds Heat/cool mode. Needs both a heater and a cooler. |
| `cold_tolerance` | 0.3 | Heating starts at `target − cold_tolerance`; cooling stops there too. |
| `hot_tolerance` | 0.3 | Cooling starts at `target + hot_tolerance`; heating stops there too. |
| `heater_cold_tolerance`, `heater_hot_tolerance`, `cooler_cold_tolerance`, `cooler_hot_tolerance` | the shared ones | Tolerances for just the heater or the cooler. `heater_hot_tolerance: 0` stops heating right at the target. |
| `target_temp` | – | Starting target, used until you set one. |
| `target_temp_low`, `target_temp_high` | – | Starting Heat/cool range. |
| `min_temp`, `max_temp` | 7 °C, 35 °C | Limits for the target. |
| `fan_behavior`, `dryer_behavior` | `neutral` | `neutral`: always on in its mode. `cooler`: runs when too warm. `heater`: runs when too cold. |
| `reverse_cycle` | – | Devices that are one unit switching modes, e.g. `heater, cooler`. See [Reverse-cycle air conditioners](#reverse-cycle-air-conditioners). |
| `min_cycle_duration` | – | Once a device switches on or off, it stays that way at least this long. |
| `max_cycle_duration` | – | A device that has run this long is stopped, even if it's still needed. |
| `cycle_cooldown` | – | After a device stops, it rests this long before starting again. |
| `keep_alive` | – | Repeat the current command this often, for devices that can lose state. |
| `initial_hvac_mode` | `off` | Mode on the very first start. Afterwards the last mode is restored. |
| `away_temp`, `comfort_temp`, `eco_temp`, `home_temp`, `sleep_temp`, `activity_temp` | – | Target for each preset. Setting any of a preset's temperatures adds the preset. |
| `away_temp_heater`, `away_temp_cooler` (and the same for every preset) | – | The preset's targets for heating and cooling. In Heat/cool they set the low and high ends of the range. Where a preset has no temperature for the mode, your own target applies. |
| `fan_with` | – | `heater`, `cooler` or both: adds fan modes, and in Auto the fan runs whenever these devices run. See [Fan modes](#fan-modes). |
| `fan_off_delay` | – | In Auto, the fan keeps running this long after the device stops. |
| `consent_entity` | – | While this entity isn't `on`, every device is kept off. |
| `tamper_entity` | – | While this entity is `on`, every device is kept off. Unavailable doesn't block. |
| `water_sensor` | – | Supply water temperature, for the [water guard](#hydronic-systems). |
| `water_setpoint_heat`, `water_setpoint_cool` | – | Heating runs only while the water is at least `water_setpoint_heat − water_tolerance`; cooling only while it's at most `water_setpoint_cool + water_tolerance`. |
| `water_setpoint_heat_entity`, `water_setpoint_cool_entity` | – | Take the setpoints from an entity instead, such as an `input_number`. |
| `water_tolerance` | 0.3 | |
| `target_humidity_sensor` | – | Shown as the current humidity only. |
| `precision`, `target_temp_step` | system default | `0.1`, `0.5` or `1`. |

## How it behaves

| Mode | Device | Starts at | Stops at |
| --- | --- | --- | --- |
| Heat | heater | target − cold_tolerance | target + hot_tolerance |
| Cool | cooler | target + hot_tolerance | target − cold_tolerance |
| Heat/cool | heater | low − cold_tolerance | low + hot_tolerance |
| | cooler | high + hot_tolerance | high − cold_tolerance |
| Fan only, Dry | fan, dryer | depends on behavior: always (`neutral`), like a cooler, or like a heater | |
| Off | – | never | – |

The rules worth knowing:
- **Only the current mode's device is controlled**, plus the fan when a [fan mode](#fan-modes) runs it. A fan you run yourself keeps running while heat mode cycles the heater. Changing mode turns off devices that aren't part of the new mode.
- **Off leaves your devices alone.** Switching to off turns everything off once. After that, nothing is touched except to finish switching off a device that missed it, so you can run devices by hand.
- **Heater and cooler never run at the same time.** In Heat/cool, the system is idle between the two thresholds.
- **`min_cycle_duration` applies per device**, and takes effect as soon as it has passed. Changing the mode, target or preset overrides it, because that's you asking.
- **`max_cycle_duration` and `cycle_cooldown` apply to each device the mode runs**, as in the built-in thermostat. Changing the mode, target or preset skips the cooldown. The cooldown follows a run, not a restart of Home Assistant.
- **Without consent, or with the tamper entity on**, every device is turned off at once and the mode is kept. This applies in any mode. When they clear, devices start again within `min_cycle_duration` and `cycle_cooldown`.
- **Restarts restore everything:** mode, all targets, preset, fan mode, and the mode `climate.turn_on` returns to.
- **Devices that misbehave are handled.**
  - Commands aren't repeated while a device hasn't reported back yet.
  - Unavailable devices aren't sent commands, and get the current decision once they're back.
  - A device that missed being switched off is switched off when it shows up on.
- **If the temperature sensor goes unavailable**, the last reading is kept.

## Recipes

### Reverse-cycle air conditioners
Use template switches that put the unit in each mode, and list them in `reverse_cycle`. The unit can be driven over IR, or by setting the mode of another climate entity.

When you change mode and the new mode's switch needs to turn on, the old switch isn't turned off first. The unit changes mode directly instead of powering off and back on. If the new mode doesn't need to run yet, the old switch is turned off. A listed device that's replaced this way counts as off, even if its template switch still reads on.

```yaml
reverse_cycle: heater, cooler, fan, dryer
```

Only list devices that really are one unit. If the incoming device isn't listed, the outgoing one is turned off first. In Heat/cool, handing heating over to cooling always turns the heater off first.

### Compressor and reversing-valve relays
Don't point `heater` at a group that shares a relay with `cooler`. Create one template switch per mode instead. For example, *heat* switches the valve and the compressor on, and *cool* switches the valve off and the compressor on. Make each template's state reflect its own mode, then list the template switches in `reverse_cycle`.

### One relay that both heats and cools
If something else decides the direction (a changeover valve, a seasonal setting), set `heater` and `cooler` to the same entity. The thermostat never switches it off and on just to change role, and reports heating or cooling based on which side of the range triggered it.

### Fan modes
Set `fan_with` to the devices the fan should run with, and the thermostat gets a fan mode selector:
- **Auto** runs the fan whenever those devices run, plus `fan_off_delay` after they stop. Use it for a fan that spreads a space heater's warmth (#11). The fan always starts with them, even within its own `min_cycle_duration`.
- **On** runs the fan all the time, in every mode but Off. Use it for continuous circulation while a compressor cycles.
- **Off** leaves the fan alone, as without `fan_with`.

```yaml
fan: switch.fan
fan_with: heater
fan_off_delay:
  minutes: 3
```

Fan only mode still runs the fan by itself, as set by `fan_behavior`. A fan listed in `reverse_cycle` is the same unit as the heater or cooler, so it can't use `fan_with`.

### Schedules and windows
Set `consent_entity` to a schedule, a calendar or an input boolean. The thermostat keeps everything off whenever it isn't `on`. For a window sensor, set `tamper_entity` instead: everything stays off while it's `on`.

### Hydronic systems
Heating a room with water that's still cold only blows cold air. The water guard holds back heating until the supply water is hot enough, and cooling until it's cold enough:

```yaml
water_sensor: sensor.supply_water
water_setpoint_heat: 35
water_setpoint_cool_entity: input_number.chilled_water_setpoint
water_tolerance: 1
```

- Each device checks its own setpoint, so in Heat/cool the cooler can run while the heater waits.
- A fan or dryer that acts like a heater or a cooler (`fan_behavior`, `dryer_behavior`) waits too.
- A running device stops as soon as the water isn't ready; starting again still waits for `min_cycle_duration`.
- Without a water reading, nothing is held back.
- The thermostat shows `water_temperature`, `water_setpoint_heat`, `water_setpoint_cool` and `water_guard_active` as attributes.

### IR and RF devices that miss commands
Set `keep_alive` (for example 5 minutes) to repeat the current state regularly.

## Reporting an issue
1. Enable debug logging and reproduce the problem:
   ```yaml
   logger:
     logs:
       custom_components.dualmode_generic: debug
   ```
2. For thermostats set up in the UI, download diagnostics from the helper's menu.
3. [Open an issue](https://github.com/zacs/ha-dualmodegeneric/issues) with your configuration, the log and what you expected to happen.

## Translations
The setup and options screens are in English and Italian (thanks to @GiuseppeP96). To add a language, copy `custom_components/dualmode_generic/translations/en.json`, translate the text, and keep the keys and `{placeholders}` as they are. The tests check that.

## Development
Tests use [pytest-homeassistant-custom-component](https://github.com/MatthieuDartiailh/pytest-homeassistant-custom-component) and need Python 3.14:
```sh
python3.14 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest
ruff check . && ruff format --check .
```
The decision logic lives in `controller.py` and has no Home Assistant dependency.

Two test files track bugs:
- `tests/test_known_bugs.py` holds confirmed bugs as strict expected failures.
- `tests/test_regressions.py` keeps fixed ones from coming back.

## License
MIT. See [LICENSE](LICENSE).
