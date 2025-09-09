"""Switch device implementations for the Qilowatt integration."""

from abc import ABC, abstractmethod

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .base_device import BaseDevice


class BaseSwitch(BaseDevice, ABC):
    """Abstract base class for switch implementations."""

    @abstractmethod
    def get_switch_state(self) -> bool | None:
        """Get the current switch state."""

    @abstractmethod
    def handle_command_received(self, state: bool) -> None:
        """Handle switch state command received from MQTT."""


class HASwitch(BaseSwitch):
    """Implementation for Home Assistant switch entities."""

    def __init__(self, hass: HomeAssistant, config_entry):
        """Initialize the HA switch implementation."""
        super().__init__(hass, config_entry)
        self.device_id = config_entry.data["device_id"]
        self.entity_registry = er.async_get(hass)
        self.switch_entities = {}
        for entity in self.entity_registry.entities.values():
            if entity.device_id == self.device_id and entity.platform == "switch":
                self.switch_entities[entity.entity_id] = entity

    def get_switch_state(self) -> bool | None:
        """Get the current switch state from Home Assistant."""
        if not self.switch_entities:
            return None

        # Use the first switch entity found
        entity_id = next(iter(self.switch_entities.keys()))
        state = self.hass.states.get(entity_id)

        if state and state.state in ("on", "off"):
            return state.state == "on"
        return None

    def handle_command_received(self, state: bool) -> None:
        """Handle switch state command received from MQTT."""
        if not self.switch_entities:
            return

        # Update the first switch entity found
        entity_id = next(iter(self.switch_entities.keys()))

        # Call the appropriate Home Assistant service
        domain = "switch"
        service = "turn_on" if state else "turn_off"

        self.hass.async_create_task(
            self.hass.services.async_call(
                domain,
                service,
                {"entity_id": entity_id},
                blocking=True,
            )
        )


SWITCH_INTEGRATIONS = {
    "HomeAssistant": HASwitch,
}


def get_switch_class(model_name: str):
    """Get the switch class for the given model name."""
    try:
        return SWITCH_INTEGRATIONS[model_name]
    except KeyError:
        raise ValueError(f"Unsupported switch model: {model_name}") from None
