"""WORKMODE sensors."""

from qilowatt import WorkModeCommand

from custom_components.qilowatt.const import DATA_CLIENT, DOMAIN


def _command(**fields):
    return WorkModeCommand.from_dict({"Mode": "normal", "_source": "optimizer", **fields})


async def test_command_received_before_sensors_subscribe_is_not_lost(hass, config_entry, no_mqtt):
    """At startup the broker sends WORKMODE before the sensor platform is set up."""


    real_forward = hass.config_entries.async_forward_entry_setups

    async def forward_after_command(entry, platforms):
        client = hass.data[DOMAIN][entry.entry_id][DATA_CLIENT]
        # Arrives on the MQTT thread; handled on the loop before platforms load
        await hass.async_add_executor_job(
            client._on_command_received, _command(Mode="sell", PowerLimit=5000)
        )
        await hass.async_block_till_done()
        await real_forward(entry, platforms)

    hass.config_entries.async_forward_entry_setups = forward_after_command
    try:
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    finally:
        hass.config_entries.async_forward_entry_setups = real_forward

    assert hass.states.get("sensor.qw_mode").state == "sell"
    assert hass.states.get("sensor.qw_powerlimit").state == "5000"

    # Later commands still update the sensors
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    await hass.async_add_executor_job(client._on_command_received, _command(Mode="buy"))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.qw_mode").state == "buy"
