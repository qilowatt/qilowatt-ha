"""Binary sensor platform for Qilowatt integration."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import async_generate_entity_id
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DATA_CLIENT, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Qilowatt binary sensor platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]

    async_add_entities([QilowattConnectionSensor(hass, config_entry, client)])


class QilowattConnectionSensor(BinarySensorEntity):
    """Binary sensor for MQTT connection status."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, client) -> None:
        """Initialize the connection status sensor."""
        self.hass = hass
        self.config_entry = config_entry
        self.client = client
        self._attr_unique_id = f"{config_entry.data['inverter_id']}_qw_connected"
        self._attr_translation_key = "qw_connected"
        self._attr_is_on = False

        # Set explicit entity ID
        self.entity_id = async_generate_entity_id(
            "binary_sensor.{}", "qw_connected", hass.states.async_entity_ids()
        )

        # Set up device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": config_entry.title,
            "manufacturer": "Qilowatt",
            "model": config_entry.data.get("inverter_model", "Unknown"),
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to connection status updates."""
        signal_name = (
            f"{DOMAIN}_connection_status_{self.config_entry.data['inverter_id']}"
        )
        _LOGGER.debug("Binary sensor subscribing to signal: %s", signal_name)
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_name,
                self._handle_connection_update,
            )
        )

        # Set initial state based on current connection status
        if self.client.qilowatt_client and self.client.qilowatt_client.connected:
            self._attr_is_on = True
            _LOGGER.debug("Binary sensor initialized with connected state: True")
        else:
            self._attr_is_on = False
            _LOGGER.debug("Binary sensor initialized with connected state: %s", self._attr_is_on)

    @callback
    def _handle_connection_update(self, connected: bool) -> None:
        """Handle connection status update."""
        _LOGGER.debug("Connection status update: %s", connected)
        self._attr_is_on = connected
        self.async_write_ha_state()
