"""Switch platform for Qilowatt integration."""

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DEVICE_TYPE,
    CONF_QILOWATT_DEVICE_ID,
    DATA_CLIENT,
    DEVICE_TYPE_SWITCH,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Qilowatt switch platform."""
    # Only create switch entities for switch device types
    if config_entry.data.get(CONF_DEVICE_TYPE) != DEVICE_TYPE_SWITCH:
        return

    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    device_id = config_entry.data[CONF_QILOWATT_DEVICE_ID]

    # Create a switch entity for the Qilowatt switch device
    switch_entity = QilowattSwitchEntity(client, device_id, config_entry)
    async_add_entities([switch_entity])


class QilowattSwitchEntity(SwitchEntity):
    """Representation of a Qilowatt switch entity."""

    def __init__(self, client, device_id: str, config_entry: ConfigEntry) -> None:
        """Initialize the switch entity."""
        self._client = client
        self._device_id = device_id
        self._config_entry = config_entry
        self._attr_name = f"Qilowatt Switch {device_id}"
        self._attr_unique_id = f"qilowatt_switch_{device_id}"
        self._attr_is_on = None
        self._attr_available = False

    async def async_added_to_hass(self) -> None:
        """Register callbacks when entity is added to hass."""
        # Listen for switch state updates from MQTT
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_switch_update_{self._device_id}",
                self._handle_switch_update,
            )
        )

        # Listen for connection status updates
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_connection_status_{self._device_id}",
                self._handle_connection_status,
            )
        )

    @callback
    def _handle_switch_update(self, state: bool) -> None:
        """Handle switch state update from MQTT."""
        _LOGGER.debug("Switch %s state updated to: %s", self._device_id, state)
        self._attr_is_on = state
        self.async_write_ha_state()

    @callback
    def _handle_connection_status(self, connected: bool) -> None:
        """Handle connection status update."""
        _LOGGER.debug("Switch %s connection status: %s", self._device_id, connected)
        self._attr_available = connected
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on the switch."""
        if hasattr(self._client, "qw_device") and self._client.qw_device:
            await self.hass.async_add_executor_job(self._client.qw_device.turn_on)
            self._attr_is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off the switch."""
        if hasattr(self._client, "qw_device") and self._client.qw_device:
            await self.hass.async_add_executor_job(self._client.qw_device.turn_off)
            self._attr_is_on = False
            self.async_write_ha_state()

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": f"Qilowatt Switch {self._device_id}",
            "manufacturer": "Qilowatt",
            "model": "Switch Device",
        }
