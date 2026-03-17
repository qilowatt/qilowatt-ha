"""Qilowatt integration for Home Assistant."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DATA_CLIENT, DOMAIN
from .mqtt_client import MQTTClient

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Migrate old config entries to new version."""
    if config_entry.version == 1:
        # v2 adds optional secondary_device_ids; absence is handled by .get() defaults
        hass.config_entries.async_update_entry(config_entry, version=2)
        _LOGGER.info("Migrated Qilowatt config entry %s from v1 to v2", config_entry.entry_id)
    return True


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the Qilowatt integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Qilowatt from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    client = MQTTClient(hass, entry)
    hass.data[DOMAIN][entry.entry_id] = {DATA_CLIENT: client}

    # Start the client asynchronously
    await client.start()

    # Use the new method and await it
    await hass.config_entries.async_forward_entry_setups(
        entry, ["sensor", "binary_sensor"]
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a Qilowatt config entry."""
    client = hass.data[DOMAIN][entry.entry_id][DATA_CLIENT]
    await hass.async_add_executor_job(client.stop)
    hass.data[DOMAIN].pop(entry.entry_id)

    await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    await hass.config_entries.async_forward_entry_unload(entry, "binary_sensor")

    return True
