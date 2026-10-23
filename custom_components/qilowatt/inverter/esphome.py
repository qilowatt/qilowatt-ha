import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from qilowatt import EnergyData, MetricsData

from .base_inverter import BaseInverter

_LOGGER = logging.getLogger(__name__)


class EspHomeInverter(BaseInverter):
    """Implementation for EspHome integrated inverters."""

    def __init__(self, hass: HomeAssistant, config_entry, device_id=None):
        super().__init__(hass, config_entry, device_id)
        self.hass = hass
        self.device_id = device_id or config_entry.data["device_id"]
        self.entity_registry = er.async_get(hass)
        self.inverter_entities = {}
        for entity in self.entity_registry.entities.values():
            if entity.device_id == self.device_id:
                self.inverter_entities[entity.entity_id] = entity.name

    def find_entity_state(self, entity_id):
        """Helper method to find a state by entity_id."""
        return next(
            (
                self.hass.states.get(entity)
                for entity in self.inverter_entities
                if entity.endswith(entity_id)
            ),
            None,
        )

    def get_state_float(self, entity_id, default=0.0):
        """Helper method to get a sensor state as float."""

        state = self.find_entity_state(entity_id)
        if state and state.state not in ("unknown", "unavailable", ""):
            try:
                return float(state.state)
            except ValueError:
                _LOGGER.warning(f"Could not convert state of {entity_id} to float")
        else:
            _LOGGER.warning(f"State of {entity_id} is unavailable or unknown")
        return default

    def get_state_int(self, entity_id, default=0):
        """Helper method to get a sensor state as int."""
        state = self.find_entity_state(entity_id)
        if state and state.state not in ("unknown", "unavailable", ""):
            try:
                return int(float(state.state))
            except ValueError:
                _LOGGER.warning(f"Could not convert state of {entity_id} to int")
        else:
            _LOGGER.warning(f"State of {entity_id} is unavailable or unknown")
        return default

    def get_optional_float(self, entity_id):
        """Return a sensor state as float, or None if it is missing or unavailable.

        Unlike get_state_float this does not log, so it suits readings that only
        some ESPHome configurations expose, such as the generator port.
        """
        state = self.find_entity_state(entity_id)
        if state is None or state.state in ("unknown", "unavailable", ""):
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    def get_generator_data(self):
        """Return (voltage, power, current) per phase for the generator port.

        Reads the Generator Voltage L1..L3 and Generator Power L1..L3 sensors
        defined in examples/esphome-lilygo-tcan485.yaml (Deye registers
        661-666). Configurations without them report zeros.
        """
        voltage = [self.get_optional_float(f"_generator_voltage_l{i}") for i in (1, 2, 3)]
        power = [self.get_optional_float(f"_generator_power_l{i}") for i in (1, 2, 3)]
        voltage = [v if v is not None else 0.0 for v in voltage]
        power = [x if x is not None else 0.0 for x in power]
        current = [round(x / v, 2) if v else 0.0 for x, v in zip(power, voltage)]
        return voltage, power, current

    def get_energy_data(self):
        """Retrieve ENERGY data."""
        power = [
            self.get_state_float("_external_ct_l1_power"),
            self.get_state_float("_external_ct_l2_power"),
            self.get_state_float("_external_ct_l3_power"),
        ]
        today = self.get_state_float("_daily_energy_bought")
        total = 0.0  # As per payload
        current = [0.0, 0.0, 0.0]  # As per payload
        voltage = [
            self.get_state_float("_grid_voltage_l1"),
            self.get_state_float("_grid_voltage_l2"),
            self.get_state_float("_grid_voltage_l3"),
        ]
        frequency = self.get_state_float("_inverter_frequency")

        return EnergyData(
            Power=power,
            Today=today,
            Total=total,
            Current=current,
            Voltage=voltage,
            Frequency=frequency,
        )

    def get_metrics_data(self):
        """Retrieve METRICS data."""
        pv_power = [
            self.get_state_float("_pv1_power"),
            self.get_state_float("_pv2_power"),
        ]
        pv_voltage = [
            self.get_state_float("_pv1_voltage"),
            self.get_state_float("_pv2_voltage"),
        ]
        pv_current = [
            self.get_state_float("_pv1_current"),
            self.get_state_float("_pv2_current"),
        ]
        load_power = [
            self.get_state_float("_load_power_l1"),
            self.get_state_float("_load_power_l2"),
            self.get_state_float("_load_power_l3"),
        ]
        alarm_codes = [self.get_state_int("_error1"), self.get_state_int("_error2"), self.get_state_int("_error3"), self.get_state_int("_warning1"), self.get_state_int("_warning2"), self.get_state_int("_warning3")]
        battery_soc = self.get_state_int("_battery_capacity")
        load_current = [0.0, 0.0, 0.0]  # As per payload
        battery_power = [-1 * self.get_state_float("_battery_output_power")]
        battery_current = [-1 * self.get_state_float("_battery_output_current")]
        battery_voltage = [self.get_state_float("_battery_voltage")]
        inverter_status = 0  # As per payload
        grid_export_limit = self.get_state_float("_max_solar_sell_power")
        battery_temperature = [self.get_state_float("_battery_temperature")]
        inverter_temperature = self.get_state_float("_heat_sink_temperature")
        gen_voltage, gen_power, gen_current = self.get_generator_data()

        return MetricsData(
            PvPower=pv_power,
            PvVoltage=pv_voltage,
            PvCurrent=pv_current,
            LoadPower=load_power,
            AlarmCodes=alarm_codes,
            BatterySOC=[battery_soc],
            LoadCurrent=load_current,
            BatteryPower=battery_power,
            BatteryCurrent=battery_current,
            BatteryVoltage=battery_voltage,
            GenVoltage=gen_voltage,
            GenPower=gen_power,
            GenCurrent=gen_current,
            InverterStatus=inverter_status,
            GridExportLimit=grid_export_limit,
            BatteryTemperature=battery_temperature,
            InverterTemperature=inverter_temperature,
        )
