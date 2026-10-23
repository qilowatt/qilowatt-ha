"""The library pulls inverter data through MQTTClient.read_inverter_data."""

from unittest.mock import patch

from homeassistant.helpers import entity_registry as er
from qilowatt import EnergyData, MetricsData

from custom_components.qilowatt.const import DATA_CLIENT, DOMAIN
from custom_components.qilowatt.mqtt_client import MQTTClient

from .test_init import FakeQilowattClient


def _energy(power, today=1.0):
    return EnergyData(Power=list(power), Today=today, Total=0.0, Current=[1.0, 1.0, 1.0],
                      Voltage=[230.0, 231.0, 232.0], Frequency=50.0)


def _metrics(soc, load, gen):
    return MetricsData(PvPower=[100.0], PvVoltage=[300.0], PvCurrent=[0.3], LoadPower=list(load),
                       BatterySOC=[soc], LoadCurrent=[1.0, 1.0, 1.0], BatteryPower=[10.0],
                       BatteryCurrent=[0.2], BatteryVoltage=[48.0], GridExportLimit=100.0,
                       BatteryTemperature=[20.0], InverterTemperature=30.0,
                       GenPower=list(gen), GenCurrent=[1.0, 1.0, 1.0], GenVoltage=[230.0, 230.0, 230.0])


async def test_start_registers_provider_and_no_longer_runs_its_own_loop(hass, config_entry):
    FakeQilowattClient.instances.clear()
    FakeQilowattClient.outcome = "ok"
    with patch("custom_components.qilowatt.mqtt_client.QilowattMQTTClient", FakeQilowattClient):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
        try:
            assert client.qw_device._data_provider == client.read_inverter_data
            assert not hasattr(client, "update_data_loop")
            # The library's timers are running on the device, not an HA task
            assert client.qw_device._sensor_timer_thread is not None
        finally:
            await hass.config_entries.async_unload(config_entry.entry_id)
            await hass.async_block_till_done()
    assert client.qw_device._sensor_timer_thread is None


async def test_read_inverter_data_returns_fresh_adapter_readings(hass, config_entry):
    client = MQTTClient(hass, config_entry)
    readings = iter([(_energy([1.0, 2.0, 3.0]), _metrics(50, [5.0, 5.0, 5.0], [0.0, 0.0, 0.0])),
                     (_energy([4.0, 5.0, 6.0]), _metrics(51, [6.0, 6.0, 6.0], [0.0, 0.0, 0.0]))])
    current = {}

    def next_reading():
        current["e"], current["m"] = next(readings)

    next_reading()
    with patch.object(client.inverter, "get_energy_data", side_effect=lambda: current["e"]), \
         patch.object(client.inverter, "get_metrics_data", side_effect=lambda: current["m"]):
        energy, metrics = client.read_inverter_data()
        assert energy.Power == [1.0, 2.0, 3.0] and metrics.BatterySOC == [50]
        next_reading()
        energy, metrics = client.read_inverter_data()
        assert energy.Power == [4.0, 5.0, 6.0] and metrics.BatterySOC == [51]


async def test_read_inverter_data_aggregates_secondaries(hass, config_entry):
    client = MQTTClient(hass, config_entry)
    secondary = MQTTClient(hass, config_entry).inverter   # same adapter class, stands in for a 2nd unit
    client.secondary_inverters = [secondary]

    with patch.object(client.inverter, "get_energy_data", return_value=_energy([100.0, 100.0, 100.0], today=2.0)), \
         patch.object(client.inverter, "get_metrics_data", return_value=_metrics(40, [10.0, 10.0, 10.0], [50.0, 0.0, 0.0])), \
         patch.object(secondary, "get_energy_data", return_value=_energy([1.0, 2.0, 3.0], today=0.5)), \
         patch.object(secondary, "get_metrics_data", return_value=_metrics(60, [1.0, 1.0, 1.0], [5.0, 5.0, 5.0])):
        energy, metrics = client.read_inverter_data()

    assert energy.Power == [101.0, 102.0, 103.0]
    assert energy.Today == 2.5
    assert energy.Voltage == [230.0, 231.0, 232.0]      # primary only
    assert metrics.BatterySOC == [40, 60]               # one entry per unit
    assert metrics.LoadPower == [11.0, 11.0, 11.0]
    assert metrics.GenPower == [55.0, 5.0, 5.0]
    assert metrics.GenVoltage == [230.0, 230.0, 230.0]  # primary only


async def test_read_inverter_data_survives_a_failing_secondary(hass, config_entry):
    client = MQTTClient(hass, config_entry)
    secondary = MQTTClient(hass, config_entry).inverter
    client.secondary_inverters = [secondary]
    with patch.object(client.inverter, "get_energy_data", return_value=_energy([1.0, 1.0, 1.0])), \
         patch.object(client.inverter, "get_metrics_data", return_value=_metrics(1, [1.0, 1.0, 1.0], [0.0, 0.0, 0.0])), \
         patch.object(secondary, "get_energy_data", side_effect=RuntimeError("entities missing")):
        energy, metrics = client.read_inverter_data()
    assert energy.Power == [1.0, 1.0, 1.0] and metrics.BatterySOC == [1]


