"""Device factory for the Qilowatt integration."""

from ..const import DEVICE_TYPE_INVERTER, DEVICE_TYPE_SWITCH
from ..inverter import get_inverter_class
from .switch_factory import get_switch_class


def get_device_class(device_type: str, device_model: str):
    """Get the appropriate device class based on device type and model."""
    if device_type == DEVICE_TYPE_INVERTER:
        return get_inverter_class(device_model)
    if device_type == DEVICE_TYPE_SWITCH:
        return get_switch_class(device_model)
    raise ValueError(f"Unsupported device type: {device_type}")
