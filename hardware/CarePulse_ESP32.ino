/***************************************************
 * CarePulse - ESP32 Health Monitoring Firmware
 *
 * Sensors:
 *   MAX30100 -> Heart Rate + SpO2 (I2C: SDA=GPIO 21, SCL=GPIO 22)
 *   DS18B20  -> Body Temperature  (OneWire: DATA=GPIO 4, 4.7k pull-up)
 *
 * Server:
 *   POST https://unit-pelt-unusable.ngrok-free.dev/api/sensor-data
 *
 * Libraries required (install via Arduino Library Manager):
 *   1. MAX30100lib       by OXullo Intersecans (v1.2.1)
 *   2. DallasTemperature by Miles Burton
 *   3. OneWire           by Paul Stoffregen
 ****************************************************/

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include "MAX30100_PulseOximeter.h"
#include <OneWire.h>
#include <DallasTemperature.h>

// ==================================================
// 1. CONFIGURATION
// ==================================================
const char* ssid     = "CMF by Nothing Phone 2 Pro_6901";
const char* password = "12345678";

const char* serverUrl = "https://unit-pelt-unusable.ngrok-free.dev/api/sensor-data";
const char* deviceId  = "ESP32-001";
const char* patientId = "P001";

// ==================================================
// 2. SENSOR OBJECTS
// ==================================================
PulseOximeter pox;
bool max30100OK = false;

#define ONE_WIRE_BUS 4
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature tempSensor(&oneWire);
bool dsOK = false;

volatile float latestTempC = DEVICE_DISCONNECTED_C;
TaskHandle_t tempTaskHandle = NULL;

unsigned long lastSendTime = 0;
const unsigned long SEND_INTERVAL = 3000;

// ==================================================
// 3. CALLBACKS
// ==================================================
void onBeatDetected() {
  Serial.println("[CarePulse] ♥ Beat detected!");
}

// ==================================================
// 4. TEMPERATURE TASK (runs on Core 0)
//    DS18B20 is slow & blocking. Isolating it on
//    Core 0 prevents it from starving the MAX30100
//    update loop running on Core 1.
// ==================================================
void tempTask(void *parameter) {
  for (;;) {
    if (dsOK) {
      tempSensor.requestTemperatures();
      float t = tempSensor.getTempCByIndex(0);
      if (t > -50.0 && t < 85.0) {
        latestTempC = t;
      }
    }
    vTaskDelay(2000 / portTICK_PERIOD_MS);
  }
}

// ==================================================
// 5. SEND DATA TO CAREPULSE (via ngrok HTTPS)
// ==================================================
void sendData() {
  float temperature = latestTempC;
  float heartRate   = pox.getHeartRate();
  int   spo2        = pox.getSpO2();

  Serial.printf("[Sensor] HR: %.1f BPM | SpO2: %d%% | Temp: %.1f°C\n",
                heartRate, spo2,
                (temperature == DEVICE_DISCONNECTED_C ? 0.0 : temperature));

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Disconnected. Reconnecting...");
    WiFi.reconnect();
    return;
  }

  WiFiClientSecure *client = new WiFiClientSecure;
  client->setInsecure();

  HTTPClient http;
  http.begin(*client, serverUrl);
  http.addHeader("Content-Type", "application/json");

  float safeTemp = (temperature == DEVICE_DISCONNECTED_C) ? 36.6 : temperature;

  String json = "{";
  json += "\"device_id\":\""  + String(deviceId)    + "\",";
  json += "\"patient_id\":\"" + String(patientId)   + "\",";
  json += "\"heart_rate\":"   + String(heartRate, 1) + ",";
  json += "\"spo2\":"         + String(spo2)         + ",";
  json += "\"temperature\":"  + String(safeTemp, 1)  + ",";
  json += "\"data_source\":\"ESP32\"";
  json += "}";

  int code = http.POST(json);
  if (code > 0) {
    Serial.printf("[Server] OK (HTTP %d)\n", code);
  } else {
    Serial.printf("[Server] FAILED: %s\n", http.errorToString(code).c_str());
  }

  http.end();
  delete client;
}

// ==================================================
// 6. SETUP
// ==================================================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n==================================");
  Serial.println("    CarePulse ESP32 Firmware");
  Serial.println("==================================");

  Wire.begin(21, 22);

  // --- Wi-Fi ---
  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.print("\nConnected! IP: ");
  Serial.println(WiFi.localIP());

  // --- MAX30100 ---
  Serial.print("Checking MAX30100... ");
  if (pox.begin()) {
    max30100OK = true;
    Serial.println("FOUND!");
    pox.setIRLedCurrent(MAX30100_LED_CURR_7_6MA);
    pox.setOnBeatDetectedCallback(onBeatDetected);
  } else {
    Serial.println("NOT FOUND! Check: VIN->3V3, GND->GND, SDA->D21, SCL->D22");
  }

  // --- DS18B20 ---
  Serial.print("Checking DS18B20... ");
  tempSensor.begin();
  if (tempSensor.getDeviceCount() > 0) {
    dsOK = true;
    Serial.println("FOUND!");
    xTaskCreatePinnedToCore(tempTask, "TempTask", 4096, NULL, 1, &tempTaskHandle, 0);
  } else {
    Serial.println("NOT FOUND! Check: DATA->D4, 4.7k pull-up to 3V3");
  }

  Serial.println("\nStreaming to CarePulse via ngrok...\n");
}

// ==================================================
// 7. MAIN LOOP
// ==================================================
void loop() {
  // MAX30100 MUST be updated as fast as possible on Core 1
  if (max30100OK) {
    pox.update();
  }

  // Send data every 3 seconds (non-blocking)
  if (millis() - lastSendTime >= SEND_INTERVAL) {
    lastSendTime = millis();
    sendData();
  }
}
