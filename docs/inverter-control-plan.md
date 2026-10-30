# Implementation plan: optional direct inverter control

Status: plan, not implemented. Written 2026-10-30 after reading this repo, the
qilowatt-py 2026.10.7 sources and the control surface of every supported
inverter integration (section 5). Hand this file to the implementing session.

## 0. Decisions already made (do not re-open)

1. **Runtime toggle, not configuration.** Control is switched on and off with a
   switch entity, `switch.qw_inverter_control`, that lives on the Qilowatt
   device. Off by default, state restored across restarts, usable from
   dashboards and automations. The config flow is **not** changed and there is
   **no options flow**.
2. **All limits come from Qilowatt.** Every WORKMODE command carries the
   values the user configured on the Qilowatt side. The integration never
   asks for, stores, or invents a current or power limit. The hard-coded
   `# ADJUST` constants of `examples/deye-workmode-control/` are replaced by
   the command's fields (section 2). A value the inverter entity cannot
   accept is clamped to that entity's own `min`/`max` attributes and logged.
3. **Default off = no behaviour change.** With the switch off the integration
   does exactly what it does today. The examples stay as the manual
   alternative.
4. **Desired-state reconciler pattern** from the examples (full state per
   mode, re-sent every 10 s until the inverter reports it back) is kept.
5. **Victron stays read-only** (section 5.6).

## 1. Orientation in this repo

- `custom_components/qilowatt/mqtt_client.py` — `MQTTClient` wraps
  qilowatt-py. Commands arrive on the MQTT thread in `_on_command_received`
  and are forwarded with `async_dispatcher_send` on signal
  `qilowatt_workmode_update_<inverter_id>`; connection state on
  `qilowatt_connection_status_<inverter_id>`. The primary adapter is
  `self.inverter`, parallel units are `self.secondary_inverters`.
- `custom_components/qilowatt/inverter/*.py` — one read adapter per
  integration, all with `find_entity_state(suffix)` matching entity ids of
  the selected device by suffix (Huawei uses fixed ids instead).
  `AVAILABILITY_ENTITIES` drives `is_available()`.
- `custom_components/qilowatt/sensor.py` — `WORKMODE_SENSORS` exposes
  `Mode, _source, BatterySoc, PowerLimit, PeakShaving, MaxPower,
  ChargeCurrent, DischargeCurrent` as `sensor.qw_*`.
- `custom_components/qilowatt/binary_sensor.py` — `qw_connected`.
- `examples/deye-workmode-control/` — the automations this feature replaces;
  `README.md` there has the mode → Deye state table and the TOU precondition.
- Tests: `tests/` on pytest-homeassistant-custom-component; `conftest.py`
  has `solarman_device`, `config_entry`, `no_mqtt` fixtures.
  `tests/test_init.py` has `FakeQilowattClient`.
- CI: `.github/workflows/ci.yml` runs pytest, hassfest and HACS validation.
  Release: bump `manifest.json` `version`.

### WORKMODE command (qilowatt-py `models.py`, `WorkModeCommand`)

