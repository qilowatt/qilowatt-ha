"""Qilowatt integration for Home Assistant."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_DEVICE_MODEL,
    CONF_DEVICE_TYPE,
    CONF_INVERTER_ID,
    CONF_INVERTER_MODEL,
    CONF_QILOWATT_DEVICE_ID,
    DATA_CLIENT,
    DEVICE_TYPE_INVERTER,
    DOMAIN,
)
from .qilowatt_client import QilowattClient

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry from version 1 to version 2."""
    _LOGGER.debug("Migrating config entry from version %s", config_entry.version)

    if config_entry.version > 2:
        # This means the user has downgraded from a newer version
        return False

    if config_entry.version == 1:
        # Migrate from version 1 to version 2
        new_data = dict(config_entry.data)

        # Rename inverter_id to qilowatt_device_id
        if CONF_INVERTER_ID in new_data:
            new_data[CONF_QILOWATT_DEVICE_ID] = new_data.pop(CONF_INVERTER_ID)

        # Rename inverter_model to device_model and add device_type
        if CONF_INVERTER_MODEL in new_data:
            new_data[CONF_DEVICE_MODEL] = new_data.pop(CONF_INVERTER_MODEL)
            new_data[CONF_DEVICE_TYPE] = DEVICE_TYPE_INVERTER

        # Update the config entry
        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
            version=2,
            minor_version=1,
        )

    _LOGGER.debug("Migration to version %s successful", config_entry.version)
    return True


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Qilowatt integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Qilowatt from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    client = QilowattClient(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = {DATA_CLIENT: client}

    # Start the client asynchronously
    await client.start()

    # Use the new method and await it
    await hass.config_entries.async_forward_entry_setups(
        entry, ["sensor", "binary_sensor", "switch"]
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a Qilowatt config entry."""
    client = hass.data[DOMAIN][entry.entry_id][DATA_CLIENT]
    await hass.async_add_executor_job(client.stop)
    hass.data[DOMAIN].pop(entry.entry_id)

    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    await hass.config_entries.async_forward_entry_unload(entry, "binary_sensor")
    await hass.config_entries.async_forward_entry_unload(entry, "switch")

    return True
