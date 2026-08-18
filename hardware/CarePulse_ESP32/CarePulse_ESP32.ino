/***************************************************
 * CarePulse - ESP32 Health Monitoring Firmware
 * Dual-Streaming: Blynk Cloud + Local CarePulse Server
 *
 * Sensors:
 *   MAX30100 -> Heart Rate + SpO2 (I2C: SDA=21, SCL=22)
 *   DS18B20  -> Temperature (DATA=GPIO 4 with 4.7k pull-up)
 ****************************************************/

// ==================================================
// 1. BLYNK CONFIGURATION
// ==================================================
#define BLYNK_TEMPLATE_ID "TMPL3TrC9KP57"
#define BLYNK_TEMPLATE_NAME "CarePulse"
#define BLYNK_AUTH_TOKEN "t3A72ofBbSYnV7wVs3V35Ez8LYrieLQ4"
#define BLYNK_PRINT Serial

// ==================================================
// 2. LIBRARIES
// ==================================================
#include <WiFi.h>
#include <HTTPClient.h>
#include <BlynkSimpleEsp32.h>
#include <Wire.h>
#include "MAX30100_PulseOximeter.h"
#include <OneWire.h>
#include <DallasTemperature.h>

// ==================================================
// 3. WIFI & SERVER CONFIGURATION
// ==================================================
char ssid[] = "motorola edge 40";
char pass[] = "password";

// Your computer's current local Wi-Fi IP address (Check via 'ipconfig' in command prompt)
const char* serverUrl = "http://10.115.14.225:5000/api/sensor-data";
const char* deviceId  = "ESP32-001";
const char* patientId = "P001";

// ==================================================
// 4. SENSORS & DUAL-CORE TASK
// ==================================================
PulseOximeter pox;
bool max30100OK = false;

#define ONE_WIRE_BUS 4
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature tempSensor(&oneWire);

volatile float latestTempC = DEVICE_DISCONNECTED_C;
bool dsOK = false;
TaskHandle_t tempTaskHandle = NULL;
BlynkTimer timer;

void onBeatDetected() {
  Serial.println("Beat detected!");
}

// Background task running on Core 0 (keeps DS18B20 off Core 1)
void tempTask(void *parameter) {
  for (;;) {
    if (dsOK) {
      tempSensor.requestTemperatures();
      float t = tempSensor.getTempCByIndex(0);
      latestTempC = t;
    }
    vTaskDelay(2000 / portTICK_PERIOD_MS);
  }
}

// ==================================================
// 5. SEND DATA (TO BLYNK + CAREPULSE SERVER)
// ==================================================
void sendData() {
  float temperature = latestTempC;
  float heartRate   = pox.getHeartRate();
  int   spo2        = pox.getSpO2();

  // 1. Send to Blynk
  if (temperature != DEVICE_DISCONNECTED_C) {
    Blynk.virtualWrite(V0, temperature);
  }
  Blynk.virtualWrite(V1, heartRate);
  Blynk.virtualWrite(V2, spo2);

  // 2. Print to Serial Monitor
  Serial.print("[Sensor Data] HR: ");
  Serial.print(heartRate, 1);
  Serial.print(" bpm | SpO2: ");
  Serial.print(spo2);
  Serial.print(" % | Temp: ");
  if (temperature == DEVICE_DISCONNECTED_C || temperature <= -50.0) {
    Serial.println("DISCONNECTED (Error)");
  } else {
    Serial.print(temperature, 1);
    Serial.println(" C");
  }

  // 3. Smart Validation: Only stream genuine readings to CarePulse server
  if (WiFi.status() == WL_CONNECTED) {
    // Check if finger is actually detected
    if (heartRate <= 20.0 || spo2 <= 50) {
      Serial.println("  -> [MAX30100/102] Waiting for finger on sensor (Zero readings rejected)");
      return;
    }

    // Check if temperature sensor is connected
    if (temperature == DEVICE_DISCONNECTED_C || temperature <= -50.0 || temperature >= 85.0) {
      Serial.println("  -> [DS18B20] Sensor disconnected! Real temperature reading required.");
      return;
    }

    HTTPClient http;
    http.begin(serverUrl);
    http.addHeader("Content-Type", "application/json");

    String json = "{";
    json += "\"device_id\":\""   + String(deviceId)    + "\",";
    json += "\"patient_id\":\""  + String(patientId)   + "\",";
    json += "\"heart_rate\":"    + String(heartRate, 1)+ ",";
    json += "\"spo2\":"          + String(spo2)        + ",";
    json += "\"temperature\":"   + String(temperature, 1)+ ",";
    json += "\"data_source\":\"ESP32\"";
    json += "}";

    int code = http.POST(json);
    if (code > 0) {
      Serial.printf("  -> [CarePulse Server] Sync OK (HTTP %d)\n", code);
    } else {
      Serial.printf("  -> [CarePulse Server] Failed: %s\n", http.errorToString(code).c_str());
    }
    http.end();
  }
}

// ==================================================
// 6. SETUP
// ==================================================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n==================================");
  Serial.println("      CarePulse Health Monitor    ");
  Serial.println("==================================");

  // Start I2C (SDA=21, SCL=22)
  Wire.begin(21, 22);

  // Connect to Blynk and WiFi
  Serial.println("Connecting to WiFi and Blynk...");
  Blynk.begin(BLYNK_AUTH_TOKEN, ssid, pass);
  Serial.println("Blynk connected!");

  // Initialize MAX30100 (7.6mA LED current)
  Serial.print("Checking MAX30100... ");
  if (pox.begin()) {
    max30100OK = true;
    Serial.println("FOUND");
    pox.setIRLedCurrent(MAX30100_LED_CURR_7_6MA);
    pox.setOnBeatDetectedCallback(onBeatDetected);
  } else {
    Serial.println("NOT FOUND! Check wiring.");
  }

  // Initialize DS18B20
  Serial.print("Checking DS18B20... ");
  tempSensor.begin();
  int deviceCount = tempSensor.getDeviceCount();
  if (deviceCount > 0) {
    dsOK = true;
    Serial.print("FOUND (");
    Serial.print(deviceCount);
    Serial.println(" device(s))");

    // Pin temperature reading task to Core 0
    xTaskCreatePinnedToCore(tempTask, "TempTask", 4096, NULL, 1, &tempTaskHandle, 0);
  } else {
    Serial.println("NOT FOUND! Check 4.7k resistor on D4.");
  }

  // Send readings every 1 second
  timer.setInterval(1000L, sendData);

  Serial.println("Starting live stream...\n");
}

// ==================================================
// 7. LOOP
// ==================================================
void loop() {
  if (max30100OK) {
    pox.update();
  }
  Blynk.run();
  timer.run();
}