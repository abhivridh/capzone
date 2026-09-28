# CarePulse - IoT Healthcare Monitoring System

## 1. Project Title
CarePulse - IoT-Based Healthcare Monitoring and Alert System with Remote Pulse Verification

## 2. Project Description
CarePulse is an advanced, production-ready IoT healthcare system designed to monitor patient vitals continuously and automatically dispatch critical alerts. It seamlessly bridges physical hardware (ESP32) with a robust Python Flask backend, supporting multi-tier Role-Based Access Control (RBAC) for Patients, Caregivers, and Doctors.

## 3. Features
* **Automated Critical Alerts:** Triggers SMTP email dispatch without requiring user login.
* **Role-Based Access:** Distinct portals for Patients, Caregivers, and Doctors.
* **Multi-Recipient Notifications:** Emails Caregivers and Doctors simultaneously, securely tracked in the database.
* **Camera Pulse Verification:** Secondary rPPG estimation allowing Doctors to verify physical sensor anomalies.
* **SQLite Fallback:** Intelligent database connection that uses MySQL by default, but seamlessly falls back to a self-healing SQLite database if offline.

## 4. Architecture
ESP32 Hardware ? Flask API (Backend) ? Database Storage ? Condition Evaluation ? Alert Creation ? SMTP Multi-Email Dispatch ? Doctor Review/Camera Verification

## 5. Technologies
* **Backend:** Python (Flask, PyMySQL, SQLite3)
* **Frontend:** HTML5, CSS (Tailwind), JavaScript, Jinja2
* **Hardware:** ESP32, MAX30102 (Heart Rate & SpO2), DS18B20 (Temperature)
* **Database:** MySQL / SQLite

## 6. Folder Structure
* /templates/ - HTML dashboard templates (Patient, Caregiver, Doctor, Monitoring, etc.)
* /hardware/ - Scripts and instructions for the ESP32 setup.
* pp.py - Main Flask entry point and routing logic.
* database.py - Database connection and migration logic.
* email_service.py - Multi-recipient automated SMTP worker.
* models.py - Application models (User, Patient, Caregiver, Alerts, Thresholds).
* schema.sql - Complete MySQL schema configuration.

## 7. Database Structure
Key Tables:
* users, patients, caregivers, doctor_assignments (Relationships)
* devices, sensor_readings, 	hresholds (Telemetry)
* lerts, 
otification_history, pulse_verifications (Action tracking)

## 8. Installation
1. Install Python 3.8+
2. Install requirements: pip install -r requirements.txt (or install flask, pymysql, python-dotenv).

## 9. Environment Setup
Rename .env.example to .env and fill in your MySQL credentials and SMTP Google App Password.

## 10. How to run Flask
Run the command: python app.py (accessible on http://127.0.0.1:5000)

## 11. How to connect ESP32
Ensure the ESP32 is on the same local network and configured to POST JSON payloads to http://<YOUR_IP>:5000/api/sensor-data.

## 12. How to configure email
Enable 2-Step Verification on your Gmail account. Generate a 16-character **App Password** and insert it into .env under SMTP_PASSWORD. 

## 13. How critical alerts work
Alert generation is strictly decoupled from the UI. When the ESP32 posts data to /api/sensor-data, the Flask backend automatically evaluates the numbers against the 	hresholds table. If critical, it triggers a background worker thread (email_service.py) that queries the Caregiver and Doctor emails and dispatches notifications instantly, tracking success in 
otification_history.

## 14. How doctor verification works
Doctors log into their dedicated portal to view assigned patients. When an alert triggers, they can review the patient's history and change the doctor_review_status from Pending to Reviewed or Needs Recheck, adding clinical notes.

## 15. How camera pulse verification works
When reviewing an alert, a doctor can click "Verify Pulse with Camera." This opens a UI utilizing the device webcam to perform an rPPG estimation. The backend stores both the original MAX30102 value and the camera estimate in the pulse_verifications table for comparison. The original sensor data is **never** overwritten.

## 16. User Roles
* **Patient:** Curiously views their own historical data.
* **Caregiver:** Primarily monitors the live dashboard and receives emergency intervention emails.
* **Doctor:** Clinically reviews historical trends, alerts, and performs secondary camera verification.
* **Admin:** Manages device and patient associations.

## 17. Testing Instructions
Run python test_carepulse.py or manually trigger the APIs via Postman to /api/sensor-data to simulate hardware telemetry and verify the email dispatch system.

## 18. Limitations
Camera rPPG estimation heavily relies on adequate lighting and minimal subject movement, and is secondary to the physical MAX30102 hardware.

## 19. Future Enhancements
* Machine Learning predictive trend analysis for sudden SpO2 drops.
* Mobile application wrapper for push notifications.

