import logging
import asyncio
from threading import Lock
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from .const import DOMAIN
from .inverter import get_inverter_class
from qilowatt import QilowattMQTTClient, WorkModeCommand

_LOGGER = logging.getLogger(__name__)


class MQTTClient:
    """Wrapper for the Qilowatt MQTT client."""

    def __init__(self, hass: HomeAssistant, config_entry):
        self.hass = hass
        self.config_entry = config_entry

        self.mqtt_username = config_entry.data["mqtt_username"]
        self.mqtt_password = config_entry.data["mqtt_password"]
        self.inverter_id = config_entry.data["inverter_id"]
        self.inverter_model = config_entry.data["inverter_model"]

        self.qilowatt_client = None  # Will be initialized later

        # Initialize the inverter
        inverter_class = get_inverter_class(self.inverter_model)
        self.inverter = inverter_class(self.hass, config_entry)

    def initialize_client(self):
        """Initialize the Qilowatt MQTT client."""
        _LOGGER.debug("Initializing Qilowatt MQTT client")
        self.qilowatt_client = QilowattMQTTClient(
            mqtt_username=self.mqtt_username,
            mqtt_password=self.mqtt_password,
            inverter_id=self.inverter_id,
        )
        self.qilowatt_client.set_command_callback(self._on_command_received)

    async def start(self):
        """Start the Qilowatt MQTT client."""
        _LOGGER.debug("Starting Qilowatt MQTT client")
        if self.qilowatt_client is None:
            self.initialize_client()
        self.qilowatt_client.connect()
        # Start data update loop
        self.hass.loop.create_task(self.update_data_loop())

    def stop(self):
        """Stop the Qilowatt MQTT client."""
        _LOGGER.debug("Stopping Qilowatt MQTT client")
        if self.qilowatt_client:
            self.qilowatt_client.disconnect()

    def _on_command_received(self, command: WorkModeCommand):
        """Handle the WORKMODE command received from the MQTT broker."""
        _LOGGER.debug(f"Received WORKMODE command: {command}")
        
        # Control the inverter
        asyncio.run_coroutine_threadsafe(
            self.handle_inverter_control(command),
            self.hass.loop,
        )

        # Dispatch the command to Home Assistant using async_dispatcher_send
        self.hass.loop.call_soon_threadsafe(
            async_dispatcher_send,
            self.hass,
            f"{DOMAIN}_workmode_update_{self.inverter_id}",
            command,
        )

    async def handle_inverter_control(self, command: WorkModeCommand):
        """Determine if inverter control is allowed and execute control if so."""
        # Get the unique ID of the Inverter Control select entity
        select_unique_id = f"{self.config_entry.entry_id}_inverter_control"

        # Get the entity ID from the entity registry
        select_entity_id = self.entity_registry.async_get_entity_id(
            "select", DOMAIN, select_unique_id
        )

        if not select_entity_id:
            _LOGGER.error("Inverter Control select entity not found.")
            return

        # Get the state of the Inverter Control select entity
        select_state = self.hass.states.get(select_entity_id)
        if not select_state:
            _LOGGER.error("Unable to get state of Inverter Control select entity.")
            return

        inverter_control_value = select_state.state
        _LOGGER.debug(f"Inverter Control value: {inverter_control_value}")

        # Determine if the _source is allowed based on the Inverter Control setting
        control_map = {
            "Full control": ["timer", "fusebox"],
            "Only timer": ["timer"],
            "Only Fusebox": ["fusebox"],
            "No control": [],
        }

        allowed_sources = control_map.get(inverter_control_value, [])

        if command._source not in allowed_sources:
            _LOGGER.info(
                f"Source '{command._source}' is not allowed by Inverter Control setting '{inverter_control_value}'."
            )
            return

        # Proceed to control the inverter
        await self.inverter.set_mode(command)

    async def update_data_loop(self):
        """Loop to periodically fetch data and send it to MQTT."""
        while True:
            try:
                await self.hass.async_add_executor_job(self.update_data)
            except Exception as e:
                _LOGGER.error(f"Error updating data: {e}")
            await asyncio.sleep(10)  # Adjust the interval as needed

    def update_data(self):
        """Fetch data from inverter and send to MQTT."""
        # Fetch latest data from the inverter
        energy_data = self.inverter.get_energy_data()
        metrics_data = self.inverter.get_metrics_data()

        # Set data in the qilowatt client
        self.qilowatt_client.set_energy_data(energy_data)
        self.qilowatt_client.set_metrics_data(metrics_data)
