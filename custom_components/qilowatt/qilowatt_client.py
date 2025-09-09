"""Client wrapper for Qilowatt integration."""

import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.const import __version__ as HA_VERSION

from qilowatt import InverterDevice, SwitchDevice, QilowattMQTTClient, WorkModeCommand

from .const import (
    CONF_DEVICE_MODEL,
    CONF_DEVICE_TYPE,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_USERNAME,
    CONF_QILOWATT_DEVICE_ID,
    DEVICE_TYPE_INVERTER,
    DEVICE_TYPE_SWITCH,
    DOMAIN,
)
from .device import get_device_class

_LOGGER = logging.getLogger(__name__)


class QilowattClient:
    """Wrapper for the Qilowatt MQTT client."""

    def __init__(self, hass: HomeAssistant, config_entry) -> None:
        """Initialize the MQTT client wrapper."""
        self.hass = hass
        self.config_entry = config_entry

        self.mqtt_username = config_entry.data[CONF_MQTT_USERNAME]
        self.mqtt_password = config_entry.data[CONF_MQTT_PASSWORD]
        self.device_id = config_entry.data[CONF_QILOWATT_DEVICE_ID]
        self.device_type = config_entry.data[CONF_DEVICE_TYPE]
        self.device_model = config_entry.data[CONF_DEVICE_MODEL]

        self.qilowatt_client = None  # Will be initialized later

        # Initialize the device handler
        device_class = get_device_class(self.device_type, self.device_model)
        self.device_handler = device_class(self.hass, config_entry)

        # Initialize the appropriate Qilowatt device
        if self.device_type == DEVICE_TYPE_INVERTER:
            self.qw_device = InverterDevice(device_id=self.device_id)
        elif self.device_type == DEVICE_TYPE_SWITCH:
            self.qw_device = SwitchDevice(device_id=self.device_id)
        else:
            raise ValueError(f"Unsupported device type: {self.device_type}")

        # Set qw_device version data (convert AwesomeVersion to str)
        qilowatt_integration = self.hass.data.get("integrations", {}).get(DOMAIN)
        qilowatt_ha_version = (
            str(qilowatt_integration.version)
            if qilowatt_integration and getattr(qilowatt_integration, "version", None)
            else "unknown"
        )
        for requirement in qilowatt_integration.requirements:
            if requirement.startswith("qilowatt=="):
                qilowatt_py_version = requirement.split("==")[1]
                break

        self.qw_device.set_version_data(
            {
                "HA": HA_VERSION,
                "qilowatt-ha": qilowatt_ha_version,
                "qilowatt-py": qilowatt_py_version,
            }
        )

    def initialize_client(self):
        """Initialize the Qilowatt MQTT client."""
        _LOGGER.debug("Initializing Qilowatt MQTT client")

        self.qilowatt_client = QilowattMQTTClient(
            mqtt_username=self.mqtt_username,
            mqtt_password=self.mqtt_password,
            device=self.qw_device,
            host="test-mqtt.qilowatt.it",
        )

        # Set up appropriate callbacks based on device type
        if self.device_type == DEVICE_TYPE_INVERTER:
            self.qw_device.set_command_callback(self._on_inverter_command_received)
        elif self.device_type == DEVICE_TYPE_SWITCH:
            self.qw_device.set_command_callback(self._on_switch_command_received)

        # Add connection status callback
        self.qilowatt_client.add_connection_callback(self._on_connection_status_changed)

    async def start(self):
        """Start the Qilowatt MQTT client."""
        _LOGGER.debug("Starting Qilowatt MQTT client")
        # Run the blocking initialization in the executor
        if self.qilowatt_client is None:
            await self.hass.async_add_executor_job(self.initialize_client)
        # Run the blocking connect in the executor too
        await self.hass.async_add_executor_job(self.qilowatt_client.connect)

        # Start data update loop
        self.hass.loop.create_task(self.update_data_loop())

    def stop(self):
        """Stop the Qilowatt MQTT client."""
        _LOGGER.debug("Stopping Qilowatt MQTT client")
        if self.qilowatt_client:
            self.qilowatt_client.disconnect()

    def _on_inverter_command_received(self, command: WorkModeCommand):
        """Handle the WORKMODE command received from the MQTT broker for inverters."""
        _LOGGER.debug("Received WORKMODE command: %s", command)
        # Dispatch the command to Home Assistant using async_dispatcher_send
        self.hass.loop.call_soon_threadsafe(
            async_dispatcher_send,
            self.hass,
            f"{DOMAIN}_workmode_update_{self.device_id}",
            command,
        )

    def _on_switch_command_received(self, state: bool):
        """Handle the switch state command received from the MQTT broker for switches."""
        _LOGGER.debug("Received switch state command: %s", state)
        # Handle the command via the device handler
        try:
            self.device_handler.handle_command_received(state)
        except Exception as e:  # pylint: disable=broad-except
            _LOGGER.error("Error handling switch command: %s", e)

        # Dispatch the state to Home Assistant using async_dispatcher_send
        self.hass.loop.call_soon_threadsafe(
            async_dispatcher_send,
            self.hass,
            f"{DOMAIN}_switch_update_{self.device_id}",
            state,
        )

    def _on_connection_status_changed(self, connected: bool):
        """Handle MQTT connection status changes."""
        _LOGGER.debug("MQTT connection status changed: %s", connected)
        # Dispatch the connection status to Home Assistant using async_dispatcher_send
        self.hass.loop.call_soon_threadsafe(
            async_dispatcher_send,
            self.hass,
            f"{DOMAIN}_connection_status_{self.device_id}",
            connected,
        )

    async def update_data_loop(self):
        """Loop to periodically fetch data and send it to MQTT."""
        # Initial delay to give MQTT client time to establish connection
        await asyncio.sleep(5)

        while True:
            try:
                await self.hass.async_add_executor_job(self.update_data)
            except Exception as e:  # pylint: disable=broad-except
                _LOGGER.error("Error updating data: %s", e)
            await asyncio.sleep(10)  # Adjust the interval as needed

    def update_data(self):
        """Fetch data from device and send to MQTT."""
        # Skip if client doesn't exist
        if not self.qilowatt_client:
            _LOGGER.debug("MQTT client not initialized, skipping data update")
            return

        # Check connection status using the connected property
        if not self.qilowatt_client.connected:
            _LOGGER.debug("MQTT client not connected, skipping data update")
            return

        # Handle different device types
        if self.device_type == DEVICE_TYPE_INVERTER:
            self._update_inverter_data()
        elif self.device_type == DEVICE_TYPE_SWITCH:
            self._update_switch_data()

    def _update_inverter_data(self):
        """Update data for inverter devices."""
        # Fetch latest data from the inverter
        energy_data = self.device_handler.get_energy_data()
        metrics_data = self.device_handler.get_metrics_data()

        # Set data in the qilowatt client
        self.qw_device.set_energy_data(energy_data)
        self.qw_device.set_metrics_data(metrics_data)

    def _update_switch_data(self):
        """Update data for switch devices."""
        # Fetch latest state from the switch
        switch_state = self.device_handler.get_switch_state()

        # Set state in the qilowatt client if available
        if switch_state is not None:
            if switch_state:
                self.qw_device.turn_on()
            else:
                self.qw_device.turn_off()
