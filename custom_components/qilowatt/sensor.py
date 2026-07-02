# custom_components/qilowatt/sensor.py

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfElectricCurrent, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, async_generate_entity_id
from qilowatt import WorkModeCommand

from .const import CONF_INVERTER_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)

ENTITY_ID_FORMAT = "sensor.{}"

# Descriptions for each WORKMODE command field exposed as a sensor
WORKMODE_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="Mode",
        name="Mode",
    ),
    SensorEntityDescription(
        key="_source",
        name="Source",
    ),
    SensorEntityDescription(
        key="BatterySoc",
        name="Battery State of Charge",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="PowerLimit",
        name="Power Limit",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="PeakShaving",
        name="Peak Shaving",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="MaxPower",
        name="Max Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="ChargeCurrent",
        name="Charge Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="DischargeCurrent",
        name="Discharge Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities
):
    """Set up Qilowatt sensors."""
    inverter_id = config_entry.data[CONF_INVERTER_ID]

    # Add sensors for WORKMODE commands
    async_add_entities(
        WorkModeSensor(hass, inverter_id, description, config_entry)
        for description in WORKMODE_SENSORS
    )


class WorkModeSensor(SensorEntity):
    """Sensor for WORKMODE command fields."""

    def __init__(self, hass: HomeAssistant, inverter_id, entity_description: SensorEntityDescription, entry) -> None:
        self.hass = hass
        self._inverter_id = inverter_id
        self.entity_description = entity_description
        self.entry = entry
        self._attr_unique_id = f"{inverter_id}_{entity_description.key}"
        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, f"qw_{entity_description.key}", hass.states.async_entity_ids()
        )

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

    async def async_added_to_hass(self):
        """Register dispatcher to listen for WORKMODE updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{DOMAIN}_workmode_update_{self._inverter_id}",
                self._handle_workmode_update,
            )
        )

    async def _handle_workmode_update(self, command: WorkModeCommand):
        """Handle WORKMODE command updates."""
        _LOGGER.debug("WorkModeSensor '%s' handling update.", self.name)
        self._attr_native_value = getattr(command, self.entity_description.key, None)
        self.async_write_ha_state()
