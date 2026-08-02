-- ===================================================
-- CAREPULSE - IoT-Based Healthcare Monitoring System
-- Database Schema (MySQL 5.7+ / 8.0+)
-- ===================================================

CREATE DATABASE IF NOT EXISTS carepulse CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE carepulse;

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    phone VARCHAR(20) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('Patient', 'Doctor', 'Caregiver', 'Admin') NOT NULL DEFAULT 'Patient',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Patients Table
CREATE TABLE IF NOT EXISTS patients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL UNIQUE,
    user_id INT NULL,
    name VARCHAR(120) NOT NULL,
    age INT NOT NULL,
    gender ENUM('Male', 'Female', 'Other') NOT NULL DEFAULT 'Other',
    phone VARCHAR(20) NOT NULL,
    emergency_contact VARCHAR(100) NOT NULL,
    caregiver_alert_mode ENUM('PRIMARY', 'ALL') NOT NULL DEFAULT 'PRIMARY',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- 2b. Caregivers Table (Emergency Relatives & Contacts)
CREATE TABLE IF NOT EXISTS caregivers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    name VARCHAR(120) NOT NULL,
    relationship ENUM('Daughter', 'Son', 'Husband', 'Wife', 'Parent', 'Other') NOT NULL DEFAULT 'Other',
    email VARCHAR(120) NOT NULL,
    phone VARCHAR(30) NULL,
    is_primary TINYINT(1) NOT NULL DEFAULT 1,
    receive_alerts TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_cg_patient (patient_id)
);

-- 3. Devices Table
CREATE TABLE IF NOT EXISTS devices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL UNIQUE,
    patient_id VARCHAR(50) NULL,
    device_name VARCHAR(100) NOT NULL DEFAULT 'CarePulse ESP32',
    status ENUM('CONNECTED', 'NOT CONNECTED', 'DEMO MODE') NOT NULL DEFAULT 'NOT CONNECTED',
    last_seen TIMESTAMP NULL DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Sensor Readings Table
CREATE TABLE IF NOT EXISTS sensor_readings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    device_id VARCHAR(50) NOT NULL,
    heart_rate DECIMAL(5,2) NOT NULL,
    spo2 DECIMAL(5,2) NOT NULL,
    temperature DECIMAL(5,2) NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_source ENUM('DEMO', 'ESP32') NOT NULL DEFAULT 'DEMO',
    INDEX idx_patient_time (patient_id, timestamp),
    INDEX idx_data_source (data_source)
);

-- 5. Alerts Table
CREATE TABLE IF NOT EXISTS alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    device_id VARCHAR(50) NOT NULL,
    sensor_type ENUM('Heart Rate', 'SpO2', 'Temperature') NOT NULL,
    value DECIMAL(5,2) NOT NULL,
    threshold DECIMAL(5,2) NOT NULL,
    severity ENUM('Critical', 'Warning', 'Info') NOT NULL DEFAULT 'Warning',
    message VARCHAR(255) NOT NULL,
    status ENUM('Active', 'Resolved') NOT NULL DEFAULT 'Active',
    doctor_review_status ENUM('Pending', 'Reviewed', 'Needs Recheck') NOT NULL DEFAULT 'Pending',
    doctor_comment TEXT NULL,
    doctor_id INT NULL,
    email_status VARCHAR(50) NOT NULL DEFAULT 'NONE',
    email_error TEXT NULL,
    email_recipient VARCHAR(255) NULL,
    email_sent_at DATETIME NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP NULL DEFAULT NULL,
    INDEX idx_status (status),
    INDEX idx_created (created_at),
    FOREIGN KEY (doctor_id) REFERENCES users(id) ON DELETE SET NULL
);

