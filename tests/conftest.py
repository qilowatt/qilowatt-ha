"""Shared fixtures."""

from unittest.mock import patch

import pytest
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.qilowatt.const import (
    CONF_DEVICE_ID,
    CONF_INVERTER_ID,
    CONF_INVERTER_MODEL,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_USERNAME,
    CONF_SECONDARY_DEVICE_IDS,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components in every test."""
    yield


@pytest.fixture
def solarman_device(hass):
    """A discoverable Solarman inverter device."""
    registry = dr.async_get(hass)
    other = MockConfigEntry(domain="solarman", data={})
    other.add_to_hass(hass)
    return registry.async_get_or_create(
        config_entry_id=other.entry_id,
        identifiers={("solarman", "serial-1")},
        name="Deye Inverter",
        manufacturer="Deye",
    )


def entry_data(device_id="dev-1"):
    return {
        CONF_MQTT_USERNAME: "user",
        CONF_MQTT_PASSWORD: "pass",
        CONF_INVERTER_ID: "QW123",
        CONF_DEVICE_ID: device_id,
        CONF_INVERTER_MODEL: "Solarman",
        CONF_SECONDARY_DEVICE_IDS: [],
    }


@pytest.fixture
def config_entry(hass, solarman_device):
    """A v3 config entry pointing at the Solarman device."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Deye Inverter",
        data=entry_data(solarman_device.id),
        unique_id="QW123",
        version=3,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def no_mqtt():
    """Keep the real MQTT client out of integration setup."""
    with patch(
        "custom_components.qilowatt.mqtt_client.MQTTClient.start", return_value=None
    ), patch(
        "custom_components.qilowatt.mqtt_client.MQTTClient.async_stop", return_value=None
    ):
        yield
