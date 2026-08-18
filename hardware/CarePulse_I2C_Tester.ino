/* ==============================================================================
 * CarePulse - Quick I2C & Chip Part ID Diagnostic Scanner
 * Run this first to inspect your MAX30100 / MAX30102 chip without any libraries!
 * ============================================================================== */

#include <Wire.h>

void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n--- CarePulse I2C & Chip Diagnostic Scanner ---");
  Wire.begin(21, 22); // SDA=21, SCL=22

  Serial.println("Scanning I2C address 0x57...");
  Wire.beginTransmission(0x57);
  byte err = Wire.endTransmission();

  if (err == 0) {
    Serial.println("✓ [SUCCESS] Chip found at 0x57!");

    // Read Part ID Register 0xFF
    Wire.beginTransmission(0x57);
    Wire.write(0xFF);
    Wire.endTransmission(false);
    Wire.requestFrom(0x57, 1);
    
    if (Wire.available()) {
      byte partId = Wire.read();
      Serial.print("✓ [INFO] Part ID (Register 0xFF): 0x");
      Serial.println(partId, HEX);

      if (partId == 0x11) {
        Serial.println(">>> RESULT: Your board contains an actual MAX30100!");
        Serial.println(">>> Use the MAX30100lib library in Arduino IDE.");
      } else if (partId == 0x15) {
        Serial.println(">>> RESULT: Your board contains a MAX30102!");
        Serial.println(">>> Use the SparkFun MAX3010x library in Arduino IDE.");
      } else {
        Serial.print(">>> RESULT: Other revision detected (0x");
        Serial.print(partId, HEX);
        Serial.println("). Both MAX30100lib and SparkFun can communicate with it.");
      }
    }

    // Read Revision ID Register 0xFE
    Wire.beginTransmission(0x57);
    Wire.write(0xFE);
    Wire.endTransmission(false);
    Wire.requestFrom(0x57, 1);
    if (Wire.available()) {
      Serial.print("✓ [INFO] Revision ID (Register 0xFE): 0x");
      Serial.println(Wire.read(), HEX);
    }

  } else {
    Serial.print("✗ [FAILED] No I2C response at 0x57. Error code: ");
    Serial.println(err);
    Serial.println("Check wires: VIN->3V3, GND->GND, SDA->D21, SCL->D22.");
  }
}

void loop() {
  delay(5000);
}
