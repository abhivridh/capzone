import sqlite3
import bcrypt

def migrate():
    conn = sqlite3.connect('carepulse.db')
    c = conn.cursor()
    
    print("Creating new tables...")
    
    c.executescript("""
    CREATE TABLE IF NOT EXISTS family_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        patient_id VARCHAR(50) NOT NULL,
        assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS monthly_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id VARCHAR(50) NOT NULL,
        report_month VARCHAR(20) NOT NULL,
        hr_avg DECIMAL(5,2), hr_min DECIMAL(5,2), hr_max DECIMAL(5,2),
        spo2_avg DECIMAL(5,2), spo2_min DECIMAL(5,2), spo2_max DECIMAL(5,2),
        temp_avg DECIMAL(5,2), temp_min DECIMAL(5,2), temp_max DECIMAL(5,2),
        total_readings INTEGER,
        normal_readings INTEGER,
        warning_events INTEGER,
        critical_events INTEGER,
        total_alerts INTEGER,
        doctor_review_status VARCHAR(50) DEFAULT 'Pending Review',
        doctor_comment TEXT,
        reviewed_at TIMESTAMP,
        reviewed_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS camera_monitoring_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id VARCHAR(50) NOT NULL,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ended_at TIMESTAMP,
        face_status VARCHAR(50),
        movement_status VARCHAR(50),
        expression VARCHAR(50),
        monitoring_status VARCHAR(50)
    );
    """)

    # Check if Family Member demo user exists
    c.execute("SELECT id FROM users WHERE email = 'family@carepulse.com'")
    if not c.fetchone():
        salt = bcrypt.gensalt()
        pw_hash = bcrypt.hashpw('demo1234'.encode('utf-8'), salt).decode('utf-8')
        c.execute("INSERT INTO users (full_name, email, phone, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                  ('Demo Family Member', 'family@carepulse.com', '+1 555-0400', pw_hash, 'Family Member'))
        fm_id = c.lastrowid
        # Link to P001
        c.execute("INSERT INTO family_members (user_id, patient_id) VALUES (?, ?)", (fm_id, 'P001'))
        
    # Ensure caregiver assignment is correct: we also need caregivers to have user accounts so they can log in.
    # Currently, how do caregivers log in? Let's check users table for caregivers.
    c.execute("SELECT id FROM users WHERE email = 'daughter@carepulse.com'")
    if not c.fetchone():
        salt = bcrypt.gensalt()
        pw_hash = bcrypt.hashpw('demo1234'.encode('utf-8'), salt).decode('utf-8')
        c.execute("INSERT INTO users (full_name, email, phone, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                  ('Jane Patient', 'daughter@carepulse.com', '+1 555-0198', pw_hash, 'Caregiver'))

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == '__main__':
    migrate()
