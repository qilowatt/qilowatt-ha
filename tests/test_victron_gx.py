"""Tests for the VictronGXInverter adapter."""

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qilowatt.const import (
    CONF_DEVICE_ID,
    CONF_INVERTER_ID,
    CONF_INVERTER_MODEL,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_USERNAME,
    CONF_SECONDARY_DEVICE_IDS,
    DOMAIN,
)
from custom_components.qilowatt.inverter.victron_gx import VictronGXInverter


@pytest.fixture
def victron_gx_config_entry(hass):
    """A foreign config entry mimicking the victron_gx integration."""
    entry = MockConfigEntry(domain="victron_gx", data={})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def victron_gx_devices(hass, victron_gx_config_entry):
    """Create a realistic set of victron_gx devices for one installation."""
    dev_reg = dr.async_get(hass)
    system_device = dev_reg.async_get_or_create(
        config_entry_id=victron_gx_config_entry.entry_id,
        identifiers={("victron_gx", "d41243_system_0")},
        name="Victron System",
    )
    grid_device = dev_reg.async_get_or_create(
        config_entry_id=victron_gx_config_entry.entry_id,
        identifiers={("victron_gx", "d41243_grid_30")},
        name="Grid Meter",
    )
    battery_device = dev_reg.async_get_or_create(
        config_entry_id=victron_gx_config_entry.entry_id,
        identifiers={("victron_gx", "d41243_battery_256")},
        name="Battery",
    )
    charger_device = dev_reg.async_get_or_create(
        config_entry_id=victron_gx_config_entry.entry_id,
        identifiers={("victron_gx", "d41243_solarcharger_279")},
        name="Solar Charger",
    )
    return {
        "system": system_device,
        "grid": grid_device,
        "battery": battery_device,
        "charger": charger_device,
    }


def _register_entity(hass, device_id, object_id, domain="sensor"):
    ent_reg = er.async_get(hass)
    return ent_reg.async_get_or_create(
        domain, "victron_gx", object_id,
        suggested_object_id=object_id,
        device_id=device_id,
    )


def _populate_entities(hass, devices):
    """Register entities across victron_gx devices and set their states."""
    grid_dev = devices["grid"]
    bat_dev = devices["battery"]
    sys_dev = devices["system"]
    chg_dev = devices["charger"]

    grid_entities = {
        "grid_meter_grid_power_l1": "1500.0",
        "grid_meter_grid_power_l2": "800.0",
        "grid_meter_grid_power_l3": "300.0",
        "grid_meter_grid_voltage_l1": "230.5",
        "grid_meter_grid_voltage_l2": "231.0",
        "grid_meter_grid_voltage_l3": "229.8",
        "grid_meter_grid_current_l1": "6.5",
        "grid_meter_grid_current_l2": "3.5",
        "grid_meter_grid_current_l3": "1.3",
        "grid_meter_grid_frequency": "50.01",
        "grid_meter_grid_energy_forward": "12345.6",
    }
    for obj_id, value in grid_entities.items():
        _register_entity(hass, grid_dev.id, obj_id)
        hass.states.async_set(f"sensor.{obj_id}", value)

    bat_entities = {
        "battery_battery_soc": "85",
        "battery_battery_power": "-200.0",
        "battery_battery_current": "-4.2",
        "battery_battery_voltage": "48.1",
        "battery_battery_temperature": "24.5",
    }
    for obj_id, value in bat_entities.items():
        _register_entity(hass, bat_dev.id, obj_id)
        hass.states.async_set(f"sensor.{obj_id}", value)

    sys_entities = {
        "victron_system_system_dc_pv_power": "3200.0",
        "victron_system_system_dc_pv_current": "10.5",
        "victron_system_system_consumption_power_l1": "900.0",
        "victron_system_system_consumption_power_l2": "450.0",
        "victron_system_system_consumption_power_l3": "200.0",
    }
    for obj_id, value in sys_entities.items():
        _register_entity(hass, sys_dev.id, obj_id)
        hass.states.async_set(f"sensor.{obj_id}", value)

    chg_entities = {
        "solar_charger_solarcharger_voltage": "310.0",
    }
    for obj_id, value in chg_entities.items():
        _register_entity(hass, chg_dev.id, obj_id)
        hass.states.async_set(f"sensor.{obj_id}", value)


def _make_qw_entry(hass, device_id):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Victron GX",
        data={
            CONF_MQTT_USERNAME: "user",
            CONF_MQTT_PASSWORD: "pass",
            CONF_INVERTER_ID: "QW_VGX",
            CONF_DEVICE_ID: device_id,
            CONF_INVERTER_MODEL: "VictronGX",
            CONF_SECONDARY_DEVICE_IDS: [],
        },
        unique_id="QW_VGX",
        version=3,
    )
    entry.add_to_hass(hass)
    return entry


async def test_energy_data_from_grid_meter(hass, victron_gx_devices):
    _populate_entities(hass, victron_gx_devices)
    entry = _make_qw_entry(hass, victron_gx_devices["system"].id)
    inv = VictronGXInverter(hass, entry)

    energy = inv.get_energy_data()
    assert energy.Power == [1500.0, 800.0, 300.0]
    assert energy.Voltage == [230.5, 231.0, 229.8]
    assert energy.Current == [6.5, 3.5, 1.3]
    assert energy.Frequency == 50.01
    assert energy.Total == 12345.6
    assert energy.Today == 0.0


