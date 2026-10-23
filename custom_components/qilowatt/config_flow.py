"""Config flow for the Qilowatt integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_DEVICE_ID,
    CONF_INVERTER_ID,
    CONF_INVERTER_MODEL,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_USERNAME,
    CONF_SECONDARY_DEVICE_IDS,
    DOMAIN,
)
from .mqtt_client import CannotConnect, InvalidAuth, async_validate_credentials

_LOGGER = logging.getLogger(__name__)

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class QilowattConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Qilowatt Integration."""

    VERSION = 3

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._user_input: dict[str, Any] = {}
        self._available_inverters: dict[str, dict[str, str]] = {}

    async def _async_check_credentials(
        self, username: str, password: str, inverter_id: str
    ) -> dict[str, str]:
        """Try the credentials against the broker; return form errors, if any."""
        try:
            await async_validate_credentials(self.hass, username, password, inverter_id)
        except InvalidAuth:
            return {"base": "invalid_auth"}
        except CannotConnect as err:
            _LOGGER.warning("Could not validate Qilowatt credentials: %s", err)
            return {"base": "cannot_connect"}
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected error validating Qilowatt credentials")
            return {"base": "unknown"}
        return {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        self._available_inverters = await self._discover_inverters()

        if not self._available_inverters:
            return self.async_abort(reason="no_devices_found")

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_INVERTER_ID])
            self._abort_if_unique_id_configured()

            errors = await self._async_check_credentials(
                user_input[CONF_MQTT_USERNAME],
                user_input[CONF_MQTT_PASSWORD],
                user_input[CONF_INVERTER_ID],
            )

        if user_input is not None and not errors:
            selected_device_id = user_input[CONF_DEVICE_ID]
            inverter_model = self._available_inverters[selected_device_id][
                "inverter_integration"
            ]
            user_input[CONF_INVERTER_MODEL] = inverter_model
            self._user_input = user_input

            # Check if there are other inverters of the same model
            remaining = {
                did: inv
                for did, inv in self._available_inverters.items()
                if did != selected_device_id
                and inv["inverter_integration"] == inverter_model
            }

            if remaining:
                return await self.async_step_secondary()

            # No secondary inverters available, create entry directly
            user_input[CONF_SECONDARY_DEVICE_IDS] = []
            return self.async_create_entry(
                title=f"{self._available_inverters[selected_device_id]['name']}",
                data=user_input,
            )

        inverter_options = {
            device_id: inverter["name"]
            for device_id, inverter in self._available_inverters.items()
        }

        data_schema = vol.Schema(
            {
                vol.Required(CONF_MQTT_USERNAME): str,
                vol.Required(CONF_MQTT_PASSWORD): PASSWORD_SELECTOR,
                vol.Required(CONF_INVERTER_ID): str,
                vol.Required(CONF_DEVICE_ID): vol.In(inverter_options),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(data_schema, user_input),
            errors=errors,
        )

    async def async_step_secondary(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the secondary inverter selection step."""
        primary_device_id = self._user_input[CONF_DEVICE_ID]
        primary_model = self._user_input[CONF_INVERTER_MODEL]

        remaining = {
            did: inv
            for did, inv in self._available_inverters.items()
            if did != primary_device_id
            and inv["inverter_integration"] == primary_model
        }

        if user_input is not None:
            selected = user_input.get(CONF_SECONDARY_DEVICE_IDS, [])
            self._user_input[CONF_SECONDARY_DEVICE_IDS] = selected
            return self.async_create_entry(
                title=f"{self._available_inverters[primary_device_id]['name']}",
                data=self._user_input,
            )

        secondary_options = {
            device_id: inverter["name"]
            for device_id, inverter in remaining.items()
        }

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_SECONDARY_DEVICE_IDS): cv.multi_select(
                    secondary_options
                ),
            }
        )

        return self.async_show_form(
            step_id="secondary", data_schema=data_schema, errors={}
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Handle a reauth request: the broker rejected the stored credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for new MQTT credentials and validate them before saving."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await self._async_check_credentials(
                user_input[CONF_MQTT_USERNAME],
                user_input[CONF_MQTT_PASSWORD],
                entry.data[CONF_INVERTER_ID],
            )
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_MQTT_USERNAME: user_input[CONF_MQTT_USERNAME],
                        CONF_MQTT_PASSWORD: user_input[CONF_MQTT_PASSWORD],
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_MQTT_USERNAME, default=entry.data.get(CONF_MQTT_USERNAME, "")
                ): str,
                vol.Required(CONF_MQTT_PASSWORD): PASSWORD_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"inverter_id": entry.data[CONF_INVERTER_ID]},
        )

    async def _discover_inverters(self) -> dict[str, dict[str, str]]:
        """Discover inverters in Home Assistant."""
        device_registry = dr.async_get(self.hass)
        inverters: dict[str, dict[str, str]] = {}
        seen_gx_entries: set[str] = set()

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
                    if device.manufacturer == "Sofar":
                        # Solarman Sofar inverter integration
                        inverters[device.id] = {
                            "name": device.name,
                            "inverter_integration": "SolarmanSofar",
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
                if domain == "victron_qw_addon":
                    # Victron inverter integration (legacy addon)
                    inverters[device.id] = {
                        "name": device.name or device_id,
                        "inverter_integration": "Victron",
                    }
                if domain == "victron_gx":
                    # HA native Victron GX integration – one entry per
                    # installation (all devices share a config entry).
                    entry_ids = frozenset(device.config_entries)
                    if entry_ids not in seen_gx_entries:
                        seen_gx_entries.add(entry_ids)
                        inverters[device.id] = {
                            "name": device.name or device_id,
                            "inverter_integration": "VictronGX",
                        }
            if (device.name and "Deye" in device.name) and (device.model and "esp32" in device.model):
                inverters[device.id] = {
                    "name": device.name,
                    "inverter_integration": "EspHome",
                }
        return inverters