-- 6. Thresholds Table
CREATE TABLE IF NOT EXISTS thresholds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    sensor_type ENUM('Heart Rate', 'SpO2', 'Temperature') NOT NULL,
    normal_min DECIMAL(5,2) NOT NULL,
    normal_max DECIMAL(5,2) NOT NULL,
    warning_min DECIMAL(5,2) NOT NULL,
    warning_max DECIMAL(5,2) NOT NULL,
    critical_min DECIMAL(5,2) NOT NULL,
    critical_max DECIMAL(5,2) NOT NULL,
    UNIQUE KEY uq_patient_sensor (patient_id, sensor_type)
);


-- 7. Doctor Assignments Table
CREATE TABLE IF NOT EXISTS doctor_assignments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    doctor_id INT NOT NULL,
    patient_id VARCHAR(50) NOT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (doctor_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE,
    UNIQUE KEY uq_doc_patient (doctor_id, patient_id)
);

-- 8. Pulse Verifications Table
CREATE TABLE IF NOT EXISTS pulse_verifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id VARCHAR(50) NOT NULL,
    doctor_id INT NOT NULL,
    health_reading_id INT NOT NULL,
    sensor_bpm DECIMAL(5,2) NOT NULL,
    camera_bpm DECIMAL(5,2) NULL,
    difference_bpm DECIMAL(5,2) NULL,
    signal_quality ENUM('Good', 'Poor', 'Insufficient') NOT NULL DEFAULT 'Insufficient',
    comparison_status ENUM('Similar', 'Difference Detected', 'Insufficient Data') NOT NULL DEFAULT 'Insufficient Data',
    doctor_review_status ENUM('Pending', 'Reviewed', 'Needs Recheck') NOT NULL DEFAULT 'Pending',
    doctor_comment TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (health_reading_id) REFERENCES sensor_readings(id) ON DELETE CASCADE
);

-- 9. Notification History Table
CREATE TABLE IF NOT EXISTS notification_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    alert_id INT NOT NULL,
    recipient VARCHAR(120) NOT NULL,
    recipient_type ENUM('Caregiver', 'Doctor', 'Patient') NOT NULL,
    notification_type ENUM('Email', 'Dashboard') NOT NULL DEFAULT 'Email',
    status ENUM('Sent', 'Failed', 'Pending') NOT NULL DEFAULT 'Pending',
    failure_reason TEXT NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE CASCADE
);

-- ===================================================
-- SEED DATA
-- ===================================================

-- Initial Demo User (Password: demo1234, pre-hashed using bcrypt)
-- Also creates Doctor and Admin users (doctor@carepulse.com, admin@carepulse.com)
INSERT INTO users (id, full_name, email, phone, password_hash, role)
VALUES 
(1, 'Demo Patient', 'demo@carepulse.com', '+1 555-0199', '$2b$12$wjqACvv09.uaqieqGBev1uy6h97ZMp3v2DT5qGW5yJ3fCm70ycBBu', 'Patient'),
(2, 'Dr. Sarah Mitchell', 'doctor@carepulse.com', '+1 555-0144', '$2b$12$wjqACvv09.uaqieqGBev1uy6h97ZMp3v2DT5qGW5yJ3fCm70ycBBu', 'Doctor'),
(3, 'CarePulse Admin', 'admin@carepulse.com', '+1 555-0100', '$2b$12$wjqACvv09.uaqieqGBev1uy6h97ZMp3v2DT5qGW5yJ3fCm70ycBBu', 'Admin')
ON DUPLICATE KEY UPDATE full_name=VALUES(full_name);