| Field | Unit | Meaning (qilowatt docs / node-red-hass README) |
|---|---|---|
| `Mode` | – | normal, buy, sell, frrup, frrdown, savebattery, pvsell, limitexport, nobattery |
| `_source` | – | timer, manual, optimizer, Q, fusebox, kratt (priority only; ignored for control) |
| `PowerLimit` | W | target grid power for buy/sell/frrup/frrdown/limitexport, always positive |
| `BatterySoc` | % | battery floor the mode should keep |
| `ChargeCurrent` | A | maximum battery charge current (user's Qilowatt device setting) |
| `DischargeCurrent` | A | maximum battery discharge current |
| `PeakShaving` | W | "maximum grid export allowance according to the agreement with the grid operator" (qilowatt.eu guide); 0 = none |
| `MaxPower` | W | inverter maximum power (Qilowatt "Inverter maximum power") |
| `MxByPw` | W | maximum buy (grid import) power — **undocumented, infer from name** |
| `MxSlPw` | W | maximum sell (grid export) power — **undocumented, infer from name** |

Unknown keys land in `command.extras`. All fields except `Mode` are
`Optional`; absent means "not configured on the Qilowatt side".

**First implementation task (section 6, step 0):** capture real WORKMODE
payloads for every mode from a live system at debug level and pin down the
semantics of `PeakShaving`, `MaxPower`, `MxByPw`, `MxSlPw` before writing
the limit logic. Record the findings in this file.

## 2. Limits derived from the command (`control/limits.py`)

```python
@dataclass(frozen=True)
class Limits:
    charge_current_a: int | None       # command.ChargeCurrent
    discharge_current_a: int | None    # command.DischargeCurrent
    max_export_w: int | None           # command.MxSlPw, else command.PeakShaving if > 0, else command.MaxPower
    max_import_w: int | None           # command.MxByPw, else command.MaxPower
    inverter_max_w: int | None         # command.MaxPower
    soc_floor: int | None              # command.BatterySoc

    @classmethod
    def from_command(cls, command: WorkModeCommand) -> "Limits": ...
```

Rules the controller enforces for every written value:

- A current written to any "max charge / max grid charge" register is
  `charge_current_a`; to "max discharge" is `discharge_current_a`. If the
  command has no value, use the target entity's `max` attribute and log a
  warning once ("Qilowatt sent no ChargeCurrent; using inverter maximum").
- `PowerLimit` is clamped: sell/frrup/limitexport → `min(PowerLimit,
  max_export_w)`; buy/frrdown → `min(PowerLimit, max_import_w)`.
- A "max sell power" written in normal/pvsell mode is `max_export_w`; the
  grid-import safety net in hold modes is `max_import_w`.
- A write is never above the entity's `max` or below its `min`; values are
  rounded to its `step`.
- The last command's limits are remembered so the failsafe (section 3.5)
  can build a plan after the connection is gone.

## 3. Architecture

```
qilowatt-py ──WORKMODE──▶ MQTTClient._on_command_received ──dispatcher──▶ WorkModeController
                                                                          │ enabled? (switch.qw_inverter_control)
                                                                          │ Intent ← intent_for(command)
                                                                          │ ControlPlan ← adapter.get_control_plan(intent, limits, share)
                                                                          │ reconcile every 10 s: compare, write diffs, 1 s apart
                                                                          ▼
                                                        inverter integration entities (select/number/switch/button/services)
```

### 3.1 Files

```
custom_components/qilowatt/
  control/
    __init__.py
    limits.py        # Limits.from_command (section 2)
    modes.py         # Intent, intent_for(command, current_soc)
    models.py        # Setting, ServiceStep, ControlPlan
    controller.py    # WorkModeController: enable/disable, reconcile loop, failsafe, diagnostics
  switch.py          # NEW platform: QilowattControlSwitch (the toggle)
  binary_sensor.py   # + QilowattControlInSyncSensor
  inverter/
    base_inverter.py # + SUPPORTS_CONTROL, find_entity_id(), select_option_for(), get_control_plan()
    deye_control.py  # DeyeControlMixin shared by solarman.py, solarassistant.py, esphome.py
    solarman.py, solarassistant.py, esphome.py, solarman_sofar.py, sofar.py, huawei.py  # plan() per adapter
  __init__.py        # PLATFORMS += Platform.SWITCH; create controller in async_setup_entry
  const.py           # DATA_CONTROLLER, signal names, RECONCILE_INTERVAL=10 s, WRITE_SPACING=1 s, FAILSAFE_MINUTES=15
  strings.json, translations/en.json  # entity names, repair issue texts
```

### 3.2 The switch (`switch.py`)

- `QilowattControlSwitch(SwitchEntity, RestoreEntity)`, `has_entity_name`,
  translation key `inverter_control`, `EntityCategory.CONFIG`, unique id
  `f"{inverter_id}_inverter_control"`, entity id `switch.qw_inverter_control`
  (same `async_generate_entity_id` pattern as the sensors), device info as
  the other entities.
- Created only when the primary adapter class has `SUPPORTS_CONTROL = True`
  **and** `adapter.control_supported()` returns True at setup (runtime
  probe; e.g. Sofar HYD-ES has no writable entities). Otherwise no switch
  and a one-line info log.
- `async_added_to_hass`: restore last state; if it was on, call
  `controller.async_enable()`. `async_turn_on/off` → controller
  `async_enable()/async_disable()`, then `async_write_ha_state`.
- `extra_state_attributes`: `last_command` (dict), `in_sync` (bool),
  `pending` (dict entity_id → desired), `unresolved_entities` (list).

### 3.3 Intent (`control/modes.py`)

Inverter-agnostic decision taken once, so every adapter behaves the same:

```python
@dataclass(frozen=True)
class Intent:
    kind: Literal["self_use", "sell", "grid_charge", "zero_export"]
    export_w: int | None      # grid export target/cap (sell, limitexport, self_use cap)
    import_w: int | None      # grid import target (grid_charge)
    soc_floor: int            # BatterySoc, or current SoC for hold modes
    allow_discharge: bool     # False for nobattery
```

| Mode | kind | export_w | import_w | soc_floor | allow_discharge |
|---|---|---|---|---|---|
| normal, unknown | self_use | `max_export_w` | – | BatterySoc (default 10) | yes |
| sell, frrup (PowerLimit ≥ 100) | sell | min(PowerLimit, max_export_w) | – | BatterySoc | yes |
| sell, frrup (PowerLimit < 100 or missing) | zero_export | 0 | – | BatterySoc | yes |
| buy, frrdown | grid_charge | 0 | max(min(PowerLimit, max_import_w), 100) | 100 | yes |
| savebattery | zero_export | 0 | – | current SoC | yes (floor = now, so none) |
| pvsell | self_use | `max_export_w` | – | current SoC | yes |
| limitexport (PowerLimit ≥ 1) | self_use | min(PowerLimit, max_export_w) | – | BatterySoc | yes |
| limitexport (0 / missing) | zero_export | 0 | – | BatterySoc | yes |
| nobattery | zero_export | 0 | – | current SoC | no |

The 100 W floors reproduce the example's Deye quirk ("Selling first" with max
sell 0 sells on one phase and buys on another).

