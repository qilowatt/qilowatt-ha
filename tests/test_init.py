"""Setup, migration and runtime auth-failure handling."""

import asyncio
import threading
import time
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry
from qilowatt import AuthenticationError

from custom_components.qilowatt.const import DATA_CLIENT, DOMAIN
from custom_components.qilowatt.mqtt_client import (
    CannotConnect,
    InvalidAuth,
    async_validate_credentials,
)

from .conftest import entry_data


async def test_unreachable_broker_retries_setup(hass, config_entry):
    with patch(
        "custom_components.qilowatt.mqtt_client.MQTTClient.start",
        side_effect=ConfigEntryNotReady("broker down"),
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    assert config_entry.state is config_entries.ConfigEntryState.SETUP_RETRY


async def test_connect_oserror_becomes_config_entry_not_ready(hass, config_entry):
    """The wrapper turns a socket-level failure from paho into ConfigEntryNotReady."""
    from custom_components.qilowatt.mqtt_client import MQTTClient

    client = MQTTClient(hass, config_entry)
    with patch.object(client, "initialize_client"):
        class FakeQw:
            def connect(self):
                raise OSError("Network is unreachable")

        client.qilowatt_client = FakeQw()
        with pytest.raises(ConfigEntryNotReady):
            await client.start()


async def test_rejected_credentials_start_reauth(hass, config_entry, no_mqtt):
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]

    # The library calls this from its network thread
    await hass.async_add_executor_job(
        client._on_client_error, AuthenticationError("Authentication failed after 2 retries")
    )
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == config_entries.SOURCE_REAUTH
    assert flows[0]["context"]["entry_id"] == config_entry.entry_id


async def test_migration_v2_to_v3_sets_unique_id(hass, solarman_device, no_mqtt):
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data(solarman_device.id), version=2)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.version == 3
    assert entry.unique_id == "QW123"
    assert entry.state is config_entries.ConfigEntryState.LOADED


async def test_migration_refuses_downgrade(hass, solarman_device, no_mqtt):
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data(solarman_device.id), version=4)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.MIGRATION_ERROR


class FakeQilowattClient:
    """Stand-in for QilowattMQTTClient that reports a scripted outcome on connect."""

    outcome = None  # "ok", "auth", "silent" or an exception instance
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._conn = []
        self._err = []
        self.disconnected = False
        self.connect_finished = threading.Event()
        FakeQilowattClient.instances.append(self)

    def add_connection_callback(self, cb):
        self._conn.append(cb)

    def add_error_callback(self, cb):
        self._err.append(cb)

    def connect(self):
        try:
            if isinstance(self.outcome, Exception):
                raise self.outcome
            if self.outcome == "stall":
                # Blocking DNS/TCP/TLS that takes longer than the deadline
                time.sleep(0.3)
                return
            if self.outcome == "ok":
                for cb in self._conn:
                    cb(True)
            elif self.outcome == "auth":
                for cb in self._err:
                    cb(AuthenticationError("Authentication failed"))
        finally:
            self.connect_finished.set()

    def disconnect(self):
        # Like the real client: disconnect() takes the lock that connect()
        # holds, so it cannot complete until a stalled connect() returns.
        self.connect_finished.wait(timeout=2.0)
        self.disconnected = True


@pytest.fixture
def fake_qw():
    FakeQilowattClient.instances.clear()
    with patch("custom_components.qilowatt.mqtt_client.QilowattMQTTClient", FakeQilowattClient):
        yield FakeQilowattClient


async def test_validate_credentials_accepts(hass, fake_qw):
    fake_qw.outcome = "ok"
    await async_validate_credentials(hass, "u", "p", "QW123")
    client = fake_qw.instances[-1]
    assert client.kwargs["max_auth_retries"] == 0
    assert client.disconnected


async def test_validate_credentials_rejected(hass, fake_qw):
    fake_qw.outcome = "auth"
    with pytest.raises(InvalidAuth):
        await async_validate_credentials(hass, "u", "p", "QW123")
    assert fake_qw.instances[-1].disconnected


async def test_validate_credentials_unreachable(hass, fake_qw):
    fake_qw.outcome = OSError("no route")
    with pytest.raises(CannotConnect):
        await async_validate_credentials(hass, "u", "p", "QW123")


async def test_validate_credentials_times_out(hass, fake_qw):
    fake_qw.outcome = "silent"
    with patch("custom_components.qilowatt.mqtt_client.VALIDATE_TIMEOUT", 0.05):
        with pytest.raises(CannotConnect):
            await async_validate_credentials(hass, "u", "p", "QW123")
    # On a timeout the cleanup is deliberately not awaited by the caller
    await hass.async_block_till_done(wait_background_tasks=True)
    assert fake_qw.instances[-1].disconnected


async def test_validate_credentials_deadline_covers_blocking_connect(hass, fake_qw):
    """A stalled connect() must not hold the form past VALIDATE_TIMEOUT."""
    fake_qw.outcome = "stall"
    with patch("custom_components.qilowatt.mqtt_client.VALIDATE_TIMEOUT", 0.05):
        started = time.monotonic()
        with pytest.raises(CannotConnect):
            await async_validate_credentials(hass, "u", "p", "QW123")
        elapsed = time.monotonic() - started
    assert elapsed < 0.25, f"form waited {elapsed:.2f}s for a stalled connect"

    # The client created inside the stalled executor job is still cleaned up
    await hass.async_block_till_done(wait_background_tasks=True)
    assert fake_qw.instances[-1].disconnected


async def test_homeassistant_stop_stops_publishing_before_unload(hass, config_entry):
    """Shutdown stops the timers at EVENT_HOMEASSISTANT_STOP, not at (the never
    happening) unload, so no read can see entities other integrations have
    already marked unavailable."""
    FakeQilowattClient.instances.clear()
    FakeQilowattClient.outcome = "ok"
    with patch("custom_components.qilowatt.mqtt_client.QilowattMQTTClient", FakeQilowattClient):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
        assert client.qw_device._sensor_timer_thread is not None

        hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
        await hass.async_block_till_done()

        assert FakeQilowattClient.instances[0].disconnected
        assert client.qw_device._sensor_timer_thread is None
        assert config_entry.state is config_entries.ConfigEntryState.LOADED

        # A later unload (or a second stop) must still be harmless
        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
