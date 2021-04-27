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
    heater: switch.heater
    cooler: switch.cooler
    fan: switch.fan
    fan_behavior: cooler
    dryer: switch.dryer
    dryer_behavior: cooler
    target_sensor: sensor.temperature_sensor
    min_temp: 16
    max_temp: 30
    cold_tolerance: 0.8
    hot_tolerance: 0.4
    min_cycle_duration:
        minutes: 20
```

### Possible values for *_behavior
```yaml
fan_behavior: [cooler, neutral, heater] # <-- only one
dryer_behavior: [cooler, neutral, heater] # <-- only one
```

### Possible values for reverse_cylce
```yaml
reverse_cycle: cooler, heater, dryer, fan # <-- multiple are possible, (True/False) are still valid for backward compatibility
```

The component shares the same configuration variables as the standard `generic_thermostat`, with a few exceptions:
* A `cooler` variable has been added where you can specify the `entity_id` of your switch for a cooling unit (AC, fan, etc).
* A `fan` and `dryer` variable have been added where you can specify the `entity_id`s of your switches for a fan and/or dryer unit.
* I basically made all the `switches`/`input_booleans` optional, so the user can decide which modes he wants to use (my HVAC only supports `Cool`, `Dry`, `Fan_only`). This together with `template_switches` makes for a great way to make my HVAC controllable via IR.
* If the your climate unit offers multiple modes (e.g. a reverse cycle air conditioner) setting `reverse_cycle` to `cooler, heater` will ensure the device isn't switched off entirely when switching modes
* The `ac_mode` variable has been removed, since it makes no sense for this use case.

Refer to the [Generic Thermostat documentation](https://www.home-assistant.io/components/generic_thermostat/) for details on the rest of the variables. This component doesn't change their functionality.

## Behavior

* The thermostat will follow standard mode-based behavior: if set to "cool," the only switch which can be activated is the `cooler`. This means if the target temperature is higher than the actual temperateure, the `heater` will _not_ start. Vice versa is also true.

* Keepalive logic has been updated to be aware of the mode in current use, so should function as expected.

* By default, the component will restore the last state of the thermostat prior to a restart.

* While `heater`/`cooler`/`dryer`/`fan` are documented to be `switch`es, they can also be `input_boolean`s if necessary.


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