### 3.4 Plan model (`control/models.py`)

```python
@dataclass(frozen=True)
class Setting:
    entity_id: str
    value: str | float | bool
    tolerance: float = 0.0          # numeric compare tolerance
    # service derived from domain: select→select_option, number→set_value,
    # switch→turn_on/turn_off, time→set_value

@dataclass(frozen=True)
class ServiceStep:                   # for integrations controlled by services/buttons
    domain: str; service: str; data: dict
    when: Literal["always", "after_change"]   # Sofar commit button = after_change
    confirm: Callable[[], bool] | None = None # e.g. Huawei forcible-charge sensor shows the power

@dataclass
class ControlPlan:
    settings: list[Setting]          # FULL state, ordered: mode first
    steps: list[ServiceStep] = field(default_factory=list)
    description: str = ""
```

### 3.5 Controller (`control/controller.py`)

- One per config entry, created in `async_setup_entry` next to the client,
  stored under `DATA_CONTROLLER`; always constructed, acts only while
  enabled.
- Subscribes to the dispatcher signals (no change to `mqtt_client.py`).
  Keeps `last_command`, `limits = Limits.from_command(command)` and the
  plans for primary + secondaries. `share = 1 / (1 + len(secondaries))`
  splits `export_w`/`import_w`; currents and SoC are not split.
- `async_enable()`: compute plans from `last_command` (if any), start the
  10-s `async_track_time_interval`, run one pass immediately.
  `async_disable()`: cancel timer, clear pending; the inverter keeps its
  last state (documented).
