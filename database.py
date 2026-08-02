import os
import sqlite3
import pymysql
from pymysql.cursors import DictCursor
from config import Config

import time

_current_engine = None
_last_mysql_check = 0
_mysql_available = None

def get_db_status():
    """Returns whether CarePulse is currently connected to MySQL or SQLite fallback."""
    global _current_engine
    return _current_engine or "Unknown"

def _try_connect_mysql(create_db_if_missing=True):
    """Attempts to connect to MySQL database."""
    try:
        # First connect without specifying database to create it if needed
        conn = pymysql.connect(
            host=Config.MYSQL_HOST,
            port=Config.MYSQL_PORT,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            charset='utf8mb4',
            cursorclass=DictCursor,
            connect_timeout=1
        )
        if create_db_if_missing:
            with conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{Config.MYSQL_DB}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            conn.commit()
        conn.close()

        # Connect to the specific database
        db_conn = pymysql.connect(
            host=Config.MYSQL_HOST,
            port=Config.MYSQL_PORT,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DB,
            charset='utf8mb4',
            cursorclass=DictCursor,
            autocommit=True,
            connect_timeout=1
        )
        return db_conn
    except Exception as e:
        return None

def _get_sqlite_conn():
    """Fallback connection to local SQLite database if MySQL server is offline."""
    db_path = Config.SQLITE_DB
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_db_connection():
    """Returns active database connection (MySQL preferred, SQLite fallback)."""
    global _current_engine, _last_mysql_check, _mysql_available
    now = time.time()
    
    # Check MySQL if currently marked available or if 30s cooldown expired
    if _mysql_available is not False or (now - _last_mysql_check > 30):
        _last_mysql_check = now
        mysql_conn = _try_connect_mysql()
        if mysql_conn is not None:
            _mysql_available = True
            _current_engine = "MySQL"
            return mysql_conn
        else:
            _mysql_available = False
    
    _current_engine = "SQLite Fallback"
    return _get_sqlite_conn()

