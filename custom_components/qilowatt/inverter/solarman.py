import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from qilowatt import EnergyData, MetricsData

from .base_inverter import BaseInverter

_LOGGER = logging.getLogger(__name__)


class SolarmanInverter(BaseInverter):
    """Implementation for Solarman integrated inverters."""

    AVAILABILITY_ENTITIES = ("grid_l1_voltage", "_battery")

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
        some inverter profiles expose, such as the generator port.
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

        Three-phase Deye profiles expose Generator L1..L3 Voltage and Power.
        Single-phase profiles expose Generator Voltage and Power, reported on
        phase 1. Inverters without a generator port report zeros, which is what
        the Qilowatt backend expects.
        """
        voltage = [self.get_optional_float(f"generator_l{i}_voltage") for i in (1, 2, 3)]
        power = [self.get_optional_float(f"generator_l{i}_power") for i in (1, 2, 3)]
        if all(v is None for v in voltage) and all(x is None for x in power):
            voltage = [self.get_optional_float("generator_voltage"), None, None]
            power = [self.get_optional_float("generator_power"), None, None]
        voltage = [v if v is not None else 0.0 for v in voltage]
        power = [x if x is not None else 0.0 for x in power]
        current = [round(x / v, 2) if v else 0.0 for x, v in zip(power, voltage)]
        return voltage, power, current

    def get_energy_data(self):
        """Retrieve ENERGY data."""
        power = [
            self.get_state_float("grid_l1_power"),
            self.get_state_float("grid_l2_power"),
            self.get_state_float("grid_l3_power"),
        ]
        today = self.get_state_float("today_energy_import")
        total = 0.0  # As per payload
        voltage = [
            self.get_state_float("grid_l1_voltage"),
            self.get_state_float("grid_l2_voltage"),
            self.get_state_float("grid_l3_voltage"),
        ]
        current = [round(x / y, 2) if y else 0 for x, y in zip(power, voltage)]
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
            self.get_state_float("pv1_power"),
            self.get_state_float("pv2_power"),
        ]
        pv_voltage = [
            self.get_state_float("pv1_voltage"),
            self.get_state_float("pv2_voltage"),
        ]
        pv_current = [
            self.get_state_float("pv1_current"),
            self.get_state_float("pv2_current"),
        ]
        load_power = [
            self.get_state_float("load_l1_power"),
            self.get_state_float("load_l2_power"),
            self.get_state_float("load_l3_power"),
        ]
        alarm_codes = [0, 0, 0, 0, 0, 0]  # As per payload
        battery_soc = self.get_state_int("_battery")
        load_current = [0.0, 0.0, 0.0]  # As per payload
        battery_power = [-1 * self.get_state_float("battery_power")]
        battery_current = [-1 * self.get_state_float("battery_current")]
        battery_voltage = [self.get_state_float("battery_voltage")]
        inverter_status = 2  # As per payload
        grid_export_limit = self.get_state_float("grid_max_export_power")
        battery_temperature = [self.get_state_float("battery_temperature")]
        inverter_temperature = self.get_state_float("inverter_temperature")
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
