"""Base class for inverter implementations in Qilowatt integration."""

from abc import ABC, abstractmethod

from ..device.base_device import BaseDevice


class BaseInverter(BaseDevice, ABC):
    """Abstract base class for inverter implementations."""

    @abstractmethod
    def get_energy_data(self):
        """Retrieve ENERGY data."""

    @abstractmethod
    def get_metrics_data(self):
        """Retrieve METRICS data."""
