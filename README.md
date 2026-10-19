# Multi-Mode Generic Thermostat for Home Assistant

One thermostat for up to four separate devices: a **heater**, a **cooler**, a **fan** and a **dryer**. Each can be any switch-like entity: relays, smart plugs, template switches driving an IR blaster or another climate entity, groups, and so on. It began as a fork of Home Assistant's built-in [`generic_thermostat`](https://www.home-assistant.io/integrations/generic_thermostat/), which only drives a single device.

- Each device adds a mode: a heater adds Heat, a cooler adds Cool, a fan adds Fan only and a dryer adds Dry.
- A heater and a cooler together can also offer **Heat/cool**, which keeps the temperature within a range.
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
2. **How the devices work:** heat/cool mode, fan and dryer behavior, and reverse-cycle devices. This step only appears when it applies.
3. **Temperatures and timing:** tolerances, limits, minimum run time and keep-alive.
4. **Away and consent.**

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
| `target_temp` | – | Starting target, used until you set one. |
| `target_temp_low`, `target_temp_high` | – | Starting Heat/cool range. |
| `min_temp`, `max_temp` | 7 °C, 35 °C | Limits for the target. |
| `fan_behavior`, `dryer_behavior` | `neutral` | `neutral`: always on in its mode. `cooler`: runs when too warm. `heater`: runs when too cold. |
| `reverse_cycle` | – | Devices that are one unit switching modes, e.g. `heater, cooler`. See [Reverse-cycle air conditioners](#reverse-cycle-air-conditioners). |
| `min_cycle_duration` | – | Once a device switches on or off, it stays that way at least this long. |
| `keep_alive` | – | Repeat the current command this often, for devices that can lose state. |
| `initial_hvac_mode` | `off` | Mode on the very first start. Afterwards the last mode is restored. |
| `away_temp` | – | Target for the Away preset. Setting any away temperature adds the preset. |
| `away_temp_heater`, `away_temp_cooler` | – | Away targets for heating and cooling. In Heat/cool they set the low and high ends of the range. |
| `consent_entity` | – | While this entity isn't `on`, every device is kept off. |
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
- **Only the current mode's device is controlled.** A fan you run yourself keeps running while heat mode cycles the heater. Changing mode turns off devices that aren't part of the new mode.
- **Off leaves your devices alone.** Switching to off turns everything off once. After that, nothing is touched except to finish switching off a device that missed it, so you can run devices by hand.
- **Heater and cooler never run at the same time.** In Heat/cool, the system is idle between the two thresholds.
- **`min_cycle_duration` applies per device**, and takes effect as soon as it has passed. Changing the mode, target or preset overrides it, because that's you asking.
- **Without consent**, every device is turned off and the mode is kept. This applies in any mode.
- **Restarts restore everything:** mode, all targets, preset, and the mode `climate.turn_on` returns to.
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

### Continuous fan with a cycling compressor
Switch the fan on yourself (or with an automation) and use Cool mode. The compressor cycles while the fan keeps running.

### Schedules, windows and hydronic systems
Set `consent_entity` to a schedule, a calendar, an input boolean, or a sensor that's on when the boiler is ready. The thermostat keeps everything off whenever it isn't `on`. For a window sensor, which is on while the window is open, use a template binary sensor that inverts it.

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
