# Qilowatt Home Assistant Integration: Installation and User Guide

This guide provides a comprehensive walkthrough for installing, configuring, and using the Qilowatt Home Assistant integration. It is designed for users who want to connect their Home Assistant-controlled energy system to the Qilowatt platform for services like the mFRR balancing market, without using a physical Qilowatt hardware device.

This document is a community effort, based on the collective knowledge and best practices shared within the official Qilowatt Discord channels.

---

## 1. Prerequisites

Before you begin, ensure you have the following:

1.  **A working Home Assistant installation.**
2.  **HACS (Home Assistant Community Store)** installed and operational.
3.  **A supported and controllable inverter integrated into Home Assistant.** You must be able to see its data (e.g., battery SOC, power) and, most importantly, **be able to change its settings** (e.g., work mode, charge/discharge power) from within Home Assistant. Without this, you cannot act on commands from Qilowatt.

#### Supported Inverter Integrations
The `qilowatt-ha` integration relies on existing HA integrations to discover and read data from your inverter. Supported integrations include:

-   **Deye:**
    -   Via **Solar Assistant**.
    -   Via **Solarman**: The community strongly recommends the [davidrapan/ha-solarman](https://github.com/davidrapan/ha-solarman) version for reliability.
    -   Via **ESPHome**: An [example configuration](https://github.com/qilowatt/qilowatt-ha/blob/main/examples/esphome-lilygo-tcan485.yaml) is available.
-   **Sofar:**
    -   Via **SolaX Modbus**: Requires the [wills106/homeassistant-solax-modbus](https://github.com/wills106/homeassistant-solax-modbus) integration.
    -   Via **Solarman**: Works with adapted version from [davidrapan/ha-solarman](https://github.com/davidrapan/ha-solarman) (Pending pull request: https://github.com/davidrapan/ha-solarman/pull/759/files)
-   **Huawei:**
    -   Via **Huawei Solar**: Requires the [wlcrs/huawei_solar](https://github.com/wlcrs/huawei_solar) integration.
-   **Victron:**
    -   Via **Victron for QW**: - Requires https://github.com/mnuxx/victron_qw_addon

---

## 2. Step-by-Step Installation

### Step 1: Create a Qilowatt Account & Get MQTT Credentials
The integration communicates with Qilowatt's servers via MQTT. You will need unique credentials for this.

1.  Go to **[https://app.qilowatt.it](https://app.qilowatt.it)** and create a new user account.
    *   **Important:** Make sure you are on the `app.` subdomain, not the Qilowatt e-shop.
2.  Contact Qilowatt support to request your MQTT credentials. You can reach out to the support team through their official Discord server or other available support channels.
3.  In your message, provide the email address you used to register on `app.qilowatt.it`.
4.  You will receive a **username**, **password**, and a device **serial number**.

### Step 2: Install the Integration via HACS
1.  In your Home Assistant, navigate to **HACS**.
2.  Go to `Integrations`, click the three dots in the top-right corner, and select **`Custom repositories`**.
3.  Add the repository URL: `https://github.com/qilowatt/qilowatt-ha`
4.  Select the category `Integration` and click **`Add`**.
5.  Find the new "Qilowatt" integration in your HACS list and install it.
6.  **Restart Home Assistant** to load the integration.

### Step 3: Configure the Integration in Home Assistant
1.  Navigate to `Settings` > `Devices & Services` and click **`Add Integration`**.
2.  Search for "Qilowatt" and select it.
3.  A configuration window will appear. Enter the credentials you received:
    -   **Username:** Your provided MQTT username.
    -   **Password:** Your provided MQTT password.
    -   **Qilowatt inverter ID:** This is the **serial number** you were given.
4.  On the next screen, the integration will auto-discover supported inverter integrations already present in your Home Assistant. **Select your primary inverter** from the list.
5.  Complete the setup process.

### Step 4: Configure the Qilowatt Web UI (CRITICAL STEP)
This step is essential. If you skip it, the sensors in Home Assistant will remain in an "Unknown" state.

1.  Log in to **[https://app.qilowatt.it](https://app.qilowatt.it)**.
2.  Go to "My Devices" and find the device associated with your serial number.
3.  Set the `Hardware Type` to **`MQTT`**.
4.  Fill in the details for your inverter and solar array under the "Inverters" and "Solar Plants" sections.
5.  **Activate your Trial Subscription** for the device.
6.  **Create at least one timer.** This is the most common reason for setup failure. Without an active timer or optimizer, the Qilowatt backend will not send any commands, and your HA sensors will not initialize.
    -   **Rule:** The timers must cover the entire 24-hour day.
    -   **For testing:** Create a single timer from `00:00` to `23:59` with the mode set to `Normal`. Save and activate it.

After a few minutes, your Qilowatt sensors in Home Assistant should start showing data.

---

## 3. Controlling Your Inverter with Automations

The Qilowatt integration **does not directly control your inverter**. It provides a set of sensors that reflect the commands sent by Qilowatt. You must create your own automations in Home Assistant to act on these sensor changes.

### Key Sensors for Automation
-   `sensor.qw_mode`: The current command (`normal`, `buy`, `sell`, `frrup`, etc.).
-   `sensor.qw_source`: The origin of the command (`timer`, `fusebox`, `optimizer`).
-   `sensor.qw_powerlimit`: The target power in Watts (always a positive value).
-   `binary_sensor.qw_connected`: Shows the status of the MQTT connection to Qilowatt. Use this to build failsafe automations (e.g., revert to a safe mode if the connection is lost).

### Recommended Automation Pattern: "Desired State"
Sending multiple commands to an inverter in quick succession can cause some to be missed. The community has developed a robust pattern using HA `helpers` to ensure reliability.

**The Logic:**
1.  **Create `helpers`:** For each inverter setting you need to control (work mode, charge current, etc.), create a corresponding helper in HA (e.g., `input_select.deye_desired_work_mode`, `input_number.deye_desired_charge_current`).
2.  **Automation 1 (QW -> Helper):** Your main automation that triggers on `qw_mode` changes should **only modify the state of these helpers**, not the inverter directly.
3.  **Automation 2 (Helper -> Inverter):** A separate automation triggers periodically (e.g., every minute) and whenever a helper's state changes. It compares the helper's "desired state" with the inverter's "actual state." If they don't match, it sends the command to the inverter.

This pattern ensures that commands are persistent and will be re-sent until the inverter correctly reports the desired state.

**Example Automations (replace entity IDs with your own):**
-   **Automation 1 (QW -> Helper):** [https://pastebin.com/t0wbZYQM](https://pastebin.com/t0wbZYQM)
-   **Automation 2 (Helper -> Inverter):** [https://pastebin.com/7LFrY3Cs](https://pastebin.com/7LFrY3Cs)
-   **Optional Power Fine-Tuning Automation:** [https://pastebin.com/pYygtW33](https://pastebin.com/pYygtW33)

---

## 4. Automation Reference: Modes and Sources

Use the following information from the official README to build your automation logic.

### Modes
-   `normal`: Self-use mode. PV powers the load and charges the battery. The battery is used if PV is insufficient. Excess PV is exported to the grid if the battery is full.
-   `savebattery`: PV powers the load and can charge the battery, but the battery will not discharge. The grid is used if PV is insufficient.
-   `pvsell`: PV powers the load, and all excess is exported to the grid. The battery is not used.
-   `sell`: Both PV and the Battery are used to power the load and export to the grid. In this mode set battery max discharge current in accordance to PowerLimit.
-   `frrup`: In this mode you need to set your grid max sell power to PowerLimit and battery output power to max.
-   `frrdown`: In this mode you need to take energy from grid set by PowerLimit. For Deye, use Grid Peak Shaving for this. Set max battery and grid charge currents to max.
-   `buy`: Grid and PV are used to charge the battery and power the load. In this mode set battery max charge and grid charge currents in accordance to PowerLimit.
-   `limitexport`: Limits export to the grid, even if the battery is full (useful for negative NPS prices).
-   `nobattery`: Disables battery usage completely.

### Source
-   `fusebox`: A command from the mFRR market. **These commands are mandatory and have the highest priority.**
-   `kratt`: A command from the mFRR market. **These commands are mandatory and have the highest priority.**
-   `optimizer`: An AI-managed command from the Qilowatt Optimizer.
-   `timer`: A command from a manually created timer in the Qilowatt UI.
-   `manual`: A command triggered manually from the Qilowatt UI.

---

## 5. Troubleshooting & Common Issues

-   **Sensors are "Unknown":** This is the most common issue. The cause is almost always an inactive timer or subscription in the Qilowatt web UI. See **Step 4** and ensure you have an active trial/subscription and a 24/7 timer running.
-   **Inverter Not Responding:** Double-check all `entity_id`s in your automations. Implement the "Desired State" pattern for reliability. Some Deye inverters occasionally require a physical restart to resolve communication issues.
-   **Unstable Wi-Fi Dongle (Solarman):** The standard Wi-Fi dongles are notoriously unreliable for control, as they try to communicate with the cloud simultaneously. The community's universal recommendation is to switch to a **wired RS485 connection**, using either an RS485-to-USB or RS485-to-Ethernet adapter.
-   **Battery Power is Reversed (+/- signs wrong):** Some inverter integrations report charging as negative and discharging as positive, or vice-versa. Check the "bubbles" on the Qilowatt web UI to see if energy is flowing in the correct direction. If not, create a `template sensor` in HA that multiplies your battery power entity by `-1` and use that template sensor in the Qilowatt integration setup.
