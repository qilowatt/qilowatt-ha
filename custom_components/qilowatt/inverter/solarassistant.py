import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from qilowatt import EnergyData, MetricsData

from .base_inverter import BaseInverter

_LOGGER = logging.getLogger(__name__)


class SolarAssistantInverter(BaseInverter):
    """Implementation for SolarAssistant integrated inverters."""

    def __init__(self, hass: HomeAssistant, config_entry):
        super().__init__(hass, config_entry)
        self.hass = hass
        self.device_id = config_entry.data["device_id"]
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

    def get_energy_data(self):
        """Retrieve ENERGY data."""
        power = [
            self.get_state_float("grid_power_1"),
            self.get_state_float("grid_power_2"),
            self.get_state_float("grid_power_3"),
        ]
        today = self.get_state_float("grid_energy_in")
        total = 0.0  # As per payload
        current = [0.0, 0.0, 0.0]  # As per payload
        voltage = [
            self.get_state_float("grid_voltage_1"),
            self.get_state_float("grid_voltage_2"),
            self.get_state_float("grid_voltage_3"),
        ]
        frequency = self.get_state_float("grid_frequency")

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
            self.get_state_float("pv_power_1"),
            self.get_state_float("pv_power_2"),
        ]
        pv_voltage = [
            self.get_state_float("pv_voltage_1"),
            self.get_state_float("pv_voltage_2"),
        ]
        pv_current = [
            self.get_state_float("pv_current_1"),
            self.get_state_float("pv_current_2"),
        ]
        load_power = [
            self.get_state_float("load_power_1"),
            self.get_state_float("load_power_2"),
            self.get_state_float("load_power_3"),
        ]
        alarm_codes = [0]  # As per payload
        battery_soc = self.get_state_int("battery_state_of_charge")
        load_current = [0.0, 0.0, 0.0]  # As per payload
        battery_power = [self.get_state_float("battery_power")]
        battery_current = [self.get_state_float("battery_current")]
        battery_voltage = [self.get_state_float("battery_voltage")]
        inverter_status = 0  # As per payload
        grid_export_limit = self.get_state_float("max_sell_power")
        battery_temperature = [self.get_state_float("battery_temperature")]
        inverter_temperature = self.get_state_float("temperature")

        return MetricsData(
            PvPower=pv_power,
            PvVoltage=pv_voltage,
            PvCurrent=pv_current,
            LoadPower=load_power,
            AlarmCodes=alarm_codes,
            BatterySOC=battery_soc,
            LoadCurrent=load_current,
            BatteryPower=battery_power,
            BatteryCurrent=battery_current,
            BatteryVoltage=battery_voltage,
            InverterStatus=inverter_status,
            GridExportLimit=grid_export_limit,
            BatteryTemperature=battery_temperature,
            InverterTemperature=inverter_temperature,
        )