- Reconcile pass (guarded by `asyncio.Lock`, skipped if the previous pass is
  still running): for each Setting read `hass.states.get`; unavailable →
  skip and count; compare (string equality for select/switch, numeric with
  tolerance for number); on difference `await hass.services.async_call(...,
  blocking=True)` then `await asyncio.sleep(WRITE_SPACING)`. Then run
  `steps` (`after_change` ones only if something was written this pass or a
  `confirm` returns False). Errors per setting are caught and logged once
  per entity.
- Confirmation = the inverter entity reports the value back. After 6
  consecutive passes with the same mismatch create a repair issue
  (`inverter_rejects_setting`, placeholders entity_id/value); delete it when
  in sync. Unresolvable entities (plan returns None) → repair issue
  `control_entity_missing` listing the suffixes.
- Failsafe: on `connected=False` start `async_call_later(FAILSAFE_MINUTES*60)`;
  if still disconnected, apply the plan for `Mode="normal"` with the last
  known limits, create a persistent notification. Cancel on reconnect
  (Qilowatt re-sends WORKMODE on reconnect).
- Never write during shutdown: listen to `EVENT_HOMEASSISTANT_STOP` and
  disable; `async_unload_entry` disables before unloading platforms.
- Dispatches `qilowatt_control_status_<id>` after every pass so the switch
  attributes and `binary_sensor.qw_control_in_sync` update.

### 3.6 Adapter contract (`base_inverter.py`)

```python
class BaseInverter(ABC):
    SUPPORTS_CONTROL: bool = False

    def control_supported(self) -> bool:            # runtime probe, default = SUPPORTS_CONTROL
    def find_entity_id(self, suffix: str, domain: str) -> str | None:
        """Entity of this device whose id ends with suffix and starts with domain."""
    def select_option_for(self, entity_id: str, synonyms: set[str]) -> str | None:
        """Pick the live option (state.attributes['options']) whose casefold is in synonyms."""
    def current_soc(self) -> int | None             # from the adapter's SoC entity
    def get_control_plan(self, intent: Intent, limits: Limits, share: float) -> ControlPlan | None
```

**Never hard-code entity ids or option labels.** Ids depend on the device
name the user gave the inverter integration (ha-solarman defaults to
"Inverter" → `select.inverter_work_mode`; Solar Assistant single-inverter
installs give `select.work_mode`; solax_modbus renamed its ids in
v2025.08.1), and the same Deye register has different labels per
integration ("Export First" in ha-solarman, "Selling first" in Solar
Assistant and the ESPHome example). Where an integration has stable unique
ids (solax_modbus `f"{hub}_{key}"`, Huawei `f"{serial}_{register}"`), resolve
through the entity registry by unique-id suffix instead.

## 4. Mode → inverter state (shared Deye mixin)

Columns use the limit names of section 2. "max" means the command's value.

| Intent | work mode | solar sell | max sell W | grid charge (slot 6) | SoC floor | charge / grid-charge A | discharge A | peak shaving | peak shaving W |
|---|---|---|---|---|---|---|---|---|---|
| sell | Export/Selling first | on | `export_w` | off | `soc_floor` | `charge_current_a` | `discharge_current_a` | off | – |
| grid_charge | Zero export to CT | off | 0 | on | 100 | `charge_current_a` | `discharge_current_a` | on | `import_w` |
| zero_export | Zero export to CT | off | 0 | off | `soc_floor` | `charge_current_a` | `discharge_current_a` or 0 if not allow_discharge | on | `max_import_w` (safety net; omit setting if None) |
| self_use | Zero export to CT | on | `export_w` | off | `soc_floor` | `charge_current_a` | `discharge_current_a` | off | – |

Precondition verified once at enable time (repair issue if unmet, not fixed
automatically in v1): Time of Use enabled and program/time-point 1–6 start
times all 00:00 so slot 6 covers the whole day (see the example README).

