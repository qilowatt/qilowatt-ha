"""The library pulls inverter data through MQTTClient.read_inverter_data."""

from unittest.mock import patch

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