def query_db(sql, params=(), one=False):
    """
    Executes a SELECT query and returns rows as dictionaries.
    Compatible with both MySQL and SQLite parameter placeholders (%s vs ?).
    """
    conn = get_db_connection()
    status = get_db_status()
    try:
        if status == "MySQL":
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                conn.close()
                if one:
                    return rows[0] if rows else None
                return rows
        else:
            # SQLite fallback: convert %s to ?
            sqlite_sql = sql.replace('%s', '?')
            cur = conn.cursor()
            cur.execute(sqlite_sql, params)
            rows = [dict(row) for row in cur.fetchall()]
            conn.close()
            if one:
                return rows[0] if rows else None
            return rows
    except Exception as e:
        print(f"[CarePulse DB Error] Query failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None if one else []

def execute_db(sql, params=()):
    """
    Executes INSERT/UPDATE/DELETE query and returns the last inserted row id or rowcount.
    """
    conn = get_db_connection()
    status = get_db_status()
    try:
        if status == "MySQL":
            with conn.cursor() as cur:
                cur.execute(sql, params)
                last_id = cur.lastrowid
                conn.commit()
                conn.close()
                return last_id
        else:
            sqlite_sql = sql.replace('%s', '?')
            cur = conn.cursor()
            cur.execute(sqlite_sql, params)
            last_id = cur.lastrowid
            conn.commit()
            conn.close()
            return last_id
    except Exception as e:
        print(f"[CarePulse DB Error] Execution failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return None

def init_db(force_reseed=False):
    """
    Initializes tables and seeds initial data.
    Works for MySQL and sets up SQLite if MySQL is unavailable.
    """
    global _current_engine
    schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
    
    # Try MySQL first
    mysql_conn = _try_connect_mysql(create_db_if_missing=True)
    if mysql_conn is not None:
        _current_engine = "MySQL"
        try:
            with open(schema_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Split and execute individual queries
            queries = [q.strip() for q in content.split(';') if q.strip()]
            with mysql_conn.cursor() as cur:
                for q in queries:
                    # Skip database creation queries inside the connected DB
                    if q.upper().startswith("CREATE DATABASE") or q.upper().startswith("USE "):
                        continue
                    cur.execute(q)
            mysql_conn.commit()
            mysql_conn.close()
            print("[CarePulse DB] MySQL database 'carepulse' initialized and verified successfully!")
            return "MySQL"
        except Exception as e:
            print(f"[CarePulse DB] MySQL initialization error: {e}")
            try:
                mysql_conn.close()
            except Exception:
                pass

    # SQLite fallback initialization
    _current_engine = "SQLite Fallback"
    print("[CarePulse DB] MySQL not reachable on port 3306. Initializing SQLite fallback for seamless execution.")
    conn = _get_sqlite_conn()
    cur = conn.cursor()
    
    # Create SQLite equivalent schema
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        phone TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'Patient',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT NOT NULL UNIQUE,
        user_id INTEGER NULL,
        name TEXT NOT NULL,
        age INTEGER NOT NULL,
        gender TEXT NOT NULL DEFAULT 'Other',
        phone TEXT NOT NULL,
        emergency_contact TEXT NOT NULL,
        caregiver_alert_mode TEXT NOT NULL DEFAULT 'PRIMARY',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS caregivers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT NOT NULL,
        name TEXT NOT NULL,
        relationship TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT NULL,
        is_primary INTEGER NOT NULL DEFAULT 1,
        receive_alerts INTEGER NOT NULL DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL UNIQUE,
        patient_id TEXT NULL,
        device_name TEXT NOT NULL DEFAULT 'CarePulse ESP32',
        status TEXT NOT NULL DEFAULT 'NOT CONNECTED',
        last_seen DATETIME NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS sensor_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT NOT NULL,
        device_id TEXT NOT NULL,
        heart_rate REAL NOT NULL,
        spo2 REAL NOT NULL,
        temperature REAL NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        data_source TEXT NOT NULL DEFAULT 'DEMO'
    );

    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT NOT NULL,
        device_id TEXT NOT NULL,
        sensor_type TEXT NOT NULL,
        value REAL NOT NULL,
        threshold REAL NOT NULL,
        severity TEXT NOT NULL DEFAULT 'Warning',
        message TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Active',
        doctor_review_status TEXT NOT NULL DEFAULT 'Pending',
        doctor_comment TEXT NULL,
        doctor_id INTEGER NULL,
        email_status TEXT NOT NULL DEFAULT 'NONE',
        email_recipient TEXT NULL,
        email_sent_at DATETIME NULL,
        email_error TEXT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        resolved_at DATETIME NULL,
        FOREIGN KEY (doctor_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS thresholds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT NOT NULL,
        sensor_type TEXT NOT NULL,
        normal_min REAL NOT NULL,
        normal_max REAL NOT NULL,
        warning_min REAL NOT NULL,
        warning_max REAL NOT NULL,
        critical_min REAL NOT NULL,
        critical_max REAL NOT NULL,
        UNIQUE(patient_id, sensor_type)
    );

    CREATE TABLE IF NOT EXISTS doctor_assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctor_id INTEGER NOT NULL,
        patient_id TEXT NOT NULL,
        assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (doctor_id) REFERENCES users(id),
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
        UNIQUE(doctor_id, patient_id)
    );

    CREATE TABLE IF NOT EXISTS pulse_verifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT NOT NULL,
        doctor_id INTEGER NOT NULL,
        health_reading_id INTEGER NOT NULL,
        sensor_bpm REAL NOT NULL,
        camera_bpm REAL NULL,
        difference_bpm REAL NULL,
        signal_quality TEXT NOT NULL DEFAULT 'Insufficient',
        comparison_status TEXT NOT NULL DEFAULT 'Insufficient Data',
        doctor_review_status TEXT NOT NULL DEFAULT 'Pending',
        doctor_comment TEXT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
        FOREIGN KEY (doctor_id) REFERENCES users(id),
        FOREIGN KEY (health_reading_id) REFERENCES sensor_readings(id)
    );

    CREATE TABLE IF NOT EXISTS notification_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_id INTEGER NOT NULL,
        recipient TEXT NOT NULL,
        recipient_type TEXT NOT NULL,
        notification_type TEXT NOT NULL DEFAULT 'Email',
        status TEXT NOT NULL DEFAULT 'Pending',
        failure_reason TEXT NULL,
        sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (alert_id) REFERENCES alerts(id)
    );
    """)
    conn.commit()

    # Migration for existing SQLite databases
    try:
        cur.execute("ALTER TABLE patients ADD COLUMN caregiver_alert_mode TEXT NOT NULL DEFAULT 'PRIMARY'")
        conn.commit()
    except Exception:
        pass

    for col, col_def in [
        ('email_status', "TEXT NOT NULL DEFAULT 'NONE'"),
        ('email_recipient', "TEXT NULL"),
        ('email_sent_at', "DATETIME NULL"),
        ('email_error', "TEXT NULL"),
        ('doctor_review_status', "TEXT NOT NULL DEFAULT 'Pending'"),
        ('doctor_comment', "TEXT NULL"),
        ('doctor_id', "INTEGER NULL")
    ]:
        try:
            cur.execute(f"ALTER TABLE alerts ADD COLUMN {col} {col_def}")
            conn.commit()
        except Exception:
            pass

    # Seed demo users & patient if empty
    cur.execute("SELECT COUNT(*) as cnt FROM users")
    if cur.fetchone()[0] == 0:
        # Default password is demo1234
        pwd_hash = '$2b$12$wjqACvv09.uaqieqGBev1uy6h97ZMp3v2DT5qGW5yJ3fCm70ycBBu'
        cur.execute("INSERT OR IGNORE INTO users (id, full_name, email, phone, password_hash, role) VALUES (1, 'Demo Patient', 'demo@carepulse.com', '+1 555-0199', ?, 'Patient')", (pwd_hash,))
        cur.execute("INSERT OR IGNORE INTO users (id, full_name, email, phone, password_hash, role) VALUES (2, 'Dr. Sarah Mitchell', 'doctor@carepulse.com', '+1 555-0144', ?, 'Doctor')", (pwd_hash,))
        cur.execute("INSERT OR IGNORE INTO users (id, full_name, email, phone, password_hash, role) VALUES (3, 'CarePulse Admin', 'admin@carepulse.com', '+1 555-0100', ?, 'Admin')", (pwd_hash,))
        
        cur.execute("INSERT OR IGNORE INTO patients (id, patient_id, user_id, name, age, gender, phone, emergency_contact, caregiver_alert_mode) VALUES (1, 'P001', 1, 'Demo Patient', 65, 'Male', '+1 555-0199', 'Jane Patient (Daughter) - daughter@carepulse.com', 'PRIMARY')")
        cur.execute("INSERT OR IGNORE INTO patients (id, patient_id, user_id, name, age, gender, phone, emergency_contact, caregiver_alert_mode) VALUES (2, 'P002', NULL, 'Eleanor Vance', 72, 'Female', '+1 555-0211', 'Robert Vance (Spouse) - +1 555-0212', 'PRIMARY')")
        cur.execute("INSERT OR IGNORE INTO patients (id, patient_id, user_id, name, age, gender, phone, emergency_contact, caregiver_alert_mode) VALUES (3, 'P003', NULL, 'Arthur Pendelton', 58, 'Male', '+1 555-0344', 'Clara Pendelton (Wife) - +1 555-0345', 'PRIMARY')")

        cur.execute("INSERT OR IGNORE INTO devices (id, device_id, patient_id, device_name, status) VALUES (1, 'ESP32-001', 'P001', 'CarePulse ESP32', 'NOT CONNECTED')")
        cur.execute("INSERT OR IGNORE INTO devices (id, device_id, patient_id, device_name, status) VALUES (2, 'ESP32-002', 'P002', 'CarePulse ESP32 Ward-B', 'NOT CONNECTED')")

        cur.execute("INSERT OR IGNORE INTO thresholds (patient_id, sensor_type, normal_min, normal_max, warning_min, warning_max, critical_min, critical_max) VALUES ('P001', 'Heart Rate', 60.0, 100.0, 50.0, 110.0, 45.0, 120.0)")
        cur.execute("INSERT OR IGNORE INTO thresholds (patient_id, sensor_type, normal_min, normal_max, warning_min, warning_max, critical_min, critical_max) VALUES ('P001', 'SpO2', 95.0, 100.0, 90.0, 94.0, 85.0, 89.0)")
        cur.execute("INSERT OR IGNORE INTO thresholds (patient_id, sensor_type, normal_min, normal_max, warning_min, warning_max, critical_min, critical_max) VALUES ('P001', 'Temperature', 36.1, 37.2, 37.3, 38.0, 38.1, 40.0)")

        # Initial readings
        cur.execute("INSERT INTO sensor_readings (patient_id, device_id, heart_rate, spo2, temperature, timestamp, data_source) VALUES ('P001', 'ESP32-001', 75.0, 98.0, 36.6, datetime('now', '-30 minutes'), 'DEMO')")
        cur.execute("INSERT INTO sensor_readings (patient_id, device_id, heart_rate, spo2, temperature, timestamp, data_source) VALUES ('P001', 'ESP32-001', 76.0, 98.0, 36.6, datetime('now', '-20 minutes'), 'DEMO')")
        cur.execute("INSERT INTO sensor_readings (patient_id, device_id, heart_rate, spo2, temperature, timestamp, data_source) VALUES ('P001', 'ESP32-001', 77.0, 97.0, 36.7, datetime('now', '-10 minutes'), 'DEMO')")
        cur.execute("INSERT INTO sensor_readings (patient_id, device_id, heart_rate, spo2, temperature, timestamp, data_source) VALUES ('P001', 'ESP32-001', 76.0, 98.0, 36.7, datetime('now'), 'DEMO')")

        # Initial sample resolved alert
        cur.execute("INSERT INTO alerts (patient_id, device_id, sensor_type, value, threshold, severity, message, status, created_at, resolved_at) VALUES ('P001', 'ESP32-001', 'Heart Rate', 112.0, 110.0, 'Warning', 'Elevated heart rate detected (112 BPM, Warning Threshold: 110 BPM)', 'Resolved', datetime('now', '-2 hours'), datetime('now', '-105 minutes'))")
        conn.commit()

    # Seed caregivers if empty
    cur.execute("SELECT COUNT(*) as cnt FROM caregivers")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT OR IGNORE INTO caregivers (id, patient_id, name, relationship, email, phone, is_primary, receive_alerts) VALUES (1, 'P001', 'Jane Patient', 'Daughter', 'daughter@carepulse.com', '+1 555-0198', 1, 1)")
        cur.execute("INSERT OR IGNORE INTO caregivers (id, patient_id, name, relationship, email, phone, is_primary, receive_alerts) VALUES (2, 'P001', 'Mark Patient', 'Son', 'son@carepulse.com', '+1 555-0197', 0, 1)")
        cur.execute("INSERT OR IGNORE INTO caregivers (id, patient_id, name, relationship, email, phone, is_primary, receive_alerts) VALUES (3, 'P001', 'David Patient', 'Husband', 'husband@carepulse.com', '+1 555-0196', 0, 1)")
        conn.commit()

    conn.close()
    return "SQLite Fallback"