## 5. Per-integration control surface (research, 2026-10-29)

### 5.1 Deye via ha-solarman (`Solarman` adapter) — Phase 1

Profiles `deye_p3.yaml` (3-phase SG04LP3/SG01HP3) and `deye_hybrid.yaml`
(1-phase) use identical entity names; `deye_sg04lp3.yaml` is a legacy alias.
Default ids below assume device name "Inverter"; match by suffix.

| Setting | Entity (suffix) | Register p3 / hybrid | Values |
|---|---|---|---|
| Work mode | `select.*_work_mode` | 142 / 244 | "Export First", "Zero Export To Load", "Zero Export To CT" |
| Solar sell | `switch.*_export_surplus` | 145 / 247 | |
| Max sell power | `number.*_export_surplus_power` | 143 / 245 | W, LV 0–24000, HV 0–80000 |
| Grid charge slot 6 | `select.*_program_6_charging` | 177 / 279 | "Disabled", "Grid", "Generator", "Both" (a select, not a switch) |
| SoC floor slot 6 | `number.*_program_6_soc` | 171 / 273 | 0–100 |
| Max charge current | `number.*_battery_max_charging_current` | 108 / 210 | A |
| Max discharge current | `number.*_battery_max_discharging_current` | 109 / 211 | A |
| Grid charge current | `number.*_battery_grid_charging_current` | 128 / 230 | A |
| Grid charge enable | `switch.*_battery_grid_charging` | 130 / 232 | |
| Grid peak shaving | `switch.*_grid_peak_shaving` | 178 bit 4 / 280 bit 8 | |
| Grid peak shaving power | `number.*_grid_peak_shaving` | 191 / 293 | W |
| Time of Use | `select.*_time_of_use` | 146 / 248 | "Enabled" ORs bit 0; day options overwrite |
| Program N start | `time.*_program_N_time` | 148–153 / 250–255 | precondition check only |

