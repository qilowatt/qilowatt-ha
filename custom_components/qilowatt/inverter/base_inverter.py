# custom_components/qilowatt/inverter/base_inverter.py

from abc import ABC, abstractmethod


class BaseInverter(ABC):
    """Abstract base class for inverter implementations."""

    # Entity names (as passed to find_entity_state) that must carry a real
    # value for this inverter's readings to mean anything, typically grid
    # voltage and battery SOC. While one of them is unavailable or unknown
    # the inverter is reported as unavailable and nothing is read from it, so
    # Qilowatt never receives zeros standing in for missing data. An entity
    # that does not exist at all is ignored, as the readers already tolerate.
    AVAILABILITY_ENTITIES: tuple[str, ...] = ()

    def __init__(self, hass, config_entry, device_id=None):
        self.hass = hass
        self.config_entry = config_entry
        self.device_id = device_id

    def is_available(self) -> bool:
        """Return False while a core entity is unavailable or unknown."""
        for name in self.AVAILABILITY_ENTITIES:
            state = self.find_entity_state(name)
            if state is not None and state.state in ("unavailable", "unknown", ""):
                return False
        return True

    @abstractmethod
    def get_energy_data(self):
        """Retrieve ENERGY data."""
        pass

    @abstractmethod
    def get_metrics_data(self):
        """Retrieve METRICS data."""
        pass
