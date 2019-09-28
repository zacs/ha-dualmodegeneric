# Home Assistant - Dual Mode Generic Thermostat

> Special thanks to [shandoosheri](https://community.home-assistant.io/t/heat-cool-generic-thermostat/76443) for getting this to work on older versions of Home Assistant, which gave me an easy blueprint to follow.

This component is a straightfoward fork of the mainline `generic_thermostat`. 

## Installation (HACS) - Highly Recommended
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

```yaml
climate:
  - platform: dualmode_generic
    name: My Thermostat
    heater: switch.heater
    cooler: switch.fan
    target_sensor: sensor.my_temp_sensor
```

The component shares the same configuration variables as the standard `generic_thermostat`, with two exceptions:
* A `cooler` variable has been added where you can specify the `entity_id` of your switch for a cooling unit (AC, fan, etc).
* The `ac_mode` variable has been removed, since it makes no sense for this use case. 

Refer to the [Generic Thermostat documentation](https://www.home-assistant.io/components/generic_thermostat/) for details on the rest of the variables. This component doesn't change their functionality.

By default, the component will restore the last state of the thermostat prior to a restart. 

## Behavior

* The thermostat will follow standard mode-based behavior: if set to "cool," the only switch which can be activated is the `cooler`. This means if the target temperature is higher than the actual temperateure, the `heater` will _not_ start. Vice versa is also true. 

* Keepalive logic has been updated to be aware of the mode in current use, so should function as expected. 

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