async def test_unavailable_primary_yields_no_data_instead_of_zeros(hass, config_entry):
    client = MQTTClient(hass, config_entry)
    with patch.object(client.inverter, "is_available", return_value=False), \
         patch.object(client.inverter, "get_energy_data") as read_energy:
        assert client.read_inverter_data() == (None, None)
    read_energy.assert_not_called()


async def test_unavailable_secondary_is_left_out_of_the_aggregate(hass, config_entry):
    client = MQTTClient(hass, config_entry)
    secondary = MQTTClient(hass, config_entry).inverter
    client.secondary_inverters = [secondary]
    with patch.object(client.inverter, "get_energy_data", return_value=_energy([1.0, 1.0, 1.0])), \
         patch.object(client.inverter, "get_metrics_data", return_value=_metrics(80, [1.0, 1.0, 1.0], [0.0, 0.0, 0.0])), \
         patch.object(secondary, "is_available", return_value=False), \
         patch.object(secondary, "get_metrics_data") as read_secondary:
        energy, metrics = client.read_inverter_data()
    read_secondary.assert_not_called()
    assert energy.Power == [1.0, 1.0, 1.0]
    assert metrics.BatterySOC == [80]          # not [80, 0]


async def test_entities_going_unavailable_during_the_read_skip_the_slot(hass, config_entry):
    """The check is repeated after the reads: a state change between them must not pass zeros."""
    client = MQTTClient(hass, config_entry)
    secondary = MQTTClient(hass, config_entry).inverter
    client.secondary_inverters = [secondary]
    zeros = _energy([0.0, 0.0, 0.0])
    with patch.object(client.inverter, "is_available", side_effect=[True, False]), \
         patch.object(client.inverter, "get_energy_data", return_value=zeros), \
         patch.object(client.inverter, "get_metrics_data", return_value=_metrics(0, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])):
        assert client.read_inverter_data() == (None, None)

    with patch.object(client.inverter, "is_available", return_value=True), \
         patch.object(client.inverter, "get_energy_data", return_value=_energy([1.0, 1.0, 1.0])), \
         patch.object(client.inverter, "get_metrics_data", return_value=_metrics(80, [1.0, 1.0, 1.0], [0.0, 0.0, 0.0])), \
         patch.object(secondary, "is_available", side_effect=[True, False]), \
         patch.object(secondary, "get_energy_data", return_value=zeros), \
         patch.object(secondary, "get_metrics_data", return_value=_metrics(0, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])):
        energy, metrics = client.read_inverter_data()
    assert energy.Power == [1.0, 1.0, 1.0]
    assert metrics.BatterySOC == [80]          # the secondary's 0 was dropped


async def test_is_available_follows_the_core_entities(hass, solarman_device, config_entry):
    registry = er.async_get(hass)
    for object_id in ("deye_grid_l1_voltage", "deye_battery", "deye_pv1_power"):
        registry.async_get_or_create(
            "sensor", "solarman", object_id, suggested_object_id=object_id,
            device_id=solarman_device.id,
        )
    hass.states.async_set("sensor.deye_grid_l1_voltage", "231.5")
    hass.states.async_set("sensor.deye_battery", "83")
    hass.states.async_set("sensor.deye_pv1_power", "unavailable")
    inverter = MQTTClient(hass, config_entry).inverter

    assert inverter.is_available()             # a non-core entity being down does not matter

    hass.states.async_set("sensor.deye_battery", "unavailable")
    assert not inverter.is_available()

    hass.states.async_set("sensor.deye_battery", "84")
    hass.states.async_set("sensor.deye_grid_l1_voltage", "unknown")
    assert not inverter.is_available()

    hass.states.async_set("sensor.deye_grid_l1_voltage", "0")
    assert inverter.is_available()             # grid down is a real reading, not a missing one


async def test_availability_changes_are_logged_once(hass, config_entry, caplog):
    client = MQTTClient(hass, config_entry)
    available = {"v": False}
    with patch.object(client.inverter, "is_available", side_effect=lambda: available["v"]), \
         patch.object(client.inverter, "get_energy_data", return_value=_energy([1.0, 1.0, 1.0])), \
         patch.object(client.inverter, "get_metrics_data", return_value=_metrics(1, [1.0, 1.0, 1.0], [0.0, 0.0, 0.0])), \
         caplog.at_level("INFO", logger="custom_components.qilowatt"):
        for _ in range(3):
            client.read_inverter_data()
        available["v"] = True
        for _ in range(3):
            client.read_inverter_data()
    assert sum("unavailable entities" in r.message for r in caplog.records) == 1
    assert sum("available again" in r.message for r in caplog.records) == 1
