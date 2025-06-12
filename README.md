# Qilowatt Home Assistant Integration

This Home Assistant integration allows you to monitor and manage your energy consumption using Qilowatt. The integration reports your inverter data to Qilowatt. Currently you get entities that tell you which mode to set the inverter to. You have to implement actual changing in an automation. Automatically controlling your inverter will be implemented in a future release.

## Supported Inverters

The following inverters are currently implemented in this integration:
- Deye (Solar Assistant)
- Deye (Solarman) - NB! currently tested with https://github.com/davidrapan/ha-solarman adapted version
- Sofar (Homeassistant SolaX modbus) - Works only with https://github.com/wills106/homeassistant-solax-modbus
- Huawei - Requires Huawei Solar integration https://github.com/wlcrs/huawei_solar. For Inverter pick any Deye inverter, e.g. Deye HV inverter.

## Modes

        normal - Self use. PV to Load and Battery, if PV < Load use Battery. If battery is full  PV to Load and Grid.
        savebattery - PV to Load and Battery, battery can be charged but no discharge. If PV < Load use Grid.
        pvsell - PV to Load and Grid.     
        sell - PV and Battery to Load and Grid.
        buy - Grid and PV to battery and load. 
        limitexport - Limit export to Grid even battery is full (negative NPS price).
        nobattery -  Disable battery usage (optimizer not using it).

## Source
        fusebox - mFRR clients must respond to commands. Modes can be buy or sell and Power limit is activated power (always positive value).
        optimizer - AI managed commands. Modes can be normal, savebattery, pvsell, sell, buy and limitexport.
        timer - Using manualy created timers. Modes can be normal, savebattery, pvsell, sell, buy, limitexport and nobattery.

## Power limit 
        Always is positive value requested power for command.

For more information about the Qilowatt service, please visit [Qilowatt](https://qilowatt.eu).
