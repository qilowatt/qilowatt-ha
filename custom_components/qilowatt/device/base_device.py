"""Base class for all device implementations in the Qilowatt integration."""

from abc import ABC


class BaseDevice(ABC):
    """Abstract base class for device implementations."""

    def __init__(self, hass, config_entry):
        """Initialize the base device."""
        self.hass = hass
        self.config_entry = config_entry
