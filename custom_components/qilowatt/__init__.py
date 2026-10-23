"""Qilowatt integration for Home Assistant."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import CONF_INVERTER_ID, DATA_CLIENT, DOMAIN
from .mqtt_client import MQTTClient

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry):
    """Migrate old config entries to new version."""
    if config_entry.version > 3:
        # Created by a newer version of the integration; refuse to downgrade
        return False

    if config_entry.version == 1:
        # v2 adds optional secondary_device_ids; absence is handled by .get() defaults
        hass.config_entries.async_update_entry(config_entry, version=2)
        _LOGGER.info("Migrated Qilowatt config entry %s from v1 to v2", config_entry.entry_id)

    if config_entry.version == 2:
        # v3 uses the Qilowatt inverter ID as unique_id so the same device
        # cannot be added twice. Skip the ID if another entry already holds it.
        inverter_id = config_entry.data.get(CONF_INVERTER_ID)
        unique_id = config_entry.unique_id
        if inverter_id and unique_id is None:
            existing = hass.config_entries.async_entry_for_domain_unique_id(DOMAIN, inverter_id)
            if existing is None:
                unique_id = inverter_id
            else:
                _LOGGER.warning(
                    "Qilowatt inverter ID %s is used by two config entries; "
                    "remove one of them",
                    inverter_id,
                )
        hass.config_entries.async_update_entry(config_entry, version=3, unique_id=unique_id)
        _LOGGER.info("Migrated Qilowatt config entry %s from v2 to v3", config_entry.entry_id)

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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a Qilowatt config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        client = hass.data[DOMAIN][entry.entry_id][DATA_CLIENT]
        await client.async_stop()
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
