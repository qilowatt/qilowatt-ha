"""Sensor platform for Qilowatt integration."""

import logging
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, async_generate_entity_id
from qilowatt import WorkModeCommand

from .const import (
    CONF_DEVICE_MODEL,
    CONF_DEVICE_TYPE,
    CONF_QILOWATT_DEVICE_ID,
    DEVICE_TYPE_INVERTER,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

ENTITY_ID_FORMAT = "sensor.{}"

# Define the metadata for each field
WORKMODE_FIELDS = {
    "Mode": {
        "name": "Mode",
        "unit_of_measurement": None,
        "device_class": None,
        "state_class": None,
    },
    "_source": {
        "name": "Source",
        "unit_of_measurement": None,
        "device_class": None,
        "state_class": None,
    },
    "BatterySoc": {
        "name": "Battery State of Charge",
        "unit_of_measurement": "%",
        "device_class": "battery",
        "state_class": "measurement",
    },
    "PowerLimit": {
        "name": "Power Limit",
        "unit_of_measurement": "W",
        "device_class": "power",
        "state_class": "measurement",
    },
    "PeakShaving": {
        "name": "Peak Shaving",
        "unit_of_measurement": "W",
        "device_class": "power",
        "state_class": "measurement",
    },
    "ChargeCurrent": {
        "name": "Charge Current",
        "unit_of_measurement": "A",
        "device_class": "current",
        "state_class": "measurement",
    },
    "DischargeCurrent": {
        "name": "Discharge Current",
        "unit_of_measurement": "A",
        "device_class": "current",
        "state_class": "measurement",
    },
}


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities
):
    """Set up Qilowatt sensors."""
    # Only set up sensors for inverter device types
    if config_entry.data.get(CONF_DEVICE_TYPE) != DEVICE_TYPE_INVERTER:
        return

    device_id = config_entry.data[CONF_QILOWATT_DEVICE_ID]

    # Add sensors for WORKMODE commands
    workmode_sensors = []
    for field, metadata in WORKMODE_FIELDS.items():
        entity_description = SensorEntityDescription(
            key=field,
            name=metadata["name"],
            unit_of_measurement=metadata["unit_of_measurement"],
            device_class=metadata["device_class"],
            state_class=metadata["state_class"],
        )
        sensor = WorkModeSensor(
            hass,
            device_id,
            entity_description,
            config_entry,
        )
        workmode_sensors.append(sensor)

    async_add_entities(workmode_sensors, update_before_add=True)


class WorkModeSensor(SensorEntity):
    """Sensor for WORKMODE command fields."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id,
        entity_description: SensorEntityDescription,
        entry,
    ) -> None:
        """Initialize the WorkMode sensor."""
        self.hass = hass
        self._device_id = device_id
        self.entity_description = entity_description
        self.entry = entry
        self._name = entity_description.name
        self._unique_id = f"{device_id}_{entity_description.key}"
        self._state = None
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT,
            f"qw_{entity_description.key}",
            hass.states.async_entity_ids(),
        )

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique ID of the sensor."""
        return self._unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the sensor."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.entry.title,
            manufacturer="Qilowatt",
            model=self.entry.data.get(CONF_DEVICE_MODEL, "Unknown"),
            via_device=(DOMAIN, self.entry.entry_id),
        )

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of the sensor."""
        return self.entity_description.unit_of_measurement

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        return self.entity_description.device_class

    @property
    def state_class(self):
        """Return the state class of the sensor."""
        return self.entity_description.state_class

    async def async_added_to_hass(self):
        """Register dispatcher to listen for WORKMODE updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_workmode_update_{self._device_id}",
                self._handle_workmode_update,
            )
        )

    async def _handle_workmode_update(self, command: WorkModeCommand):
        """Handle WORKMODE command updates."""
        _LOGGER.debug("WorkModeSensor '%s' handling update.", self._name)
        value = getattr(command, self.entity_description.key, None)
        self._state = value
        self.async_schedule_update_ha_state()
