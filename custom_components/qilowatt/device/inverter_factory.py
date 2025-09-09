"""Factory for inverter devices in the Qilowatt integration."""

from ..inverter import get_inverter_class

# Re-export for device factory
__all__ = ["get_inverter_class"]
