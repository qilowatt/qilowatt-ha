# custom_components/qilowatt/inverter/base_inverter.py

from abc import ABC, abstractmethod


class BaseInverter(ABC):
    """Abstract base class for inverter implementations."""

    def __init__(self, hass, config_entry, device_id=None):
        self.hass = hass
        self.config_entry = config_entry
        self.device_id = device_id

    @abstractmethod
    def get_energy_data(self):
        """Retrieve ENERGY data."""
        pass

    @abstractmethod
    def get_metrics_data(self):
        """Retrieve METRICS data."""
        pass
