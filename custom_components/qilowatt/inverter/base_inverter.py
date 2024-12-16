# custom_components/qilowatt/inverter/base_inverter.py

from abc import ABC, abstractmethod
from qilowatt import WorkModeCommand


class BaseInverter(ABC):
    """Abstract base class for inverter implementations."""

    def __init__(self, hass, config_entry):
        self.hass = hass
        self.config_entry = config_entry

    @abstractmethod
    def get_energy_data(self):
        """Retrieve ENERGY data."""
        pass

    @abstractmethod
    def get_metrics_data(self):
        """Retrieve METRICS data."""
        pass

    @abstractmethod
    def set_mode(self, command: WorkModeCommand):
        """Control the inverter."""
        pass
