# CarePulse - Hardware Wiring Diagram & Setup Guide

This guide explains how to connect your **ESP32**, **MAX30100 / MAX30102 sensor**, and **DS18B20 temperature probe**, and upload the firmware to stream real sensor data to your CarePulse dashboard.

---

## 📐 Circuit Connection Diagram

```
                              +--------------------------------------+
                              |           ESP32 Dev Module           |
                              |                                      |
                              | 3V3  GND  D4   ...   D21  D22        |
                              +--+----+---+-----------+----+---------+
                                 |    |   |           |    |
        +------------------------+    |   |           |    |
        |                             |   |           |    |
        |        +--------------------+   |           |    |
        |        |                        |           |    |
        |        |   +--[ 4.7kΩ ]---------+           |    |
        |        |   |  (Resistor)                    |    |
        |        |   |                                |    |
     +--+--------+---+------+                     +---+----+---+------+
     |  RED    BLACK YELLOW |                     |  VIN  GND  SDA SCL|
     |                      |                     |                   |
     |   DS18B20 Waterproof |                     |  MAX30100/MAX30102|
     |   Temperature Probe  |                     |  Pulse Oximeter   |
     +----------------------+                     +-------------------+
```

---

## 📌 Pin-to-Pin Connection Table

### 1. MAX30100 / MAX30102 Sensor (I2C Bus)
| Sensor Pin | ESP32 Pin | Wire Color (Suggested) | Notes |
| :--- | :--- | :--- | :--- |
| **VIN / VCC** | **3V3** (3.3V) | Red | Powered by ESP32 3.3V pin |
| **GND** | **GND** | Black | Ground |
| **SCL** | **GPIO 22** (D22) | Yellow / Blue | I2C Clock line |
| **SDA** | **GPIO 21** (D21) | Green / White | I2C Data line |
| **INT / IRD / RD**| *Leave Unconnected* | - | Not required for standard polling |

> [!IMPORTANT]
> **No external pull-up resistors on SDA/SCL!**  
> Your breakout board already has onboard 4.7kΩ SMD pull-up resistors (labeled "472"). Do not add external resistors on D21 or D22.

---

### 2. DS18B20 Temperature Sensor Probe (OneWire Bus)
| Sensor Probe Wire | ESP32 Pin | Notes |
| :--- | :--- | :--- |
| **RED** (VDD / Power) | **3V3** (3.3V) | Connect to 3.3V rail |
| **BLACK** (GND) | **GND** | Connect to Ground |
| **YELLOW / BLUE** (DATA) | **GPIO 4** (D4) | Connect to GPIO 4 |
| **4.7kΩ Resistor** | **Between YELLOW (DATA) and RED (3V3)** | **Mandatory pull-up resistor** |

> [!NOTE]
> The **single 4.7kΩ resistor** between the DS18B20 data wire (GPIO 4) and 3.3V is the **only external resistor needed in this entire circuit**.

---

## 🔍 The MAX30100 vs MAX30102 Diagnosis & Fix

### Why did your sensor return "NOT FOUND" previously?
Your breakout board silkscreen reads **"MAX30100/30102"**.
1. Raw I2C scan returned **Address 0x57 (Success code 0)**. This proved your wiring and power are 100% good!
2. The SparkFun library failed `.begin()` because SparkFun's library is specifically hardcoded to check for a **MAX30102 Part ID (`0x15`)**.
3. Dual-purpose breakout boards commonly have the **MAX30100** chip soldered on (Part ID `0x11`). When SparkFun reads `0x11` instead of `0x15`, it returns `FALSE` ("Sensor not found") even though the chip is alive and working.
4. **The Solution**: We use the dedicated **MAX30100lib** by OXullo Intersecans (`MAX30100_PulseOximeter.h`), which recognizes the MAX30100 registers correctly.

---

## 💻 Arduino IDE Setup Instructions (Step-by-Step)

### Step 1: Install ESP32 Board Support (if not already installed)
1. Open **Arduino IDE**.
2. Go to **File > Preferences**.
3. In "Additional Board Manager URLs", paste:
   ```text
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
4. Click **OK**.
5. Go to **Tools > Board > Boards Manager...**, search for **ESP32** by Espressif Systems, and click **Install**.

### Step 2: Install the 3 Required Arduino Libraries
Go to **Sketch > Include Library > Manage Libraries...**, and install:
1. **`MAX30100lib`** by *OXullo Intersecans* (install version 1.2.1).
2. **`DallasTemperature`** by *Miles Burton*.
3. **`OneWire`** by *Paul Stoffregen*.

### Step 3: Open the Firmware Sketch
1. Open the file:  
   📂 [`CarePulse_ESP32.ino`](CarePulse_ESP32.ino) in Arduino IDE.
2. Update your Wi-Fi credentials at the top of the file:
   ```cpp
   const char* ssid     = "YOUR_WIFI_NAME";
   const char* password = "YOUR_WIFI_PASSWORD";
   ```
3. Verify the CarePulse server URL:
   ```cpp
   // Your computer's local Wi-Fi IP address:
   const char* serverUrl = "http://10.208.74.225:5000/api/sensor-data";
   ```
   *(If your computer's IP address ever changes, check it using `ipconfig` in Command Prompt and update this string).*

### Step 4: Upload to the ESP32
1. Connect the ESP32 to your PC using a micro-USB cable.
2. In Arduino IDE, select:
   - **Tools > Board > ESP32 Arduino > ESP32 Dev Module**
   - **Tools > Port > (Select your CP2102 COM Port, e.g. COM3 or COM4)**
   - **Tools > Upload Speed > 115200**
3. Click the **Upload** arrow button (top left).  
   *(If the IDE says `Connecting......`, hold down the **BOOT** button on the ESP32 for 2 seconds until uploading begins).*

---

## 📡 Verification: Watching Live Data on CarePulse

1. Once uploaded, open **Tools > Serial Monitor** in Arduino IDE (set baud rate to **115200**).
2. You will see:
   ```text
   [CarePulse] Connecting to Wi-Fi... Connected! IP: 10.208.74.xxx
   [CarePulse] Checking I2C Bus at 0x57...
   [CarePulse] MAX30100 initialized successfully!
   [CarePulse] DS18B20 Temperature sensor ready!
   [CarePulse] Streaming telemetry to http://10.208.74.225:5000/api/sensor-data
   POST Payload: {"device_id":"ESP32-001","patient_id":"P001","heart_rate":74,"spo2":98,"temperature":36.5,"data_source":"ESP32"}
   Server Response: HTTP 201 - OK
   ```
3. Open your browser and go to: **[http://127.0.0.1:5000/dashboard](http://127.0.0.1:5000/dashboard)**
4. Notice:
   - The top banner switches to: **`🟢 LIVE HARDWARE (ESP32)`**.
   - The Vital Cards show: **`🟢 ESP32 LIVE`**.
   - The Device Status card shows: **`🟢 CONNECTED (Live Telemetry)`**.
   - Place your finger gently on the MAX30100 sensor and hold the DS18B20 probe to see your actual heartbeat and body temperature stream live into your CarePulse dashboard!
