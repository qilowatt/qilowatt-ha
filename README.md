# Qilowatt Home Assistant Integration

This Home Assistant integration allows you to monitor and manage your energy consumption using Qilowatt. The integration reports your inverter data to Qilowatt. Currently you get entities that tell you which mode to set the inverter to. You have to implement actual changing in an automation. Automatically controlling your inverter will be implemented in a future release.

## Supported Inverters

The following inverters are currently implemented in this integration:
- Deye (Solar Assistant)
- Deye (Solarman) - NB! currently tested with https://github.com/davidrapan/ha-solarman adapted version
- Sofar (Homeassistant SolaX modbus) - Works only with https://github.com/wills106/homeassistant-solax-modbus
- Huawei - Requires Huawei Solar integration https://github.com/wlcrs/huawei_solar

For more information about the Qilowatt service, please visit [Qilowatt](https://qilowatt.eu).
