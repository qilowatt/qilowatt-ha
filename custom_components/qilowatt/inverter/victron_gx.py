import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from qilowatt import EnergyData, MetricsData

from .base_inverter import BaseInverter

_LOGGER = logging.getLogger(__name__)


class VictronGXInverter(BaseInverter):
    """Implementation for the HA native Victron GX integration (victron_gx).

    Unlike most adapters that read from a single HA device, Victron GX
    spreads sensors across several devices per installation (System, Grid
    Meter, Battery, Solar Charger, VE.Bus, etc.).  This adapter collects
    entities from every device that shares the same HA config entry as the
    device selected during setup, so any device from the installation can
    be chosen in the config flow.
    """

    def __init__(self, hass: HomeAssistant, config_entry, device_id=None):
        super().__init__(hass, config_entry, device_id)
        self.device_id = device_id or config_entry.data["device_id"]
        entity_reg = er.async_get(hass)
        device_reg = dr.async_get(hass)

        installation_device_ids = {self.device_id}
        device = device_reg.async_get(self.device_id)
        if device:
            for dev in device_reg.devices.values():
                if dev.config_entries & device.config_entries:
                    if any(d == "victron_gx" for d, *_ in dev.identifiers):
                        installation_device_ids.add(dev.id)

        self.inverter_entities = {}
        for entity in entity_reg.entities.values():
            if entity.device_id in installation_device_ids:
                self.inverter_entities[entity.entity_id] = entity.name

    def is_available(self) -> bool:
        """Check availability across device-level and system-level entities.

        Victron GX spreads sensors across multiple devices and setups may
        expose only system-level aggregates.  For each essential measurement
        group (grid power, battery SOC) we try several suffixes and flag
        unavailable as soon as a found entity reports so.
        """
        for suffixes in (
            ("grid_power_l1", "system_grid_power_l1"),
            ("battery_soc", "system_dc_battery_soc"),
        ):
            for suffix in suffixes:
                state = self.find_entity_state(suffix)
                if state is not None:
                    if state.state in ("unavailable", "unknown", ""):
                        return False
                    break
        return True

    def find_entity_state(self, entity_id):
        """Find a state by entity_id suffix across the whole installation."""
        return next(
            (
                self.hass.states.get(eid)
                for eid in self.inverter_entities
                if eid.endswith(entity_id)
            ),
            None,
        )

    def get_state_float(self, entity_id, default=0.0):
        """Get a sensor state as float."""
        state = self.find_entity_state(entity_id)
        if state and state.state not in ("unknown", "unavailable", ""):
            try:
                return float(state.state)
            except ValueError:
                _LOGGER.warning("Could not convert state of %s to float", entity_id)
        return default

    def get_state_int(self, entity_id, default=0):
        """Get a sensor state as int."""
        state = self.find_entity_state(entity_id)
        if state and state.state not in ("unknown", "unavailable", ""):
            try:
                return int(float(state.state))
            except ValueError:
                _LOGGER.warning("Could not convert state of %s to int", entity_id)
        return default

    def _first_float(self, *suffixes, default=0.0):
        """Try several entity suffixes, return the first valid float."""
        for suffix in suffixes:
            state = self.find_entity_state(suffix)
            if state and state.state not in ("unknown", "unavailable", ""):
                try:
                    return float(state.state)
                except ValueError:
                    continue
        return default

    def _first_int(self, *suffixes, default=0):
        """Try several entity suffixes, return the first valid int."""
        for suffix in suffixes:
            state = self.find_entity_state(suffix)
            if state and state.state not in ("unknown", "unavailable", ""):
                try:
                    return int(float(state.state))
                except ValueError:
                    continue
        return default

    # ----- EnergyData --------------------------------------------------

    def get_energy_data(self):
        """Retrieve ENERGY data."""
        power = [
            self._first_float("grid_power_l1", "system_grid_power_l1"),
            self._first_float("grid_power_l2", "system_grid_power_l2"),
            self._first_float("grid_power_l3", "system_grid_power_l3"),
        ]
        voltage = [
            self.get_state_float("grid_voltage_l1"),
            self.get_state_float("grid_voltage_l2"),
            self.get_state_float("grid_voltage_l3"),
        ]
        current = [
            self.get_state_float("grid_current_l1"),
            self.get_state_float("grid_current_l2"),
            self.get_state_float("grid_current_l3"),
        ]
        frequency = self.get_state_float("grid_frequency")
        today = 0.0
        total = self.get_state_float("grid_energy_forward")

        return EnergyData(
            Power=power,
            Today=today,
            Total=total,
            Current=current,
            Voltage=voltage,
            Frequency=frequency,
        )

    # ----- MetricsData -------------------------------------------------

    def get_metrics_data(self):
        """Retrieve METRICS data."""
        pv_power = [self._first_float("system_dc_pv_power", "solarcharger_yield_power")]
        pv_voltage = [self.get_state_float("solarcharger_voltage")]
        pv_current = [self._first_float("system_dc_pv_current", "solarcharger_pv_current")]

        load_power = [
            self._first_float("system_consumption_power_l1", "acload_power_l1"),
            self._first_float("system_consumption_power_l2", "acload_power_l2"),
            self._first_float("system_consumption_power_l3", "acload_power_l3"),
        ]

        battery_soc = self._first_int("system_dc_battery_soc", "battery_soc")
        battery_power = [self._first_float("system_dc_battery_power", "battery_power")]
        battery_current = [
            self._first_float("system_dc_battery_current", "battery_current")
        ]
        battery_voltage = [
            self._first_float("system_dc_battery_voltage", "battery_voltage")
        ]
        battery_temperature = [self.get_state_float("battery_temperature")]
        inverter_temperature = self.get_state_float("vebus_inverter_dc_temperature")

        return MetricsData(
            PvPower=pv_power,
            PvVoltage=pv_voltage,
            PvCurrent=pv_current,
            LoadPower=load_power,
            AlarmCodes=[0, 0, 0, 0, 0, 0],
            BatterySOC=[battery_soc],
            LoadCurrent=[0.0, 0.0, 0.0],
            BatteryPower=battery_power,
            BatteryCurrent=battery_current,
            BatteryVoltage=battery_voltage,
            InverterStatus=2,
            GridExportLimit=0.0,
            BatteryTemperature=battery_temperature,
            InverterTemperature=inverter_temperature,
        )
