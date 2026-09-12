## Summary

This PR introduces several features to the Multi-Mode Generic Thermostat:

1. **Water Temperature Guard** — prevents heating/cooling devices from activating unless the water supply has reached the required temperature.
2. **Tamper Entity** — an inverse-consent entity that forces the thermostat inactive while keeping its mode.
3. **Command Panel (physical climate device)** — drive the thermostat on/off + setpoint from a physical climate device (e.g. Sonoff TP-WGZBA) used purely as an input.
4. **Config Flow + Options Flow** — full UI-based setup and configuration editing, removing the need to use YAML.

All features are fully backward-compatible with existing YAML-based configurations.

---

## Water Temperature Guard

Hydronic HVAC systems (radiant floors, fan coils, etc.) should not operate unless the water supply is at the appropriate temperature — running a heating valve when the boiler hasn't warmed the water wastes energy and provides no comfort benefit.

This feature adds two independent setpoints:

- `water_setpoint_heat`: heater activates only when `water_temp >= setpoint - tolerance` (water is hot enough)
- `water_setpoint_cool`: cooler activates only when `water_temp <= setpoint + tolerance` (water is cold enough)

Both setpoints support a fixed YAML value and/or a dynamic entity (`input_number`, `sensor`, etc.) for runtime adjustability. The entity value takes priority when configured.

### Configuration options added

| Key | Description |
|---|---|
| `water_sensor` | Entity ID of the water supply temperature sensor |
| `water_setpoint_heat` | Fixed threshold for heating mode |
| `water_setpoint_cool` | Fixed threshold for cooling mode |
| `water_setpoint_heat_entity` | Dynamic entity for heating threshold |
| `water_setpoint_cool_entity` | Dynamic entity for cooling threshold |
| `water_tolerance` | Dead-band tolerance (default: 0.3) |

### Behavior

- In `HEAT_COOL` mode, the guard is evaluated independently for each device
- When the guard blocks operation, `hvac_action` reports `idle`
- Extra state attributes are exposed: `water_temperature`, `water_setpoint_heat`, `water_setpoint_cool`, `water_guard_active`
- When the water temperature crosses the threshold, control logic is triggered automatically — no external automation needed

---

## Tamper Entity

`tamper_entity` is an optional entity (e.g. `binary_sensor`, `input_boolean`) that acts as an **inverse consent** control — the mirror of the existing `consent_entity`.

- When the tamper entity is **ON** → the thermostat is forced inactive (all controlled devices turned off), while the previously selected HVAC mode is retained
- When the tamper clears (**OFF** or unavailable) → normal control resumes

It is a layer that adds to `consent_entity`, the water guard, and `min_cycle_duration` — it does not replace any of them. Useful as a safety interlock (e.g. an open-window or tamper sensor).

---

## Command Panel (Physical Climate Device)

`command_climate` lets you drive the thermostat from a **physical climate device used purely as a command panel** — for example a Sonoff TP-WGZBA or a boiler thermostat with a dry contact. The device's own relay does not need to be wired to anything; actuation stays with the `heater`/`cooler` switches. The physical device is used only as an **input**:

