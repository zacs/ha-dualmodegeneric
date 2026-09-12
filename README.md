# Home Assistant - Dual Mode Generic Thermostat

> Special thanks to [shandoosheri](https://community.home-assistant.io/t/heat-cool-generic-thermostat/76443) for getting this to work on older versions of Home Assistant, which gave me an easy blueprint to follow. And thanks [@kevinvincent](https://github.com/kevinvincent) for writing a nice `custom_component` readme for me to fork.

This component is a straightfoward fork of the mainline `generic_thermostat`.

## Installation (HACS) - Recommended
0. Have [HACS](https://custom-components.github.io/hacs/installation/manual/) installed, this will allow you to easily update
1. Add `https://github.com/zacs/ha-dualmodegeneric` as a [custom repository](https://custom-components.github.io/hacs/usage/settings/#add-custom-repositories) as Type: Integration
2. Click install under "Dual Mode Generic Thermostat", restart your instance.

## Installation (Manual)
1. Download this repository as a ZIP (green button, top right) and unzip the archive
2. Copy `/custom_components/dualmode_generic` to your `<config_dir>/custom_components/` directory
   * You will need to create the `custom_components` folder if it does not exist
   * On Hassio the final location will be `/config/custom_components/dualmode_generic`
   * On Hassbian the final location will be `/home/homeassistant/.homeassistant/custom_components/dualmode_generic`

## Configuration
Add the following to your configuration file

### Example Config
```yaml
climate:
  - platform: dualmode_generic
    name: My Thermostat
    unique_id: climate.my_thermostat
    heater: switch.heater
    cooler: switch.cooler
    fan: switch.fan
    fan_behavior: cooler
    dryer: switch.dryer
    dryer_behavior: cooler
    target_sensor: sensor.temperature_sensor
    reverse_cycle: cooler, heater
    enable_heat_cool: True
    min_temp: 16
    max_temp: 30
    cold_tolerance: 0.8
    hot_tolerance: 0.4
    min_cycle_duration:
        minutes: 20
    consent_entity: calendar.schedule_time
    water_sensor: sensor.water_supply_temperature
    water_setpoint_heat: 30
    water_setpoint_cool: 15
    water_setpoint_heat_entity: input_number.water_setpoint_heat
    water_setpoint_cool_entity: input_number.water_setpoint_cool
    water_tolerance: 1.0
```

### Possible values for *_behavior
```yaml
fan_behavior: [cooler, neutral, heater] # <-- only one
dryer_behavior: [cooler, neutral, heater] # <-- only one
```

### Possible values for reverse_cycle
```yaml
reverse_cycle: cooler, heater, dryer, fan # <-- multiple are possible, (True/False) are still valid for backward compatibility
```

The component shares the same configuration variables as the standard `generic_thermostat`, with some exceptions:
* A `cooler` variable has been added where you can specify the `entity_id` of your switch for a cooling unit (AC, fan, etc).
* A `fan` and `dryer` variable have been added where you can specify the `entity_id`s of your switches for a fan and/or dryer unit.
* All the `switches`/`input_booleans` are optional, so the user can decide which modes he wants to use 
  (some HVAC only supports `Cool`, `Dry`, `Fan_only`). This together with `template_switches` makes for a great way to 
  make mobile HVACs controllable via IR.
* If the your climate unit offers multiple modes (e.g. a reverse cycle air conditioner) setting `reverse_cycle` to `cooler, heater` will ensure the device isn't switched off entirely when switching modes
* The `ac_mode` variable has been removed, since it makes no sense for this use case.
* `target_temp_high` and `target_temp_low` set the default value for the upper and lower setting for temperature range when in `HEAT_COOL` mode

Refer to the [Generic Thermostat documentation](https://www.home-assistant.io/components/generic_thermostat/) for details on the rest of the variables. This component doesn't change their functionality.

## Behavior

* For `HEAT` or `COOL` modes, the thermostat will follow standard mode-based behavior: if set to "cool," the only 
  switch which can be activated is the `cooler`. This means if the target temperature is higher than the actual 
  temperateure, the `heater` will _not_ start. Vice versa is also true.

* For `HEAT_COOL` mode, the thermostat will attempt to maintain the temperature within the set range, 
  turning on the configured heater when the temperature drops below the bottom of the range by `cold_tolerance` 
  and turning on the configured cooler when the temperature rises above the top of the set range by the `hot_tolerance` 
  amount. When the measured temperature is within the configured range by `(hot|cold)_tolerance` the thermostat will 
  transition to idle mode and both heater and cooler will be turned off.
    * __This mode needs to be enabled explicitly by setting `enable_heat_cool` to `True`!__
    * __Be careful with `min_cycle_duration`! If you set it too high, your AC will bounce between too hot and too cold 
      when using `heat_cool`!__

* Keepalive logic has been updated to be aware of the mode in current use, so should function as expected.

* By default, the component will restore the last state of the thermostat prior to a restart.

* While `heater`/`cooler`/`dryer`/`fan` are documented to be `switch`es, they can also be `input_boolean`s 
  if necessary. Note that these are assumed to be exclusively for the use of the thermostat - 
  the thermostat will report its mode and change its behaviour based on the position of these switches.

* `consent_entity`is an optional entity (e.g., `binary_sensor`, `input_boolean`, or `calendar`) that acts as an additional control for the thermostat. When the entity is in the "on" state (or equivalent, such as `true` for calendars), the thermostat operates normally. When the entity is "off" or unavailable, all devices controlled by the thermostat (heater, cooler, dryer, fan) are turned off, but the thermostat retains its previous HVAC mode setting ("keep previous mode"). This allows you to schedule thermostat operation using calendar entities or other logic, without needing separate automations.

## Tamper Entity

`tamper_entity` is an optional entity (e.g. `binary_sensor`, `input_boolean`) that acts as an **inverse consent** control. When the tamper entity is **ON**, the thermostat is forced inactive: all controlled devices (heater, cooler, fan, dryer) are turned off while the previously selected HVAC mode is retained. When the tamper clears (**OFF** or unavailable), normal control resumes.

This is a layer that adds to `consent_entity`, the water guard and `min_cycle_duration` — it does not replace any of them. Use it as a safety interlock (e.g. an open-window or tamper sensor that must stop the thermostat).

## Command Panel (Physical Climate Device)

`command_climate` lets you drive the thermostat from a **physical climate device used purely as a command panel** — for example a Sonoff TP-WGZBA or a boiler thermostat with a dry contact. The device's own relay does not need to be wired to anything; the actuation stays with the `heater`/`cooler` switches. The physical device is used only as an **input**:

* Its `system_mode` acts as an additional consent (it does **not** change the thermostat's HVAC mode):
    * `off` → the thermostat goes **inactive** (all devices off), but keeps the HVAC mode you selected on the dual mode thermostat
    * non-off (`heat` / `auto`) → normal control resumes
* Its setpoint is read and applied as the target temperature, **clamped** into the configured limits:
    * in `HEAT` mode → clamped between `min_heat_temp` and `max_heat_temp`
    * in `COOL` mode → clamped between `min_cool_temp` and `max_cool_temp`
    * if a mode-specific limit is unset, it falls back to the global `min_temp` / `max_temp`
    * a value outside the range is forced to the nearest limit
* `running_state` is **ignored** (the relay is not used)
* If the physical device becomes unavailable, it is **ignored** — the thermostat keeps its last state and continues to work from the Home Assistant UI

The heat/cool clamp limits are optional and additive (fully backward compatible):

| Key | Description |
|---|---|
| `min_heat_temp` | Lower clamp for the setpoint synced from the command panel in HEAT mode |
| `max_heat_temp` | Upper clamp for the setpoint synced from the command panel in HEAT mode |
| `min_cool_temp` | Lower clamp for the setpoint synced from the command panel in COOL mode |
| `max_cool_temp` | Upper clamp for the setpoint synced from the command panel in COOL mode |

The mode choice (heat vs cool) always stays on the dual mode thermostat — the physical panel only provides on/off and a setpoint.

### Temperature source

When `command_climate` is configured, its own temperature reading (the climate entity's `current_temperature`, e.g. the device `local_temperature`) is used as the room temperature — so **`target_sensor` becomes optional**. If you configure `target_sensor` as well, it **takes priority** (useful if you want to average the panel reading with another sensor via a template/statistics sensor). At least one of `target_sensor` or `command_climate` must be configured.

### Example Config

```yaml
climate:
  - platform: dualmode_generic
    name: Living Room
    heater: switch.heating_valve
    cooler: switch.cooling_valve
    target_sensor: sensor.room_temperature
    enable_heat_cool: True
    tamper_entity: binary_sensor.window_open
    command_climate: climate.wall_panel
    min_heat_temp: 16
    max_heat_temp: 24
    min_cool_temp: 20
    max_cool_temp: 28
```

## Water Temperature Guard

The thermostat supports an optional **water supply temperature guard** that prevents the heater or cooler from activating unless the water circuit has reached the required temperature. This is useful for hydronic systems (e.g., radiant floor heating, fan coils) where the equipment should only run when the boiler or chiller has prepared the water.

### Configuration

| Key | Required | Description |
|---|---|---|
| `water_sensor` | Yes (to enable guard) | Entity ID of the sensor measuring the water supply temperature |
| `water_setpoint_heat` | Optional | Fixed water temperature threshold for heating (float, °C or °F). The heater starts only when water temp ≥ this value |
| `water_setpoint_cool` | Optional | Fixed water temperature threshold for cooling (float, °C or °F). The cooler starts only when water temp ≤ this value |
| `water_setpoint_heat_entity` | Optional | Entity whose state provides the heating threshold dynamically (e.g. `input_number`) — takes priority over `water_setpoint_heat` |
| `water_setpoint_cool_entity` | Optional | Entity whose state provides the cooling threshold dynamically (e.g. `input_number`) — takes priority over `water_setpoint_cool` |
| `water_tolerance` | Optional (default: `0.3`) | Dead-band tolerance applied to the water setpoint checks |

At least one setpoint (fixed or entity) must be provided for the relevant mode together with `water_sensor` for the guard to function. If no setpoint is configured for a specific mode, the guard is satisfied and operation proceeds normally for that mode.

### Behavior

* **Heating mode** (`heat`, `fan_only` with `fan_behavior: heater`, `dry` with `dryer_behavior: heater`): the device starts only when `water_temp >= water_setpoint_heat - tolerance`. Example: `water_setpoint_heat: 30` with `water_tolerance: 1` → the heater runs when the water supply reaches at least 29°C (`30 - 1`). If the water is not hot enough, all devices are turned off and the action reports `idle`.
* **Cooling mode** (`cool`, `fan_only` with `fan_behavior: cooler`, `dry` with `dryer_behavior: cooler`): the device starts only when `water_temp <= water_setpoint_cool + tolerance`. Example: `water_setpoint_cool: 15` with `water_tolerance: 1` → the cooler runs when the water supply is at most 16°C (`15 + 1`). If the water is not cold enough, all devices are turned off and the action reports `idle`.
* **`HEAT_COOL` mode**: the guard is applied independently per device. The heater will not start if the water is not hot enough (checked against `water_setpoint_heat`), and the cooler will not start if the water is not cold enough (checked against `water_setpoint_cool`). The two can operate independently.
* When the water temperature crosses the threshold (because of a sensor update or a setpoint entity change), `_async_control_heating` is triggered automatically — the device will start or stop without any additional automation needed.

### Additional State Attributes

When `water_sensor` is configured, the following attributes are added to the thermostat entity:

| Attribute | Description |
|---|---|
| `water_temperature` | Current water supply temperature from the sensor |
| `water_setpoint_heat` | The active heating setpoint (entity value if configured, otherwise fixed value) |
| `water_setpoint_cool` | The active cooling setpoint (entity value if configured, otherwise fixed value) |
| `water_guard_active` | `true` when the guard is blocking operation |

### Example Config

```yaml
climate:
  - platform: dualmode_generic
    name: Floor Heating & Cooling
    heater: switch.floor_heating_valve
    cooler: switch.floor_cooling_valve
    target_sensor: sensor.room_temperature
    enable_heat_cool: True
    water_sensor: sensor.water_supply_temp
    water_setpoint_heat: 30
    water_setpoint_cool: 15
    water_setpoint_heat_entity: input_number.water_setpoint_winter
    water_setpoint_cool_entity: input_number.water_setpoint_summer
    water_tolerance: 1.5
```


## Reporting an Issue
1. Setup your logger to print debug messages for this component using:
```yaml
logger:
  default: info
  logs:
    custom_components.dualmode_generic: debug
```
2. Restart HA
3. Verify you're still having the issue
4. File an issue in this Github Repository containing your HA log (Developer section > Info > Load Full Home Assistant Log)
   * You can paste your log file at pastebin https://pastebin.com/ and submit a link.
   * Please include details about your setup (Pi, NUC, etc, docker?, HASSOS?)
   * The log file can also be found at `/<config_dir>/home-assistant.log`
