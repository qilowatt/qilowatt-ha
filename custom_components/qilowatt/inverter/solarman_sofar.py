import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from qilowatt import EnergyData, MetricsData

from .base_inverter import BaseInverter

_LOGGER = logging.getLogger(__name__)


class SolarmanSofarInverter(BaseInverter):
    """Implementation for Sofar integrated inverters."""

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
        """Helper method to find a state by entity_id (for Sofar sensors)."""
        return next(
            (
                self.hass.states.get(entity)
                for entity in self.inverter_entities
                if entity.endswith(entity_id)
            ),
            None,
        )

    def get_state_float(self, entity_id, default=0.0):
        """Helper method to get a sensor state as float (for Sofar sensors)."""
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
        """Helper method to get a sensor state as int (for Sofar sensors)."""
        state = self.find_entity_state(entity_id)
        if state and state.state not in ("unknown", "unavailable", ""):
            try:
                return int(float(state.state))
            except ValueError:
                _LOGGER.warning(f"Could not convert state of {entity_id} to int")
        else:
            _LOGGER.warning(f"State of {entity_id} is unavailable or unknown")
        return default

    def get_state_text(self, entity_id, default=""):
        """Helper method to get a sensor state as text (for Sofar sensors)."""
        state = self.find_entity_state(entity_id)
        if state and state.state not in ("unknown", "unavailable", "", None):
            return str(state.state)
        else:
            _LOGGER.warning(f"State of {entity_id} is unavailable, unknown, or empty")
        return default


    def get_energy_data(self):
        """Retrieve ENERGY data."""
        # Sensor is in kW and swap positive with negative and vice versa
        power = [
            self.get_state_float("inverter_activepower_pcc_r") * -1,
            self.get_state_float("inverter_activepower_pcc_s") * -1,
            self.get_state_float("inverter_activepower_pcc_t") * -1,
        ]
        today = self.get_state_float("inverter_today_energy_import")
        total = 0.0  # As per payload
        current = [
            self.get_state_float("inverter_current_pcc_r"),
            self.get_state_float("inverter_current_pcc_s"),
            self.get_state_float("inverter_current_pcc_t"),
        ]

        # Define voltage as self, because we need it in another function to calculate current from power
        self.voltage = [
            self.get_state_float("inverter_voltage_phase_r"),
            self.get_state_float("inverter_voltage_phase_s"),
            self.get_state_float("inverter_voltage_phase_t"),
        ]
        frequency = self.get_state_float("inverter_grid_frequency_2")

        return EnergyData(
            Power=power,
            Today=today,
            Total=total,
            Current=current,
            Voltage=self.voltage,
            Frequency=frequency,
        )

    def get_metrics_data(self):
        """Retrieve METRICS data."""
        pv_power = [
            self.get_state_float("inverter_pv1_power"),
            self.get_state_float("inverter_pv2_power"),
        ]
        pv_voltage = [
            self.get_state_float("inverter_pv1_voltage"),
            self.get_state_float("inverter_pv2_voltage"),
        ]
        pv_current = [
            self.get_state_float("inverter_pv1_current"),
            self.get_state_float("inverter_pv2_current"),
        ]

        # Create power array values from one sensor
        combined_power = round(self.get_state_float("inverter_activepower_load_sys") / 3)
        load_power = [combined_power] * 3

        alarm_codes = [0]
        battery_soc = self.get_state_int("sofar_inverter_battery_soc_average")

        # Calculate current from power and voltage, ensuring voltage is not zero
        load_current = []
        for x, y in zip(load_power, self.voltage):
            if y == 0:
                _LOGGER.warning(f"Voltage is zero for load power {x}, skipping division.")
                load_current.append(0)
            else:
                load_current.append(round(x / y, 2))

        battery_power = [self.get_state_float("sofar_inverter_battery_power_total")]
        battery_current = [self.get_state_float("inverter_battery_current")]
        battery_voltage = [self.get_state_float("inverter_battery_voltage")]
        inverter_status = 0  # As per payload
        grid_export_limit = self.get_state_float("sofar_inverter_export_surplus_power")
        battery_temperature = [self.get_state_float("inverter_battery_temperature")]
        inverter_temperature = self.get_state_float("inverter_ambient_temperature_1")

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