- Its `system_mode` acts as an additional consent (it does **not** change the thermostat's HVAC mode):
    - `off` → the thermostat goes **inactive** (all devices off) while keeping the HVAC mode selected on the dual mode thermostat
    - non-off (`heat` / `auto`) → normal control resumes
- Its setpoint is read and applied as the target temperature, **clamped** into the configured limits:
    - in `HEAT` mode → clamped between `min_heat_temp` and `max_heat_temp`
    - in `COOL` mode → clamped between `min_cool_temp` and `max_cool_temp`
    - falls back to the global `min_temp` / `max_temp` when a mode-specific limit is unset
    - values outside the range are forced to the nearest limit
- `running_state` is **ignored** (the relay is not used)
- If the physical device becomes unavailable, it is **ignored** — the thermostat keeps its last state and continues to work from the Home Assistant UI

The mode choice (heat vs cool) always stays on the dual mode thermostat — the physical panel only provides on/off and a setpoint.

When `command_climate` is configured, its own temperature reading (the climate entity's `current_temperature`) is used as the room temperature, so **`target_sensor` becomes optional**. If `target_sensor` is also configured, it takes priority (allowing e.g. averaging the panel reading with another sensor). At least one of `target_sensor` or `command_climate` must be configured. `target_sensor` was changed from required to optional accordingly.

### Optional heat/cool clamp limits (additive, backward compatible)

| Key | Description |
|---|---|
| `min_heat_temp` | Lower clamp for the setpoint synced from the command panel in HEAT mode |
| `max_heat_temp` | Upper clamp for the setpoint synced from the command panel in HEAT mode |
| `min_cool_temp` | Lower clamp for the setpoint synced from the command panel in COOL mode |
| `max_cool_temp` | Upper clamp for the setpoint synced from the command panel in COOL mode |

---

## Config Flow (UI-based setup)

Users can now configure the thermostat entirely from the Home Assistant UI:

**Settings → Devices & Services → Add Integration → Multi-Mode Generic Thermostat**

The setup wizard is structured in 5 sequential steps:

1. **Base** — name, temperature sensor (optional), humidity sensor
2. **Devices** — heater, cooler, fan, dryer, behaviors, reverse cycle, heat_cool mode
3. **Temperature & Control** — targets, min/max, heat/cool clamp limits, tolerances, precision, step
4. **Timing & Modes** — min cycle duration, keep-alive, initial mode, away temps, consent entity, tamper entity, command panel
5. **Water Guard** — water sensor, setpoints (heat/cool), setpoint entities, tolerance

The `unique_id` is auto-generated (UUID4) at creation time.

---

## Options Flow (runtime editing)

After creation, all parameters can be modified from the UI without restarting Home Assistant:

**Integration card → Configure**

A menu allows editing by category:
- Devices
- Temperature & Control
- Timing & Modes
- Water Temperature Guard

Changes are applied immediately via entry reload.

---

## Guard precedence

The thermostat evaluates the following independent, cumulative gates before actuating any device (in `_async_control_heating` and `hvac_action`):

1. `consent_entity` (OFF → inactive)
2. `tamper_entity` (ON → inactive)
3. `command_climate` (system_mode off → inactive)
4. Water temperature guard

`min_cycle_duration` applies on top of all of them.

---

## Files changed

| File | Change |
|---|---|
| `climate.py` | Water guard logic, tamper entity, command-panel climate input, heat/cool clamp limits, `async_setup_entry` for config entries |
| `__init__.py` | Rewritten to support both YAML and config entry setup |
| `config_flow.py` | **New** — Config Flow (5 steps) + Options Flow (menu-based) |
| `manifest.json` | Added `config_flow: true`, bumped version to 0.3.0 |
| `strings.json` | **New** — English UI labels |
| `translations/en.json` | **New** — English translations |
| `translations/it.json` | **New** — Italian translations |
| `README.md` | Documented water guard, tamper entity and command panel with examples |

---

## Backward compatibility

- Existing YAML configurations continue to work without any changes
- The legacy `async_setup_platform` path is fully preserved
- All new options are optional; when unset, behavior is identical to before
- No breaking changes to existing behavior

---

## Testing

- Verified water guard activation/deactivation based on water temperature thresholds
- Verified `min_cycle_duration` interaction (guard check is respected, `force=True` bypasses cycle duration as expected)
- Verified tamper entity forces the thermostat inactive and resumes on clear, without changing the HVAC mode
- Verified command panel on/off drives inactive/active as consent and syncs the clamped setpoint
- Verified command panel is ignored when unavailable (thermostat keeps working via UI)
- Verified Config Flow creates working entities with auto-generated unique IDs
- Verified Options Flow correctly merges changes and reloads the entry
