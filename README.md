# Home Assistant - Dual Mode Generic Thermostat with support for two away_temp variables

> Special thanks to [zacs](https://github.com/zacs/ha-dualmodegeneric) 

This component is a straightfoward fork of the mainline `dualmode_generic` thermostat by zacs that is himself a straightfoward fork of `generic_thermostat`.

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
    reverse_cycle: true
    away_temp_heater: 18 # optional but necessary if you want to have "away mode" available
    away_temp_cooler: 27 # optional but necessary if you want to have "away mode" available
```

The component shares the same configuration variables as the standard `generic_thermostat`, with three exceptions:
* A `cooler` variable has been added where you can specify the `entity_id` of your switch for a cooling unit (AC, fan, etc).
* If the cooling and heating unit are the same device (e.g. a reverse cycle air conditioner) setting `reverse_cycle` to `true` will ensure the device isn't switched off entirely when switching modes
* The `ac_mode` variable has been removed, since it makes no sense for this use case.

Refer to the [Generic Thermostat documentation](https://www.home-assistant.io/components/generic_thermostat/) for details on the rest of the variables. This component doesn't change their functionality.

## Behavior

* The thermostat will follow standard mode-based behavior: if set to "cool," the only switch which can be activated is the `cooler`. This means if the target temperature is higher than the actual temperateure, the `heater` will _not_ start. Vice versa is also true.

* Keepalive logic has been updated to be aware of the mode in current use, so should function as expected.

* By default, the component will restore the last state of the thermostat prior to a restart.

* While `heater`/`cooler` are documented to be `switch`es, they can also be `input_boolean`s if necessary.


## In case of any Issue
1. Setup your logger to print debug messages for this component using:
```yaml
logger:
  default: info
  logs:
    custom_components.dualmode_generic: debug
```
2. Restart HA
3. Verify you're still having the issue
