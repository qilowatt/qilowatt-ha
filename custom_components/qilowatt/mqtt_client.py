"""MQTT client wrapper for Qilowatt integration."""

import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.loader import async_get_loaded_integration

from qilowatt import (
    AuthenticationError,
    EnergyData,
    InverterDevice,
    MetricsData,
    QilowattMQTTClient,
    WorkModeCommand,
)

from .const import CONF_SECONDARY_DEVICE_IDS, DOMAIN
from .inverter import get_inverter_class

_LOGGER = logging.getLogger(__name__)

# Rejected CONNACKs tolerated before the library gives up and we ask for new
# credentials. paho retries after 10 s then 20 s, so this is about half a
# minute of refusals: enough to ride out a broker hiccup, short enough that a
# rotated password shows up as a repair quickly.
MAX_AUTH_RETRIES = 2

# How long the config flow waits for the broker to accept or reject a login.
VALIDATE_TIMEOUT = 20.0


class CannotConnect(HomeAssistantError):
    """The broker could not be reached or did not answer."""


class InvalidAuth(HomeAssistantError):
    """The broker rejected the credentials."""


async def async_validate_credentials(
    hass: HomeAssistant, username: str, password: str, inverter_id: str
) -> None:
    """Connect once to check the credentials; raise InvalidAuth or CannotConnect.

    Uses a throwaway client with no retries so a rejection is reported on the
    first CONNACK. One deadline (VALIDATE_TIMEOUT) covers both the blocking
    connect (DNS, TCP, TLS) and the wait for the broker's answer, so the form
    never hangs longer than that. The client is always disconnected afterwards.
    """
    loop = asyncio.get_running_loop()
    outcome: asyncio.Future = loop.create_future()
    holder: dict[str, QilowattMQTTClient] = {}

    def _settle(value):
        if not outcome.done():
            outcome.set_result(value)

    def _on_connection(connected: bool):
        if connected:
            loop.call_soon_threadsafe(_settle, None)

    def _on_error(error: Exception):
        loop.call_soon_threadsafe(_settle, error)

    def _build_and_connect():
        device = InverterDevice(device_id=inverter_id)
        client = QilowattMQTTClient(
            mqtt_username=username,
            mqtt_password=password,
            device=device,
            max_auth_retries=0,
        )
        client.add_connection_callback(_on_connection)
        client.add_error_callback(_on_error)
        # Published before connect() so cleanup can reach the client even if
        # the deadline expires while connect() is still blocking.
        holder["client"] = client
        client.connect()

    timed_out = False
    try:
        async with asyncio.timeout(VALIDATE_TIMEOUT):
            await hass.async_add_executor_job(_build_and_connect)
            error = await outcome
    # TimeoutError is a subclass of OSError, so it must be caught first or the
    # deadline expiry would be handled as a connection error with timed_out
    # still False, and the cleanup below would then be awaited.
    except TimeoutError as err:
        timed_out = True
        raise CannotConnect("No answer from the Qilowatt broker") from err
    except OSError as err:
        raise CannotConnect(f"Could not reach the Qilowatt broker: {err}") from err
    finally:
        client = holder.get("client")
        if client is not None:
            cleanup = hass.async_add_executor_job(client.disconnect)
            # After a timeout the executor may still be inside connect();
            # disconnect() waits for it, so let the cleanup finish in the
            # background instead of holding the form past its deadline.
            if not timed_out:
                await cleanup

    if isinstance(error, AuthenticationError):
        raise InvalidAuth("Qilowatt rejected the MQTT credentials") from error
    if error is not None:
        raise CannotConnect(str(error)) from error


