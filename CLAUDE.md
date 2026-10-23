# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a Home Assistant custom integration for Qilowatt - a platform for mFRR (manual Frequency Restoration Reserve) balancing market services. The integration connects Home Assistant-controlled energy systems to Qilowatt's cloud via MQTT, enabling participation in energy markets without physical Qilowatt hardware.

## Architecture

The integration follows the Home Assistant custom component structure under `custom_components/qilowatt/`:

- **Entry point**: `__init__.py` handles setup/teardown and forwards to sensor/binary_sensor platforms
- **MQTT communication**: `mqtt_client.py` wraps the `qilowatt` Python library to handle bidirectional MQTT communication with Qilowatt's servers
- **Inverter abstraction**: `inverter/` contains an adapter pattern where `base_inverter.py` defines the interface (`get_energy_data`, `get_metrics_data`) and specific implementations (Solarman, Huawei, Sofar, ESPHome, Victron, SolarAssistant) read data from their respective HA integrations
- **Config flow**: `config_flow.py` auto-discovers supported inverter integrations via the device registry
- **Sensors**: `sensor.py` exposes WORKMODE command fields (Mode, Source, PowerLimit, etc.) as HA sensors; `binary_sensor.py` exposes MQTT connection status

### qilowatt-py Library Integration

The `qilowatt` PyPI package (source: `../qilowatt-py/`) handles MQTT protocol details:

- **QilowattMQTTClient**: Manages connection to `mqtt.qilowatt.it:8883` (TLS), auto-reconnect, auth retries
- **InverterDevice**: Represents the device, manages MQTT topics (`Q/{device_id}/SENSOR`, `Q/{device_id}/cmnd/backlog`), and timer-based publishing
- **Data models** (`models.py`): `EnergyData` (grid power/voltage/current/frequency), `MetricsData` (PV, battery, load data), `WorkModeCommand` (mode, source, power limits)

### Data Flow

1. **Outbound to Qilowatt** (exactly every 10s): qilowatt-py's sensor timer calls `MQTTClient.read_inverter_data()` (registered via `InverterDevice.set_data_provider()`) right before each publish → HA inverter adapters read `hass.states` via `get_energy_data()`/`get_metrics_data()`, secondaries are aggregated → published to `Q/{id}/SENSOR`. The library owns the cadence; the integration has no timer of its own.
2. **Inbound from Qilowatt**: Commands arrive on `Q/{id}/cmnd/backlog` as `WORKMODE {...}` → `InverterDevice.handle_command()` parses to `WorkModeCommand` → callback dispatches to HA sensors via `async_dispatcher_send`

### WORKMODE Commands

Commands contain: `Mode` (normal/buy/sell/frrup/frrdown/etc), `_source` (timer/fusebox/optimizer/manual), `PowerLimit`, `BatterySoc`, `ChargeCurrent`, `DischargeCurrent`, etc. Users create HA automations that react to sensor changes (`sensor.qw_mode`, `sensor.qw_powerlimit`) to control their inverters.

## Adding a New Inverter Integration

1. Create a new file in `inverter/` extending `BaseInverter`
2. Implement `get_energy_data()` → return `EnergyData` dataclass with grid Power (list per phase), Voltage, Current, Frequency, Today/Total energy
3. Implement `get_metrics_data()` → return `MetricsData` dataclass with PV power/voltage/current, battery SOC/power/current/voltage/temperature, load power, inverter temperature
4. Register in `inverter/__init__.py` INVERTER_INTEGRATIONS dict
5. Add discovery logic in `config_flow.py._discover_inverters()` matching the device registry domain/identifier pattern

## Version Management

When releasing, update versions in:
- `manifest.json`: both `version` and `requirements` (qilowatt package version)
