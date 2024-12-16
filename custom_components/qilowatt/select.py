import logging
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import DOMAIN, DATA_CLIENT

_LOGGER = logging.getLogger(__name__)

INVERTER_CONTROL_OPTIONS = ["Full control", "Only timer", "Only Fusebox", "No control"]

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the Inverter Control select entity."""
    client = hass.data[DOMAIN][entry.entry_id][DATA_CLIENT]
    async_add_entities([InverterControlSelect(client, entry)])

class InverterControlSelect(SelectEntity):
    """Select entity for Inverter Control."""

    _attr_options = INVERTER_CONTROL_OPTIONS

    def __init__(self, client, entry: ConfigEntry):
        """Initialize the select entity."""
        self._client = client
        self.entry = entry
        self._attr_name = "Inverter Control"
        self._attr_unique_id = f"{entry.entry_id}_inverter_control"
        self._attr_current_option = INVERTER_CONTROL_OPTIONS[0]
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the sensor."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.entry.title,
            manufacturer="Qilowatt",
            model=self.entry.data["inverter_model"],
            via_device=(DOMAIN, self.entry.entry_id),
        )

    async def async_select_option(self, option: str):
        """Handle the option selection."""
        if option not in self.options:
            _LOGGER.error("Invalid option selected: %s", option)
            return
        self._attr_current_option = option
        await self.async_update_ha_state()
        # TODO: Implement the logic to control the inverter using self._client