class MQTTClient:
    """Wrapper for the Qilowatt MQTT client."""

    def __init__(self, hass: HomeAssistant, config_entry) -> None:
        """Initialize the MQTT client wrapper."""
        self.hass = hass
        self.config_entry = config_entry

        self.mqtt_username = config_entry.data["mqtt_username"]
        self.mqtt_password = config_entry.data["mqtt_password"]
        self.inverter_id = config_entry.data["inverter_id"]
        self.inverter_model = config_entry.data["inverter_model"]

        self.qilowatt_client = None  # Will be initialized later
        self._update_task = None

        # Initialize the primary inverter
        inverter_class = get_inverter_class(self.inverter_model)
        self.inverter = inverter_class(self.hass, config_entry)

        # Initialize secondary inverters
        self.secondary_inverters = []
        for secondary_device_id in config_entry.data.get(CONF_SECONDARY_DEVICE_IDS, []):
            secondary = inverter_class(
                self.hass, config_entry, device_id=secondary_device_id
            )
            self.secondary_inverters.append(secondary)

        self.qw_device = InverterDevice(device_id=self.inverter_id)

        # Set qw_device version data (convert AwesomeVersion to str)
        qilowatt_ha_version = "unknown"
        qilowatt_py_version = "unknown"
        try:
            integration = async_get_loaded_integration(self.hass, DOMAIN)
        except Exception:  # pylint: disable=broad-except
            integration = None
            _LOGGER.debug("Could not resolve the Qilowatt integration for version info")
        if integration:
            if integration.version:
                qilowatt_ha_version = str(integration.version)
            for requirement in integration.requirements:
                if requirement.startswith("qilowatt=="):
                    qilowatt_py_version = requirement.split("==", 1)[1]
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
            max_auth_retries=MAX_AUTH_RETRIES,
        )
        self.qw_device.set_command_callback(self._on_command_received)
        # Add connection status callback
        self.qilowatt_client.add_connection_callback(self._on_connection_status_changed)
        # Told once when the library gives up (e.g. credentials rejected)
        self.qilowatt_client.add_error_callback(self._on_client_error)

    async def start(self):
        """Start the Qilowatt MQTT client."""
        _LOGGER.debug("Starting Qilowatt MQTT client")
        # Run the blocking initialization in the executor
        if self.qilowatt_client is None:
            await self.hass.async_add_executor_job(self.initialize_client)
        # Run the blocking connect in the executor too. A broker that cannot be
        # reached right now (HA booting before the network is up, DNS not yet
        # resolving) is a reason to retry setup later, not to fail it. A refused
        # login does not raise here; it arrives through _on_client_error.
        try:
            await self.hass.async_add_executor_job(self.qilowatt_client.connect)
        except OSError as err:
            raise ConfigEntryNotReady(
                f"Could not connect to the Qilowatt broker: {err}"
            ) from err

        # Start data update loop; the config entry cancels this task on unload
        self._update_task = self.config_entry.async_create_background_task(
            self.hass,
            self.update_data_loop(),
            name=f"qilowatt_update_loop_{self.inverter_id}",
        )

    async def async_stop(self):
        """Stop the update loop and the Qilowatt MQTT client."""
        _LOGGER.debug("Stopping Qilowatt MQTT client")
        if self._update_task:
            self._update_task.cancel()
            self._update_task = None
        if self.qilowatt_client:
            await self.hass.async_add_executor_job(self.qilowatt_client.disconnect)

    def _on_command_received(self, command: WorkModeCommand):
        """Handle the WORKMODE command received from the MQTT broker."""
        _LOGGER.debug("Received WORKMODE command: %s", command)
        # Dispatch the command to Home Assistant using async_dispatcher_send
        self.hass.loop.call_soon_threadsafe(
            async_dispatcher_send,
            self.hass,
            f"{DOMAIN}_workmode_update_{self.inverter_id}",
            command,
        )

    def _on_client_error(self, error: Exception):
        """Handle the library giving up on the connection.

        Runs on the MQTT network thread. For rejected credentials, start a
        reauth flow so the user gets a repair prompt asking for new ones.
        """
        if isinstance(error, AuthenticationError):
            _LOGGER.error(
                "Qilowatt rejected the MQTT credentials for %s; asking for new ones",
                self.inverter_id,
            )
            self.hass.loop.call_soon_threadsafe(
                self.config_entry.async_start_reauth, self.hass
            )
        else:
            _LOGGER.error("Qilowatt MQTT client stopped: %s", error)

    def _on_connection_status_changed(self, connected: bool):
        """Handle MQTT connection status changes."""
        _LOGGER.debug("MQTT connection status changed: %s", connected)
        # Dispatch the connection status to Home Assistant using async_dispatcher_send
        self.hass.loop.call_soon_threadsafe(
            async_dispatcher_send,
            self.hass,
            f"{DOMAIN}_connection_status_{self.inverter_id}",
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
        """Fetch data from inverter and send to MQTT."""
        # Skip if client doesn't exist
        if not self.qilowatt_client:
            _LOGGER.debug("MQTT client not initialized, skipping data update")
            return

        # Check connection status using the connected property
        if not self.qilowatt_client.connected:
            _LOGGER.debug("MQTT client not connected, skipping data update")
            return

        # Fetch latest data from the primary inverter
        energy_data = self.inverter.get_energy_data()
        metrics_data = self.inverter.get_metrics_data()

        # Aggregate with secondary inverters if present
        if self.secondary_inverters:
            secondary_energy = []
            secondary_metrics = []
            for sec in self.secondary_inverters:
                try:
                    secondary_energy.append(sec.get_energy_data())
                    secondary_metrics.append(sec.get_metrics_data())
                except Exception as e:  # pylint: disable=broad-except
                    _LOGGER.error("Error fetching secondary inverter data: %s", e)

            if secondary_energy:
                energy_data = self._aggregate_energy_data(energy_data, secondary_energy)
            if secondary_metrics:
                metrics_data = self._aggregate_metrics_data(
                    metrics_data, secondary_metrics
                )

        # Set data in the qilowatt client
        self.qw_device.set_energy_data(energy_data)
        self.qw_device.set_metrics_data(metrics_data)

    @staticmethod
    def _aggregate_energy_data(primary, secondaries):
        """Aggregate EnergyData from primary and secondary inverters."""
        power = list(primary.Power)
        current = list(primary.Current)
        today = primary.Today
        total = primary.Total

        for sec in secondaries:
            for i in range(min(len(power), len(sec.Power))):
                power[i] += sec.Power[i]
            for i in range(min(len(current), len(sec.Current))):
                current[i] += sec.Current[i]
            today += sec.Today
            total += sec.Total

        return EnergyData(
            Power=power,
            Voltage=list(primary.Voltage),
            Current=current,
            Frequency=primary.Frequency,
            Today=today,
            Total=total,
        )

    @staticmethod
    def _aggregate_metrics_data(primary, secondaries):
        """Aggregate MetricsData from primary and secondary inverters."""
        pv_power = list(primary.PvPower)
        pv_voltage = list(primary.PvVoltage)
        pv_current = list(primary.PvCurrent)
        battery_soc = list(primary.BatterySOC)
        battery_power = list(primary.BatteryPower)
        battery_current = list(primary.BatteryCurrent)
        battery_voltage = list(primary.BatteryVoltage)
        battery_temperature = list(primary.BatteryTemperature)
        load_power = list(primary.LoadPower)
        load_current = list(primary.LoadCurrent)
        gen_voltage = list(primary.GenVoltage)
        gen_power = list(primary.GenPower)
        gen_current = list(primary.GenCurrent)
        grid_export_limit = primary.GridExportLimit

        for sec in secondaries:
            # Concatenate per-string/per-unit data
            pv_power.extend(sec.PvPower)
            pv_voltage.extend(sec.PvVoltage)
            pv_current.extend(sec.PvCurrent)
            battery_soc.extend(sec.BatterySOC)
            battery_power.extend(sec.BatteryPower)
            battery_current.extend(sec.BatteryCurrent)
            battery_voltage.extend(sec.BatteryVoltage)
            battery_temperature.extend(sec.BatteryTemperature)

            # Element-wise sum for per-phase data
            for i in range(min(len(load_power), len(sec.LoadPower))):
                load_power[i] += sec.LoadPower[i]
            for i in range(min(len(load_current), len(sec.LoadCurrent))):
                load_current[i] += sec.LoadCurrent[i]
            for i in range(min(len(gen_power), len(sec.GenPower))):
                gen_power[i] += sec.GenPower[i]
            for i in range(min(len(gen_current), len(sec.GenCurrent))):
                gen_current[i] += sec.GenCurrent[i]

            grid_export_limit += sec.GridExportLimit

        return MetricsData(
            PvPower=pv_power,
            PvVoltage=pv_voltage,
            PvCurrent=pv_current,
            BatterySOC=battery_soc,
            BatteryPower=battery_power,
            BatteryCurrent=battery_current,
            BatteryVoltage=battery_voltage,
            BatteryTemperature=battery_temperature,
            LoadPower=load_power,
            LoadCurrent=load_current,
            GenVoltage=gen_voltage,
            GenPower=gen_power,
            GenCurrent=gen_current,
            AlarmCodes=list(primary.AlarmCodes),
            InverterStatus=primary.InverterStatus,
            InverterTemperature=primary.InverterTemperature,
            GridExportLimit=grid_export_limit,
        )
