"""Constants for the Qilowatt integration."""

DOMAIN = "qilowatt"
DATA_CLIENT = "client"
CONF_DEVICE_TYPE = "device_type"
CONF_DEVICE_MODEL = "device_model"
CONF_QILOWATT_DEVICE_ID = "qilowatt_device_id"
CONF_MQTT_USERNAME = "mqtt_username"
CONF_MQTT_PASSWORD = "mqtt_password"
CONF_DEVICE_ID = "device_id"

# Legacy constants for migration
CONF_INVERTER_MODEL = "inverter_model"
CONF_INVERTER_ID = "inverter_id"

# Device types
DEVICE_TYPE_INVERTER = "inverter"
DEVICE_TYPE_SWITCH = "switch"

DEVICE_TYPES = [DEVICE_TYPE_INVERTER, DEVICE_TYPE_SWITCH]
