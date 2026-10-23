"""Config flow tests: credential validation, duplicates, reauth."""

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.qilowatt.const import (
    CONF_DEVICE_ID,
    CONF_INVERTER_ID,
    CONF_INVERTER_MODEL,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_USERNAME,
    DOMAIN,
)
from custom_components.qilowatt.mqtt_client import CannotConnect, InvalidAuth

VALIDATE = "custom_components.qilowatt.config_flow.async_validate_credentials"


async def _start_user_flow(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def test_user_flow_creates_entry_with_unique_id(hass, solarman_device, no_mqtt):
    result = await _start_user_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    with patch(VALIDATE, return_value=None) as validate:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_MQTT_USERNAME: "user",
                CONF_MQTT_PASSWORD: "secret",
                CONF_INVERTER_ID: "QW123",
                CONF_DEVICE_ID: solarman_device.id,
            },
        )
        await hass.async_block_till_done()

    validate.assert_awaited_once_with(hass, "user", "secret", "QW123")
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Deye Inverter"
    assert result["data"][CONF_INVERTER_MODEL] == "Solarman"
    assert result["result"].unique_id == "QW123"
    assert result["result"].version == 3


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (InvalidAuth("nope"), "invalid_auth"),
        (CannotConnect("down"), "cannot_connect"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_user_flow_shows_validation_errors(hass, solarman_device, side_effect, error):
    result = await _start_user_flow(hass)
    with patch(VALIDATE, side_effect=side_effect):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_MQTT_USERNAME: "user",
                CONF_MQTT_PASSWORD: "bad",
                CONF_INVERTER_ID: "QW123",
                CONF_DEVICE_ID: solarman_device.id,
            },
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    assert result["step_id"] == "user"


async def test_user_flow_aborts_on_duplicate_inverter_id(hass, config_entry):
    result = await _start_user_flow(hass)
    with patch(VALIDATE, return_value=None) as validate:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_MQTT_USERNAME: "user",
                CONF_MQTT_PASSWORD: "secret",
                CONF_INVERTER_ID: "QW123",
                CONF_DEVICE_ID: config_entry.data[CONF_DEVICE_ID],
            },
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    validate.assert_not_awaited()


async def test_user_flow_aborts_without_supported_inverters(hass):
    result = await _start_user_flow(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_reauth_updates_credentials_and_reloads(hass, config_entry, no_mqtt):
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is config_entries.ConfigEntryState.LOADED

    config_entry.async_start_reauth(hass)
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    flow = flows[0]
    assert flow["context"]["source"] == config_entries.SOURCE_REAUTH
    assert flow["step_id"] == "reauth_confirm"

    # Wrong password first: form comes back with the error
    with patch(VALIDATE, side_effect=InvalidAuth("nope")):
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {CONF_MQTT_USERNAME: "user", CONF_MQTT_PASSWORD: "still-bad"}
        )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    with patch(VALIDATE, return_value=None) as validate:
        result = await hass.config_entries.flow.async_configure(
            flow["flow_id"], {CONF_MQTT_USERNAME: "user2", CONF_MQTT_PASSWORD: "new-pass"}
        )
        await hass.async_block_till_done()

    validate.assert_awaited_once_with(hass, "user2", "new-pass", "QW123")
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data[CONF_MQTT_USERNAME] == "user2"
    assert config_entry.data[CONF_MQTT_PASSWORD] == "new-pass"
    assert config_entry.data[CONF_INVERTER_ID] == "QW123"
    assert config_entry.state is config_entries.ConfigEntryState.LOADED
