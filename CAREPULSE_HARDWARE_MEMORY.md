# CarePulse – Project Memory & Real Hardware Integration Context

## 1. Project Overview & Architecture
- **Project Name:** CarePulse – Healthcare IoT Monitoring System
- **Location:** `C:\Users\athir\Downloads\CarePulse` (or root project folder when transferred).
- **Stack:**
  - **Frontend:** HTML5, CSS3, JavaScript (Bootstrap 5, FontAwesome, Chart.js).
  - **Backend:** Python 3 (Flask), utilizing SQLite (`carepulse.db`) via `database.py` with seamless SQLite fallback.
  - **IoT Controller:** ESP32 Dev Module (Xtensa Dual-Core).
  - **Sensors:**
    - **MAX30100 / MAX30102:** Pulse Oximeter & Heart Rate (I2C: SDA=GPIO 21, SCL=GPIO 22).
    - **DS18B20:** High-precision Temperature Probe (OneWire: DATA=GPIO 4 with 4.7kΩ pull-up to 3.3V).
  - **Alerting:** Automated Gmail SMTP email dispatch (`email_service.py`) with hysteresis de-duplication to prevent spamming caregivers.
  - **Strict Rule:** **ZERO DEMO MODE / NO SIMULATORS**. All live data must originate from physical ESP32 hardware via HTTP POST to `/api/sensor-data`. Stale data (>10s) renders as "Device Offline" (`--`).

---

## 2. Real Hardware Connection Details & History

### A. Physical Pin Connections
```
ESP32 Dev Module
 ├── 3V3  ────────► MAX30100/102 VIN  &  DS18B20 RED (Power)
 ├── GND  ────────► MAX30100/102 GND  &  DS18B20 BLACK (Ground)
 ├── GPIO 21 (D21) ► MAX30100/102 SDA (I2C Data)
 ├── GPIO 22 (D22) ► MAX30100/102 SCL (I2C Clock)
 └── GPIO 4  (D4)  ► DS18B20 YELLOW/BLUE (DATA)
                          │
                   [ 4.7kΩ Resistor ]
                          │
                     Connected to 3V3
```
*Note: MAX30100/102 breakout board already has onboard 4.7kΩ pull-up resistors on SDA/SCL. Do NOT add external resistors to D21/D22. Only GPIO 4 requires the 4.7kΩ pull-up resistor.*

---

### B. Hardware Sensor Diagnosis & Discoveries
1. **MAX30100 vs MAX30102 Breakout Boards:**
   - The user's sensor board silkscreen is labeled `"MAX30100/MAX30102"`.
   - Running raw I2C scans confirmed the device responds at address `0x57`.
   - The standard SparkFun MAX3010x library failed because it looks strictly for Part ID `0x15` (MAX30102). Many dual-labeled boards actually mount the MAX30100 chip (Part ID `0x11`).
   - **Solution:** We used the `MAX30100lib` library by *OXullo Intersecans* (`MAX30100_PulseOximeter.h`), which successfully initialized the chip and detected beats.

2. **DS18B20 FreeRTOS Dual-Core Requirement:**
   - The `OneWire` and `DallasTemperature` bit-banging library blocks CPU execution for up to 750ms while converting temperatures.
   - Running temperature conversion in the main Arduino `loop()` starved the MAX30100 FIFO buffer, causing I2C buffer overruns and missing heartbeats.
   - **Solution:** We decoupled reading into a FreeRTOS task pinned to **Core 0** (`tempTask`), leaving **Core 1** to process `pox.update()` continuously at high frequency.

3. **Validation & Zero-Reading Filtering:**
   - When a finger is removed, the sensor outputs `0.0 BPM` and `0% SpO2`.
   - In `CarePulse_ESP32.ino`, we filter out readings where `heartRate <= 20` or `spo2 <= 50`, printing `Waiting for finger on sensor` to Serial and suppressing HTTP transmission so the database is never polluted with fake 0 readings.
   - When the DS18B20 probe is unplugged, it reads `-127.0°C`. The firmware and backend both reject `<= -50°C` or `>= 85°C` as `SENSOR_DISCONNECTED`.

