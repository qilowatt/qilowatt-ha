import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from . import sensor
from .const import DATA_CLIENT, DOMAIN, CONF_BATTERY_SOC_SENSOR
from .mqtt_client import MQTTClient

_LOGGER = logging.getLogger(__name__)


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
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a Qilowatt config entry."""
    client = hass.data[DOMAIN][entry.entry_id][DATA_CLIENT]
    await hass.async_add_executor_job(client.stop)
    hass.data[DOMAIN].pop(entry.entry_id)

    await hass.config_entries.async_forward_entry_unload(entry, "sensor")

    return True