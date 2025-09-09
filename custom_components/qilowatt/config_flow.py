"""Config flow for Qilowatt integration."""

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr, entity_registry as er, selector

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_TYPE,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_USERNAME,
    CONF_QILOWATT_DEVICE_ID,
    DEVICE_TYPE_INVERTER,
    DEVICE_TYPE_SWITCH,
    DEVICE_TYPES,
    DOMAIN,
)


class QilowattConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Qilowatt Integration."""

    VERSION = 2
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.selected_device_type = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step - device type selection."""
        errors = {}

        if user_input is not None:
            self.selected_device_type = user_input[CONF_DEVICE_TYPE]
            if self.selected_device_type == DEVICE_TYPE_INVERTER:
                return await self.async_step_inverter()
            if self.selected_device_type == DEVICE_TYPE_SWITCH:
                return await self.async_step_switch()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_TYPE): vol.In(
                    {device_type: device_type.title() for device_type in DEVICE_TYPES}
                ),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_inverter(self, user_input=None):
        """Handle inverter configuration."""
        errors = {}
        available_inverters = await self._discover_inverters()

        if user_input is not None:
            selected_device_id = user_input[CONF_DEVICE_ID]
            device_model = available_inverters[selected_device_id][
                "inverter_integration"
            ]

            config_data = {
                CONF_MQTT_USERNAME: user_input[CONF_MQTT_USERNAME],
                CONF_MQTT_PASSWORD: user_input[CONF_MQTT_PASSWORD],
                CONF_QILOWATT_DEVICE_ID: user_input[CONF_QILOWATT_DEVICE_ID],
                CONF_DEVICE_ID: selected_device_id,
                CONF_DEVICE_TYPE: DEVICE_TYPE_INVERTER,
                CONF_DEVICE_MODEL: device_model,
            }

            return self.async_create_entry(
                title=f"{available_inverters[selected_device_id]['name']} (Inverter)",
                data=config_data,
            )

        inverter_options = {
            device_id: inverter["name"]
            for device_id, inverter in available_inverters.items()
        }

        data_schema = vol.Schema(
            {
                vol.Required(CONF_MQTT_USERNAME): str,
                vol.Required(CONF_MQTT_PASSWORD): str,
                vol.Required(CONF_QILOWATT_DEVICE_ID): str,
                vol.Required(CONF_DEVICE_ID): vol.In(inverter_options),
            }
        )

        return self.async_show_form(
            step_id="inverter", data_schema=data_schema, errors=errors
        )

    async def async_step_switch(self, user_input=None):
        """Handle switch configuration."""
        errors = {}

        if user_input is not None:
            selected_entity_id = user_input[CONF_DEVICE_ID]

            # Get the entity name for the title
            entity_registry = er.async_get(self.hass)
            entity_entry = entity_registry.async_get(selected_entity_id)
            entity_name = (
                entity_entry.name
                if entity_entry and entity_entry.name
                else selected_entity_id
            )

            config_data = {
                CONF_MQTT_USERNAME: user_input[CONF_MQTT_USERNAME],
                CONF_MQTT_PASSWORD: user_input[CONF_MQTT_PASSWORD],
                CONF_QILOWATT_DEVICE_ID: user_input[CONF_QILOWATT_DEVICE_ID],
                CONF_DEVICE_ID: selected_entity_id,
                CONF_DEVICE_TYPE: DEVICE_TYPE_SWITCH,
                CONF_DEVICE_MODEL: "HomeAssistant",
            }

            return self.async_create_entry(
                title=f"{entity_name} (Switch)",
                data=config_data,
            )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_MQTT_USERNAME): str,
                vol.Required(CONF_MQTT_PASSWORD): str,
                vol.Required(CONF_QILOWATT_DEVICE_ID): str,
                vol.Required(CONF_DEVICE_ID): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="switch",
                        multiple=False,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="switch", data_schema=data_schema, errors=errors
        )

    async def _discover_inverters(self):
        """Discover inverters in Home Assistant."""
        device_registry = dr.async_get(self.hass)
        inverters = {}

        for device in device_registry.devices.values():
            for identifier in device.identifiers:
                domain, device_id, *_ = identifier
                if domain == "mqtt":
                    # Solar Assistant inverter
                    if "sa_inverter" in device_id:
                        inverters[device.id] = {
                            "name": device.name,
                            "inverter_integration": "SolarAssistant",
                        }
                if domain == "solarman":
                    # Solarman inverter integration
                    inverters[device.id] = {
                        "name": device.name,
                        "inverter_integration": "Solarman",
                    }
                if domain == "solax_modbus":
                    # Sofar Modbus inverter integration
                    inverters[device.id] = {
                        "name": device.name,
                        "inverter_integration": "Sofar",
                    }
                if domain == "huawei_solar":
                    # Huawei inverter integration
                    inverters[device.id] = {
                        "name": device.name,
                        "inverter_integration": "Huawei",
                    }
            if "Deye" in device.name and "esp32" in device.model:
                inverters[device.id] = {
                    "name": device.name,
                    "inverter_integration": "EspHome",
                }
        return inverters

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return QilowattOptionsFlow(config_entry)


class QilowattOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Qilowatt."""

    def __init__(self, config_entry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