---

### C. Network & HTTP POST Troubleshooting (Crucial Context)
When the ESP32 attempted to send HTTP POST packets to the Flask backend, the Serial Monitor reported:
```
[Sensor Data] HR: 78.0 bpm | SpO2: 98 % | Temp: 36.6 C
  -> [CarePulse Server] Failed: connection refused
```
#### Why this happened & how to handle on any new device:
1. **Server Host Binding:**
   - Flask must run on `app.run(host='0.0.0.0', port=5000)`, NOT `127.0.0.1` or `localhost`. Binding to `0.0.0.0` allows connections from external LAN devices like the ESP32.
2. **Dynamic Wi-Fi IP Matching:**
   - The ESP32 firmware line 36 has `serverUrl`:
     ```cpp
     const char* serverUrl = "http://<YOUR_PC_WIFI_IP>:5000/api/sensor-data";
     ```
   - When switching laptops or connecting to a mobile hotspot (e.g. Motorola Edge 40), the PC's Wi-Fi IP changes (e.g. `10.84.245.225` vs `10.208.74.225` vs `192.168.1.x`).
   - Always run `ipconfig` on the PC and update line 36 in `CarePulse_ESP32.ino` before flashing.
3. **Firewall / Antivirus Port Blocking:**
   - Windows Defender Firewall blocks incoming TCP Port 5000 by default. Add rule via Admin PowerShell:
     ```powershell
     New-NetFirewallRule -DisplayName "CarePulse Flask Port 5000" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
     ```
   - **Third-Party Antivirus (McAfee, Norton, etc.):** If installed, it overrides Windows Firewall and causes an immediate `connection refused`. Temporarily disable third-party firewall or create a custom inbound allow rule for TCP Port 5000.

---

## 3. Key Files & Working Modules
- `app.py`:
  - Main web server and controllers.
  - `/patient-login`, `/caregiver-login`, `/patient-register`, `/caregiver-register`.
  - `/dashboard`: Patient live dashboard with 10s freshness.
  - `/caregiver-dashboard`: Dedicated caregiver view with assigned patients.
  - `POST /api/sensor-data`: Real hardware ingestion with biometric range validation.
  - `GET /api/live-data` & `GET /api/device-status`.
- `models.py`:
  - `UserModel`, `PatientModel`, `CaregiverModel`, `DeviceModel`, `SensorModel`, `AlertModel`, `ThresholdModel`.
  - Password hashing with bcrypt.
- `email_service.py`:
  - Gmail SMTP alerting via port 587 with STARTTLS.
  - Stateful vital tracking (`_vital_states`) for hysteresis (sends on first breach, suppresses repeat alerts until normalized).
- `hardware/CarePulse_ESP32/CarePulse_ESP32.ino`:
  - Working dual-core firmware for MAX30100/102 and DS18B20 with HTTP POST ingestion.
- `test_carepulse.py`:
  - 10 automated test suites covering public pages, auth, 14 authenticated views, hardware staleness, sensor validation, alert resolution, and caregiver dispatch. Run with `python test_carepulse.py`.

---

## 4. How to Run on a New Device
1. Install Python 3.10+ and install requirements: `pip install flask bcrypt pymysql cryptography`.
2. Connect both the laptop and the ESP32 to the **same Wi-Fi or mobile hotspot**.
3. Run `ipconfig` in Command Prompt to find the laptop's IPv4 Address.
4. Set line 36 in `hardware/CarePulse_ESP32/CarePulse_ESP32.ino` to `http://<YOUR_IP>:5000/api/sensor-data`.
5. Flash the ESP32 in Arduino IDE.
6. Run the Flask server:
   ```bash
   python app.py
   ```
7. Allow Port 5000 through the firewall.
8. Access web dashboard at `http://127.0.0.1:5000`.