-- Initial Demo Patient
INSERT INTO patients (id, patient_id, user_id, name, age, gender, phone, emergency_contact, caregiver_alert_mode)
VALUES 
(1, 'P001', 1, 'Demo Patient', 65, 'Male', '+1 555-0199', 'Jane Patient (Daughter) - +1 555-0198', 'PRIMARY'),
(2, 'P002', NULL, 'Eleanor Vance', 72, 'Female', '+1 555-0211', 'Robert Vance (Spouse) - +1 555-0212', 'PRIMARY'),
(3, 'P003', NULL, 'Arthur Pendelton', 58, 'Male', '+1 555-0344', 'Clara Pendelton (Wife) - +1 555-0345', 'PRIMARY')
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- Initial Demo Caregivers (Multiple family members linked to P001)
INSERT INTO caregivers (id, patient_id, name, relationship, email, phone, is_primary, receive_alerts)
VALUES 
(1, 'P001', 'Jane Patient', 'Daughter', 'daughter@carepulse.com', '+1 555-0198', 1, 1),
(2, 'P001', 'Mark Patient', 'Son', 'son@carepulse.com', '+1 555-0197', 0, 1),
(3, 'P001', 'David Patient', 'Husband', 'husband@carepulse.com', '+1 555-0196', 0, 1)
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- Initial Device (ESP32-001) - Clearly Marked NOT CONNECTED / DEMO MODE
INSERT INTO devices (id, device_id, patient_id, device_name, status, last_seen)
VALUES 
(1, 'ESP32-001', 'P001', 'CarePulse ESP32', 'NOT CONNECTED', NULL),
(2, 'ESP32-002', 'P002', 'CarePulse ESP32 Ward-B', 'NOT CONNECTED', NULL)
ON DUPLICATE KEY UPDATE device_name=VALUES(device_name);

-- Default Project Monitoring Thresholds for Patient P001
INSERT INTO thresholds (patient_id, sensor_type, normal_min, normal_max, warning_min, warning_max, critical_min, critical_max)
VALUES 
('P001', 'Heart Rate', 60.0, 100.0, 50.0, 110.0, 45.0, 120.0),
('P001', 'SpO2', 95.0, 100.0, 90.0, 94.0, 85.0, 89.0),
('P001', 'Temperature', 36.1, 37.2, 37.3, 38.0, 38.1, 40.0)
ON DUPLICATE KEY UPDATE normal_min=VALUES(normal_min);

-- Sample Historical Readings (Realistic, labeled DEMO)
INSERT INTO sensor_readings (patient_id, device_id, heart_rate, spo2, temperature, timestamp, data_source)
VALUES
('P001', 'ESP32-001', 75.0, 98.0, 36.6, DATE_SUB(NOW(), INTERVAL 35 MINUTE), 'DEMO'),
('P001', 'ESP32-001', 76.0, 98.0, 36.6, DATE_SUB(NOW(), INTERVAL 30 MINUTE), 'DEMO'),
('P001', 'ESP32-001', 77.0, 97.0, 36.7, DATE_SUB(NOW(), INTERVAL 25 MINUTE), 'DEMO'),
('P001', 'ESP32-001', 75.0, 98.0, 36.6, DATE_SUB(NOW(), INTERVAL 20 MINUTE), 'DEMO'),
('P001', 'ESP32-001', 78.0, 98.0, 36.8, DATE_SUB(NOW(), INTERVAL 15 MINUTE), 'DEMO'),
('P001', 'ESP32-001', 76.0, 97.0, 36.7, DATE_SUB(NOW(), INTERVAL 10 MINUTE), 'DEMO'),
('P001', 'ESP32-001', 75.0, 98.0, 36.6, DATE_SUB(NOW(), INTERVAL 5 MINUTE), 'DEMO'),
('P001', 'ESP32-001', 76.0, 98.0, 36.7, NOW(), 'DEMO');

-- Sample Resolved Alert for Initial History Demonstration
INSERT INTO alerts (patient_id, device_id, sensor_type, value, threshold, severity, message, status, created_at, resolved_at)
VALUES 
('P001', 'ESP32-001', 'Heart Rate', 112.0, 110.0, 'Warning', 'Elevated heart rate detected (112 BPM, Warning Threshold: 110 BPM)', 'Resolved', DATE_SUB(NOW(), INTERVAL 2 HOUR), DATE_SUB(NOW(), INTERVAL 105 MINUTE));