Option synonyms: sell = {"export first", "selling first"}, zero-CT = {"zero
export to ct"}, grid charge = {"grid", "grid charge", "on"}, none =
{"disabled", "no charge", "off"}.

### 5.2 Deye via Solar Assistant (`SolarAssistant` adapter) — Phase 2

MQTT discovery entities; SA must have *Allow setting changes* enabled
(Configuration → MQTT broker), otherwise every write is answered
`Rejected … updates not allowed` on `solar_assistant/set/response_message`
and nothing sticks (the in-sync sensor shows it). SA serialises writes;
~14 settings over serial take 20–30 s, so a full plan may need two passes.
Single-inverter ids are bare (`select.work_mode`), multi-inverter ids are
prefixed (`select.<model>_inverter_2_work_mode`); suffix matching covers both.

| Setting | Entity (suffix) | Values |
|---|---|---|
| Work mode | `select.*work_mode` | "Selling first", "Zero export to load", "Zero export to CT" |
| Solar sell | `switch.*solar_export_when_battery_full` | |
| Max sell power | `number.*max_sell_power` | W |
| Grid charge slot 6 | `switch.*grid_charge_point_6` | |
| SoC floor slot 6 | `number.*capacity_point_6` | % |
| Max charge / discharge / grid charge current | `number.*max_charge_current`, `number.*max_discharge_current`, `number.*max_grid_charge_current` | A |
| Grid charge enable | `switch.*grid_charge` | |
| Grid peak shaving / power | `switch.*grid_peak_shaving`, `number.*grid_peak_shaving_power` | |
| Timer enable | `switch.*use_timer` | precondition |

Unconfirmed in public dumps: per-slot power (`power_point_n`). Not needed.

### 5.3 Deye via ESPHome (`EspHome` adapter) — Phase 2

Names come from the user's YAML; ship the table matching
`examples/esphome-lilygo-tcan485.yaml` and surface unresolved suffixes in
the switch attributes so users with other YAML know what to rename.

| Setting | Entity (suffix) | Values |
|---|---|---|
| Work mode | `select.*_limit_control_mode` | "Selling first", "Zero export to load", "Zero export to CT" |
| Solar sell | `switch.*_solar_sell` | |
| Max sell power | `number.*_max_solar_sell_power` | |
| Grid charge slot 6 | `select.*_time_point_6_charge` | "No charge", "Grid charge", "Gen charge", "Grid and Gen charge" |
| SoC floor slot 6 | `number.*_time_point_6_capacity` | step 5 |
| Currents | `number.*_maximum_battery_charge_current`, `*_maximum_battery_discharge_current`, `*_maximum_battery_grid_charge_current` | |
| Grid charge enable | `switch.*_grid_charge` | |
| Grid peak shaving / power | `switch.*_grid_peak_shaving` (template over reg 178), `number.*_grid_peak_shaving_power` | |
| Time of Use | `switch.*_time_of_use` | precondition |

### 5.4 Sofar — Phase 3

**Via ha-solarman (`SolarmanSofar`)**, profiles `sofar_g3hyd.yaml` /
`sofar_g3.yaml`: plain entities, immediate write-back.
`select.*_storage_control_mode` ("Self Use", "Time of Use", "Optimized
Revenue", "Passive", "Peak Shaving", "Off-Grid", "Generator", "Export
Priority"), `number.*_passive_grid_power`, `number.*_passive_minimum_battery_power`,
`number.*_passive_maximum_battery_power` (each write rewrites the whole
0x1187–0x118C block), `select.*_export_surplus_limitation`
("Disabled"/"Enabled"/"Balanced"), `number.*_export_surplus_power`.
`sofar_hybrid.yaml` (HYD-ES) has no passive registers →
`control_supported()` False.

**Via SolaX Modbus (`Sofar`)**, `plugin_sofar.py` only (G3 units; HYD-ES uses
`plugin_sofar_old.py` with no write entities → unsupported at runtime):

| Key (unique id = `<hub>_<key>`) | Platform | Register | Notes |
|---|---|---|---|
| `charger_use_mode` | select | 0x1110 | "Self Use", "Time of Use", "Timing Mode", "Passive Mode", "Peak Cut Mode", … direct write, EEPROM-backed |
| `passive_mode_grid_power` | number | 0x1187 | W, **positive = import**; held locally 120 s only |
| `passive_mode_battery_power_min` / `_max` | number | 0x1189 / 0x118B | W, **positive = charge**; held locally 120 s |
| `passive_mode_battery_charge_discharge` | button | writes 0x1187–0x118C | the commit; must follow the numbers within 120 s |
| `passive_mode_timeout` / `_action` + `passive_mode_update_timeout` | select/button | 0x1184/0x1185 | set once at enable: 15 min, "Return to Previous Mode" |
| `feedin_limitation_mode`, `feedin_max_power` + `FeedIn: Update` button | select/number/button | 0x1023/0x1024 | export cap; EEPROM, change-only |

Sign note: the read adapter negates `active_power_pcc_*` (positive =
export there); passive registers are the opposite.

Intent → Sofar (both adapters):

| Intent | mode | grid power | bat min | bat max | feed-in limit |
|---|---|---|---|---|---|
| self_use | Self Use | – | – | – | `export_w` if < max_export_w else Disabled |
| sell | Passive | `−export_w` | `−export_w` | 0 | Disabled |
| grid_charge | Passive | `+import_w` | `+import_w` | `+inverter_max_w` | Enabled, 0 |
| zero_export | Passive | 0 | 0 | `+inverter_max_w` (0 if not allow_discharge and no PV charge wanted) | Enabled, 0 |

Sequence for solax_modbus: write mode → wait until the select reports
"Passive Mode" (numbers are ignored before, issue #1123) → numbers → commit
button → verify on next pass. The inverter may refuse discharge below ~30 %
SoC (issue #228); the 10-s retry handles it. Currents/SoC are not writable
on Sofar, so the controller itself enforces `soc_floor` by re-planning with
battery min 0 when SoC ≤ floor.

### 5.5 Huawei (`Huawei` adapter) — Phase 4

wlcrs/huawei_solar 2.1.5. Write entities and services exist only with the
*Advanced: elevate permissions* option of that integration;
`control_supported()` probes for the working-mode select (unique id suffix
`_storage_working_mode_settings`). Entity prefixes are inconsistent in
2.1.5 (`batteries_` vs `inverter_`), so resolve by unique-id suffix.

| Purpose | Entity / service |
|---|---|
| Mode | `select.*working_mode` options `maximise_self_consumption`, `fully_fed_to_grid`, `time_of_use_luna2000`, `adaptive`, `fixed_charge_discharge` |
| Force charge/discharge | `huawei_solar.forcible_charge` / `forcible_discharge` (`device_id` = Batteries device, `power` W, `duration` min); `stop_forcible_charge` |
| Charge from grid | `switch.*charge_from_grid`, `number.*grid_charge_cutoff_soc`, `number.*grid_charge_maximum_power` |
| Battery power caps | `number.*maximum_charging_power`, `number.*maximum_discharging_power` (W) |
| Export cap | `huawei_solar.set_maximum_feed_grid_power` (`device_id` = Inverter, `power` W), `set_zero_power_grid_connection`, `reset_maximum_feed_grid_power` |
| Readback | `sensor.*forcible_charge` ("Stopped" / "Charging at … W for … minutes") |

Intent → Huawei: self_use = mode `maximise_self_consumption`, stop forcing,
export cap `export_w`; sell = `forcible_discharge(min(export_w,
max_discharging_power), duration=15)` re-issued while the readback does not
show it; grid_charge = charge_from_grid on, cutoff SoC 100,
`forcible_charge(import_w, 15)` re-issued, zero-power grid connection;
zero_export = stop forcing, zero-power grid connection, discharging power 0
when not allow_discharge. Huawei has no grid setpoint, so `PowerLimit` is
met only approximately (battery-side control, as the example README warns);
Phase 5 closes the loop with the measured grid power the adapter already reads.
Convert Qilowatt currents to W with the battery voltage reading when a
Huawei power cap must honour `ChargeCurrent`/`DischargeCurrent`.

### 5.6 Victron — not supported

`mnuxx/victron_qw_addon` no longer exists on GitHub and nothing documents
writable entities for it; `SUPPORTS_CONTROL` stays False and no switch is
created. If wanted later, build on sfstar/hass-victron (write support
option): `number.victron_settings_ess_acpowersetpoint` (reg 2700, + =
import), `number.victron_settings_ess_maxdischargepower` (2704),
`number.victron_settings_ess_maxchargecurrent` (2705),
`number.victron_settings_ess_maxfeedinpower` (2706),
`number.victron_settings_ess_batterylife_minimumsoc` (2901),
`select.victron_settings_ess_mode` (only `EXTERNAL_CONTROL` reliable).
Reference behaviour: github.com/vahurm/cerbo-qilowatt-mfrr.

## 6. Work breakdown (one PR per phase, each with tests)

**Step 0 – verify the limit fields.** On a live install set
`custom_components.qilowatt: debug` and collect the WORKMODE JSON for
normal, buy, sell, frrup, frrdown, limitexport, savebattery, pvsell,
nobattery. Confirm what `PeakShaving`, `MaxPower`, `MxByPw`, `MxSlPw` carry and
update section 1 and `Limits.from_command`. Add the captured payloads as
test fixtures.

**Phase 1 – framework + switch + ha-solarman Deye**
1. `const.py`: `DATA_CONTROLLER`, intervals, signal name helper.
2. `control/limits.py`, `control/modes.py`, `control/models.py`,
   `control/controller.py`.
3. `base_inverter.py`: contract methods; `inverter/deye_control.py` mixin;
   wire into `SolarmanInverter` (`SUPPORTS_CONTROL = True`, suffix table,
   synonyms).
4. `switch.py` platform + `PLATFORMS` update in `__init__.py`; controller
   construction/teardown in `async_setup_entry` / `async_unload_entry`;
   `EVENT_HOMEASSISTANT_STOP` handling.
5. `binary_sensor.py`: `qw_control_in_sync`.
6. `strings.json` / `translations/en.json`: switch and binary sensor names,
   repair issues `inverter_rejects_setting`, `control_entity_missing`,
   `tou_precondition`.
7. README section "Let the integration control the inverter": what the
   switch does, that limits come from the Qilowatt device settings, disable
   your own reconciler automations first, turning it off leaves the inverter
   as is, which integrations are supported. CLAUDE.md: add the control
   package to the architecture notes.
8. `manifest.json` version bump.

**Phase 2 – Solar Assistant + ESPHome**: suffix tables and synonyms on the
shared mixin; SA "allow setting changes" note; ESPHome unresolved-entity
reporting.

**Phase 3 – Sofar**: `SolarmanSofar` plain plan; `Sofar` (solax_modbus) with
unique-id resolution, mode-wait, commit button, timeout setup, runtime
support probe; move the read adapter's `number.sofar_feedin_max_power`
lookup to the same resolver (id changed in v2025.08.1).

**Phase 4 – Huawei**: service-based plan with timed re-issue and
device-id lookup via device registry identifiers `(huawei_solar, "<serial>")`
and `(huawei_solar, "<serial>/connected_energy_storage")`.

**Phase 5 (optional) – closed loop**: per pass compare measured grid power
(already read for SENSOR) with the target and nudge the battery setpoint on
Sofar/Huawei.

## 7. Tests

- `tests/test_limits.py`: `Limits.from_command` on the captured payloads;
  missing fields → None; clamping and `step` rounding against entity
  attributes.
- `tests/test_modes.py`: table of section 3.3, every mode × PowerLimit
  (missing, 0, 50, 3000, above max_export_w) × BatterySoc.
- `tests/test_deye_plan.py`: registry entities for a Solarman device with
  ha-solarman names and labels; full `Setting` list per intent; synonym
  resolution; `share` split with one secondary; missing entity → None.
- `tests/test_controller.py`: states seeded in `hass.states`, fake
  `select.select_option` / `number.set_value` / `switch.turn_*` services
  recording calls and optionally updating state. Assert: only mismatches
  written; a write that does not stick is retried on the next tick
  (`async_fire_time_changed`); repair issue after 6 passes and cleared on
  sync; a command during a pass is applied next pass; nothing written while
  disabled, while the inverter is unavailable, or after
  `EVENT_HOMEASSISTANT_STOP`.
- `tests/test_switch.py`: switch absent for unsupported adapters; off by
  default; restored on restart and controller enabled accordingly; turning
  on with a stored command applies it immediately; turning off stops the
  timer and writes nothing more.
- `tests/test_failsafe.py`: connection off → after 15 min the normal plan
  with last limits is applied once; reconnect cancels.
- Per-adapter plan tests in later phases (Sofar commit sequence, Huawei
  service calls with the right `device_id`).

## 8. Risks and open points

- `MxByPw` / `MxSlPw` / `PeakShaving` / `MaxPower` semantics are inferred;
  Step 0 must confirm them. Until then `Limits.from_command` treats
  `PeakShaving` as an export cap per the qilowatt.eu guide text.
- Users who turn the switch on while their own reconciler automation still
  runs get two writers fighting; the README says to disable the automations
  and the in-sync sensor makes it visible.
- Turning the switch off leaves the inverter in its last commanded state.
- Deye Time-of-Use precondition is verified, not set.
- Sofar mode register is EEPROM-backed (~100k writes): the compare-before-
  write rule is what protects it; never write unconditionally.
- Huawei forcible charge is timed; the re-issue every pass is required.