async def test_metrics_data_across_devices(hass, victron_gx_devices):
    _populate_entities(hass, victron_gx_devices)
    entry = _make_qw_entry(hass, victron_gx_devices["system"].id)
    inv = VictronGXInverter(hass, entry)

    metrics = inv.get_metrics_data()
    assert metrics.PvPower == [3200.0]
    assert metrics.PvVoltage == [310.0]
    assert metrics.PvCurrent == [10.5]
    assert metrics.LoadPower == [900.0, 450.0, 200.0]
    assert metrics.BatterySOC == [85]
    assert metrics.BatteryPower == [-200.0]
    assert metrics.BatteryCurrent == [-4.2]
    assert metrics.BatteryVoltage == [48.1]
    assert metrics.BatteryTemperature == [24.5]


async def test_any_device_in_installation_can_be_selected(hass, victron_gx_devices):
    """Selecting the battery device should still find grid and system entities."""
    _populate_entities(hass, victron_gx_devices)
    entry = _make_qw_entry(hass, victron_gx_devices["battery"].id)
    inv = VictronGXInverter(hass, entry)

    energy = inv.get_energy_data()
    assert energy.Power == [1500.0, 800.0, 300.0]
    assert energy.Voltage == [230.5, 231.0, 229.8]

    metrics = inv.get_metrics_data()
    assert metrics.BatterySOC == [85]
    assert metrics.PvPower == [3200.0]


async def test_availability_checks_cross_device_entities(hass, victron_gx_devices):
    _populate_entities(hass, victron_gx_devices)
    entry = _make_qw_entry(hass, victron_gx_devices["system"].id)
    inv = VictronGXInverter(hass, entry)

    assert inv.is_available()

    # Battery SOC unavailable → not available
    hass.states.async_set("sensor.battery_battery_soc", "unavailable")
    assert not inv.is_available()

    hass.states.async_set("sensor.battery_battery_soc", "80")
    assert inv.is_available()

    # Grid power unavailable → not available
    hass.states.async_set("sensor.grid_meter_grid_power_l1", "unavailable")
    assert not inv.is_available()

    # Restore grid power → available again
    hass.states.async_set("sensor.grid_meter_grid_power_l1", "1500.0")
    assert inv.is_available()

    # Grid voltage unavailable but grid power valid → still available
    # (voltage is not an essential measurement for publishing)
    hass.states.async_set("sensor.grid_meter_grid_voltage_l1", "unknown")
    assert inv.is_available()


async def test_system_level_fallback(hass, victron_gx_devices):
    """When device-level entities are missing, system-level ones are used."""
    sys_dev = victron_gx_devices["system"]
    entry = _make_qw_entry(hass, sys_dev.id)

    _register_entity(hass, sys_dev.id, "victron_system_system_grid_power_l1")
    hass.states.async_set("sensor.victron_system_system_grid_power_l1", "1000.0")
    _register_entity(hass, sys_dev.id, "victron_system_system_dc_battery_soc")
    hass.states.async_set("sensor.victron_system_system_dc_battery_soc", "72")
    _register_entity(hass, sys_dev.id, "victron_system_system_dc_battery_power")
    hass.states.async_set("sensor.victron_system_system_dc_battery_power", "500.0")

    inv = VictronGXInverter(hass, entry)
    energy = inv.get_energy_data()
    assert energy.Power[0] == 1000.0

    metrics = inv.get_metrics_data()
    assert metrics.BatterySOC == [72]
    assert metrics.BatteryPower == [500.0]


async def test_config_flow_discovers_victron_gx(hass, victron_gx_devices):
    """The config flow should discover one entry per installation, not per device."""
    from custom_components.qilowatt.config_flow import QilowattConfigFlow

    flow = QilowattConfigFlow()
    flow.hass = hass
    inverters = await flow._discover_inverters()

    gx_inverters = {
        did: inv for did, inv in inverters.items()
        if inv["inverter_integration"] == "VictronGX"
    }
    # All 4 devices share one config entry → only 1 entry in the list
    assert len(gx_inverters) == 1
    for inv in gx_inverters.values():
        assert inv["inverter_integration"] == "VictronGX"


async def test_config_flow_discovers_separate_installations(hass, victron_gx_config_entry):
    """Two installations (different config entries) should appear as two entries."""
    from custom_components.qilowatt.config_flow import QilowattConfigFlow

    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=victron_gx_config_entry.entry_id,
        identifiers={("victron_gx", "inst1_system")},
        name="Installation 1",
    )

    entry2 = MockConfigEntry(domain="victron_gx", data={})
    entry2.add_to_hass(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry2.entry_id,
        identifiers={("victron_gx", "inst2_system")},
        name="Installation 2",
    )

    flow = QilowattConfigFlow()
    flow.hass = hass
    inverters = await flow._discover_inverters()

    gx_inverters = {
        did: inv for did, inv in inverters.items()
        if inv["inverter_integration"] == "VictronGX"
    }
    assert len(gx_inverters) == 2
