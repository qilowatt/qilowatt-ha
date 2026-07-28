# Sample WORKMODE automations for a Deye hybrid inverter

This is a complete, working example of how to act on Qilowatt WORKMODE commands with a
Deye hybrid inverter, using only this integration — no external optimizer (EMHASS etc.)
is required. It is based on a real production setup that has been running on the mFRR
market with Deye inverters.

The example implements the community-recommended **"desired state" pattern** described in
the main README:

```
Qilowatt cloud
   │  (MQTT)
   ▼
sensor.qw_mode / sensor.qw_powerlimit / sensor.qw_batterysoc
   │
   ▼
[1] qw-mode-dispatch.yaml      — one automation, one branch per mode
   │      calls one of the scripts below, which write the FULL desired
   ▼      inverter state into helpers
[2] scripts.yaml + helpers.yaml — desired-state helpers (input_select / input_number / input_boolean)
   │
   ▼
[3] desired-state-reconciler.yaml — every 10 s, compares each helper to the
   │      real inverter entity and re-sends the register until it sticks
   ▼
Deye inverter (via ha-solarman / Solar Assistant / ESPHome / …)
```

Why this shape:

- **Writes are retried until confirmed.** Modbus/dongle writes to a Deye get lost
  regularly. The dispatch automation never touches the inverter directly — it only sets
  helpers. The reconciler keeps re-sending each setting until the inverter reports it
  back, so a lost write costs you 10 seconds, not a whole mFRR activation.
- **Every branch applies the *full* state.** Each script sets every register the pattern
  manages, so the inverter never keeps a stale setting from the previous mode.
- **Source-agnostic.** There are no `sensor.qw_source` branches: `manual`, `timer`,
  `optimizer`, `Q` and `fusebox`/`kratt` commands all flow through the same mode logic.
  The source only tells you *who* issued the command, not what to do differently.

## Files

| File | Contents |
|------|----------|
| `helpers.yaml` | Desired-state helpers (HA package: `input_select`, `input_number`, `input_boolean`) |
| `scripts.yaml` | One script per target inverter state (`sell`, `grid charge`, `zero export`, `self-use`) |
| `qw-mode-dispatch.yaml` | Automation 1: `sensor.qw_mode`/`qw_powerlimit` → scripts → helpers |
| `desired-state-reconciler.yaml` | Automation 2: helpers → inverter registers (retry loop) |
| `qw-watchdog.yaml` | Failsafe: revert to self-use if the Qilowatt connection drops; optional push notification on mode changes |

## Installation

1. Copy the files somewhere under your HA config (e.g. a `qilowatt/` directory, with the
   three automation files in `qilowatt/automations/`) and include them:

   ```yaml
   # configuration.yaml
   homeassistant:
     packages:
       qilowatt_helpers: !include qilowatt/helpers.yaml
   script qilowatt: !include qilowatt/scripts.yaml
   automation qilowatt: !include_dir_merge_list qilowatt/automations/
   ```

   (Or paste the automations/scripts into the UI editors — the YAML is standard.)

2. **Replace the inverter entity ids.** All inverter-side entities use placeholder names
   (`select.deye_work_mode`, `number.deye_max_solar_sell_power`, …). Map them to
   whatever your integration exposes:
   - **ha-solarman / Solar Assistant**: `select.work_mode`, `number.max_discharge_current`,
     `number.capacity_point_6`, `switch.grid_charge_point_6`, …
   - **ESPHome** (see [`../esphome-lilygo-tcan485.yaml`](../esphome-lilygo-tcan485.yaml)):
     `select.deye_limit_control_mode`, `number.deye_max_solar_sell_power`, …
3. **Check the constants** marked `# ADJUST` — max charge/discharge current, max
   sell power and max import power must match *your* inverter rating and grid connection.
4. **Time-of-Use setup on the Deye:** enable Time-of-Use and set the start time of
   **every** time point (1–6) to `00:00`. With all times at zero, points 1–5 each cover a
   zero-length window and time point 6 is the only active slot for the whole day — so
   only time point 6's *capacity* and *grid charge* settings ever need to be controlled,
   which is what this example's helpers map to. If you keep a real multi-slot TOU
   schedule instead, extend the scripts/reconciler to write all active slots.

## Mode → Deye state mapping

All modes are handled. The Qilowatt timer/manual UI lets you pick six modes — `normal`,
`sell`, `buy`, `savebattery`, `limitexport`, `pvsell` — together with an optional power
(W → `sensor.qw_powerlimit`, always positive) and SOC (% → `sensor.qw_batterysoc`, used
below as the battery capacity floor). `frrup`/`frrdown` are not user-selectable: they are
issued by mFRR market activations (`fusebox`/`kratt` source) and must always be obeyed.
`nobattery` exists in the WORKMODE API and is handled for completeness.

| `sensor.qw_mode` | Deye state applied |
|---|---|
| `normal` | Self-use: *Zero export to CT* + Solar Sell on. PV → load → battery, excess exported, battery floor = `sensor.qw_batterysoc`. |
| `sell`, `frrup` | *Selling first*, `max_solar_sell_power = PowerLimit`, battery discharge opened to max. |
| `sell`/`frrup` at **0 W** | Zero-export hold instead. (Quirk: *Selling first* with max sell power 0 makes a Deye sell on one phase while buying on another.) |
| `buy`, `frrdown` | *Zero export to CT* + grid charge on + battery target 100 % + charge currents max; grid import capped via **Grid Peak Shaving** = `PowerLimit`. |
| `savebattery` | Zero-export hold with battery floor = *current* SoC → battery neither sells nor discharges; grid covers the deficit. |
| `pvsell` | *Selling first* with battery floor = current SoC → PV surplus is exported but the battery is untouched. |
| `limitexport` | Self-use with `max_solar_sell_power = PowerLimit`; at 0 W falls back to zero-export hold. |
| `nobattery` | Zero-export hold with discharge current 0 and battery floor = current SoC. |

## FRR modes on other inverters

`frrup`/`frrdown` handling is inverter-specific. A **Deye controls the grid side**: you
set the maximum grid sell power (`frrup`) or the Grid Peak Shaving import limit
(`frrdown`) to `PowerLimit`, open the battery current limits to maximum, and the inverter
itself regulates battery power so that the grid connection hits the target regardless of
what the house load or PV does.

**Inverters without grid-side setpoints must control the battery instead**: compute the
battery charge/discharge power needed to reach `PowerLimit` at the grid connection
(roughly `battery power = PowerLimit ± house load ∓ PV production`) and keep adjusting it
in a feedback loop, since load and PV change during the activation. The
`ChargeCurrent`/`DischargeCurrent` fields of the WORKMODE command
(`sensor.qw_chargecurrent` / `sensor.qw_dischargecurrent`) can be used as starting
values. No worked example of battery-side control is provided here.

## Multiple inverters

If two or more inverters share one grid connection, split the power setpoints between
them (e.g. write `PowerLimit / 2` W to each inverter's max-sell / peak-shaving register)
and duplicate the reconciler per inverter. The referenced production setup runs two Deye
20 kW units exactly this way.

## Using an external optimizer (EMHASS etc.) as well

This example assumes Qilowatt is the only thing steering the inverter. If you also run a
local optimizer such as EMHASS, keep these automations as-is for all non-`normal` modes
(mFRR commands must always win) and, in the `normal` branch, instead of applying the
self-use script, hand control back to your optimizer (e.g. turn an
`input_boolean.optimizer_enabled` on and let your optimizer's own automation drive the
same desired-state helpers). That is how the production setup this example is based on
combines Qilowatt with EMHASS.
