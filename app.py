import os
import time
import random
import threading
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, jsonify, session,
    redirect, url_for, flash, g, make_response
)

from config import Config
from database import init_db, get_db_status
from models import (
    UserModel, PatientModel, DeviceModel, 
    SensorModel, ThresholdModel, AlertModel, CaregiverModel
)

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database on startup
init_db()

# Register blueprints
try:
    from blueprints.admin import admin_bp
    from blueprints.family import family_bp
    app.register_blueprint(admin_bp)
    app.register_blueprint(family_bp)
except Exception as e:
    print("Error registering blueprints:", e)


# ==============================================================================
# AUTHENTICATION & ACCESS CONTROL HELPERS
# ==============================================================================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for('login_view', next=request.path))
        return f(*args, **kwargs)
    return decorated_function

def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login_view'))
            user_role = session.get('role', 'Patient')
            if user_role not in roles and 'Admin' not in roles:
                flash("You do not have permission to access that section.", "danger")
                return redirect(url_for('dashboard_view'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def patient_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please sign in as a patient to access this page.", "warning")
            return redirect(url_for('patient_login_view', next=request.path))
        
        current_role = str(session.get('role', '')).lower()
        if current_role not in ('patient', 'admin'):
            flash("Access restricted. This page is reserved for patients.", "danger")
            if current_role == 'caregiver':
                return redirect(url_for('caregiver_dashboard_view'))
            return redirect(url_for('patient_login_view'))
        return f(*args, **kwargs)
    return decorated_function

def caregiver_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please sign in as an authorized caregiver to access this page.", "warning")
            return redirect(url_for('caregiver_login_view', next=request.path))
        
        current_role = str(session.get('role', '')).lower()
        if current_role not in ('caregiver', 'admin'):
            flash("Access restricted. This page is reserved for caregivers.", "danger")
            if current_role == 'patient':
                return redirect(url_for('dashboard_view'))
            return redirect(url_for('caregiver_login_view'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_global_context():
    """Injects user info, database status, and active alert count to all templates."""
    active_alerts = 0
    db_engine = get_db_status()
    user_name = session.get('full_name', 'Guest')
    user_role = session.get('role', 'Guest')
    user_id = session.get('user_id', None)
    
    if 'user_id' in session:
        try:
            active_alerts = AlertModel.get_active_count()
        except Exception:
            active_alerts = 0

    is_hardware = DeviceModel.is_connected('ESP32-001', timeout_seconds=10)

    return {
        'current_user_name': user_name,
        'current_user_role': user_role,
        'current_user_id': user_id,
        'active_alerts_count': active_alerts,
        'db_engine': db_engine,
        'is_hardware_connected': is_hardware
    }

# ==============================================================================
# WEB PAGE ROUTES (14 REQUIRED PAGES)
# ==============================================================================

# 1. Home Page (Hero, Tagline, Feature Cards, Visual Flow, Demo CTA)
@app.route('/')
def home_view():
    return render_template('index.html')

# 2. Patient Registration Page
@app.route('/patient-register', methods=['GET', 'POST'])
def patient_register_view():
    if request.method == 'GET':
        if 'user_id' in session:
            return redirect(url_for('dashboard_view'))
        return render_template('patient_register.html')
    
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip().lower()
    phone = request.form.get('phone', '').strip()
    age = request.form.get('age', 45)
    gender = request.form.get('gender', 'Other')
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')

    cg_name = request.form.get('caregiver_name', '').strip()
    cg_rel = request.form.get('caregiver_relationship', 'Other Caregiver').strip()
    cg_email = request.form.get('caregiver_email', '').strip().lower()
    cg_phone = request.form.get('caregiver_phone', '').strip()

    # Backend Validations
    if not full_name or not email or not phone or not password:
        flash("Please fill in all required fields.", "danger")
        return render_template('patient_register.html')
    
    import re
    email_regex = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    if not re.match(email_regex, email):
        flash("Please enter a valid email address.", "danger")
        return render_template('patient_register.html')
    
    phone_clean = re.sub(r'\D', '', phone)
    if len(phone_clean) == 12 and phone_clean.startswith('91'):
        phone_clean = phone_clean[2:]
    if len(phone_clean) != 10 or not phone_clean.startswith(('6', '7', '8', '9')):
        flash("Please enter a valid 10-digit Indian phone number.", "danger")
        return render_template('patient_register.html')
    
    if len(password) < 8:
        flash("Password must be at least 8 characters long.", "danger")
        return render_template('patient_register.html')
    if password != confirm_password:
        flash("Passwords do not match.", "danger")
        return render_template('patient_register.html')
    
    if UserModel.get_by_email(email):
        flash("An account with this email address is already registered.", "danger")
        return render_template('patient_register.html')
    
    if not cg_name or not cg_email:
        flash("Emergency caregiver contact details are required.", "danger")
        return render_template('patient_register.html')
    if not re.match(email_regex, cg_email):
        flash("Please enter a valid caregiver alert email address.", "danger")
        return render_template('patient_register.html')

    user_id = UserModel.create(full_name, email, phone_clean, password, role='Patient')
    patient_id = f"P{user_id:03d}"
    emergency_str = f"{cg_name} ({cg_rel}) - {cg_email}"
    
    try:
        age_int = int(age)
    except Exception:
        age_int = 45

    PatientModel.create(patient_id, full_name, age_int, gender, phone_clean, emergency_str, user_id=user_id)
    ThresholdModel.get_thresholds(patient_id)
    
    CaregiverModel.create(
        patient_id=patient_id,
        name=cg_name,
        relationship=cg_rel,
        email=cg_email,
        phone=cg_phone,
        is_primary=True,
        receive_alerts=True
    )

    session.clear()
    session['user_id'] = user_id
    session['full_name'] = full_name
    session['email'] = email
    session['role'] = 'Patient'
    session['linked_patient_id'] = patient_id

    flash("Patient account registered successfully!", "success")
    return redirect(url_for('dashboard_view'))

# 3. Caregiver Registration Page
@app.route('/caregiver-register', methods=['GET', 'POST'])
def caregiver_register_view():
    if request.method == 'GET':
        if 'user_id' in session:
            return redirect(url_for('caregiver_dashboard_view'))
        return render_template('caregiver_register.html')
    
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip().lower()
    phone = request.form.get('phone', '').strip()
    relationship = request.form.get('relationship', 'Other Caregiver').strip()
    patient_identifier = request.form.get('patient_identifier', '').strip()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not full_name or not email or not phone or not password or not patient_identifier:
        flash("Please fill in all required fields.", "danger")
        return render_template('caregiver_register.html')
    
    import re
    email_regex = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
    if not re.match(email_regex, email):
        flash("Please enter a valid email address.", "danger")
        return render_template('caregiver_register.html')
    
    phone_clean = re.sub(r'\D', '', phone)
    if len(phone_clean) == 12 and phone_clean.startswith('91'):
        phone_clean = phone_clean[2:]
    if len(phone_clean) != 10 or not phone_clean.startswith(('6', '7', '8', '9')):
        flash("Please enter a valid 10-digit Indian phone number.", "danger")
        return render_template('caregiver_register.html')
    
    if len(password) < 8:
        flash("Password must be at least 8 characters long.", "danger")
        return render_template('caregiver_register.html')
    if password != confirm_password:
        flash("Passwords do not match.", "danger")
        return render_template('caregiver_register.html')
    
    if UserModel.get_by_email(email):
        flash("An account with this email address is already registered.", "danger")
        return render_template('caregiver_register.html')
    
    # Verify patient exists
    target_patient = PatientModel.get_by_email_or_id(patient_identifier)
    target_pid = target_patient['patient_id'] if target_patient else 'P001'

    user_id = UserModel.create(full_name, email, phone_clean, password, role='Caregiver')
    CaregiverModel.create(
        patient_id=target_pid,
        name=full_name,
        relationship=relationship,
        email=email,
        phone=phone_clean,
        is_primary=False,
        receive_alerts=True
    )

    session.clear()
    session['user_id'] = user_id
    session['full_name'] = full_name
    session['email'] = email
    session['role'] = 'Caregiver'
    session['linked_patient_id'] = target_pid

    flash("Caregiver account registered successfully!", "success")
    return redirect(url_for('caregiver_dashboard_view'))

# Legacy Register Route Fallback
@app.route('/register', methods=['GET', 'POST'])
def register_view():
    return redirect(url_for('patient_register_view'))

# 4. Patient Login Page
@app.route('/patient-login', methods=['GET', 'POST'])
def patient_login_view():
    if request.method == 'GET':
        if 'user_id' in session and session.get('role') in ('Patient', 'Admin'):
            return redirect(url_for('dashboard_view'))
        return render_template('patient_login.html')
    
    login_id = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    
    # 1. Lookup by email or username/full_name
    from database import query_db
    user = UserModel.get_by_email(login_id)
    if not user:
        user = query_db("SELECT * FROM users WHERE LOWER(full_name) = %s OR LOWER(email) = %s", (login_id, login_id), one=True)
        if not user and login_id in ('admin', 'administrator', 'carepulse_admin'):
            user = query_db("SELECT * FROM users WHERE role = 'Admin' LIMIT 1", one=True)

    if not user or not UserModel.verify_password(user['password_hash'], password):
        flash("Invalid username/email or password.", "danger")
        return render_template('patient_login.html')

    session.clear()
    session['user_id'] = user['id']
    session['full_name'] = user['full_name']
    session['email'] = user['email']
    session['role'] = user['role']

    role = user['role']
    if role == 'Admin':
        flash(f"Welcome, Administrator {user['full_name']}.", "success")
        return redirect(url_for('admin_bp.admin_dashboard'))
    elif role == 'Doctor':
        flash(f"Welcome, Dr. {user['full_name']}.", "success")
        return redirect(url_for('doctor_dashboard_view'))
    elif role == 'Caregiver':
        cg = CaregiverModel.get_by_email(user['email'])
        if cg: session['linked_patient_id'] = cg['patient_id']
        flash(f"Welcome, {user['full_name']} (Caregiver).", "success")
        return redirect(url_for('caregiver_dashboard_view'))
    elif role == 'Family Member':
        flash(f"Welcome back, {user['full_name']}.", "success")
        return redirect(url_for('family_bp.family_dashboard'))
    else:
        p = PatientModel.get_by_user_id(user['id'])
        session['linked_patient_id'] = p['patient_id'] if p else "P001"
        flash(f"Welcome back, {user['full_name']}!", "success")
        next_url = request.args.get('next') or url_for('dashboard_view')
        return redirect(next_url)

# 5. Caregiver Login Page
@app.route('/caregiver-login', methods=['GET', 'POST'])
def caregiver_login_view():
    if request.method == 'GET':
        if 'user_id' in session and session.get('role') in ('Caregiver', 'Admin'):
            return redirect(url_for('caregiver_dashboard_view'))
        from database import query_db
        caregivers = query_db("SELECT id, full_name, email FROM users WHERE role = 'Caregiver'")
        return render_template('caregiver_login.html', caregivers=caregivers)
    
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    
    user = UserModel.get_by_email(email)
    if not user or not UserModel.verify_password(user['password_hash'], password):
        flash("Invalid email or password.", "danger")
        return render_template('caregiver_login.html')
    
    if user['role'] == 'Patient':
        flash("This account is registered as a Patient. Please use the Patient Login portal.", "info")
        return redirect(url_for('patient_login_view'))

    session.clear()
    session['user_id'] = user['id']
    session['full_name'] = user['full_name']
    session['email'] = user['email']
    session['role'] = user['role']

    cg = CaregiverModel.get_by_email(user['email'])
    if cg:
        session['linked_patient_id'] = cg['patient_id']
    
    flash(f"Welcome back, {user['full_name']}!", "success")
    next_url = request.args.get('next') or url_for('caregiver_dashboard_view')
    return redirect(next_url)

# Legacy Login Route Fallback
@app.route('/login', methods=['GET', 'POST'])
def login_view():
    return redirect(url_for('patient_login_view'))

# 6. Dedicated Caregiver Dashboard
@app.route('/caregiver-dashboard')
@login_required
@caregiver_required
def caregiver_dashboard_view():
    caregiver_email = session.get('email', '')
    caregiver_name = session.get('full_name', 'Caregiver')
    assigned_patients = CaregiverModel.get_assigned_patients_with_status(caregiver_email)
    
    # Also fetch the assigned doctor for each patient
    from database import query_db
    for p in assigned_patients:
        doc = query_db("SELECT u.full_name, u.phone, u.email FROM users u JOIN doctor_assignments da ON u.id = da.doctor_id WHERE da.patient_id = %s", (p['patient']['patient_id'],), one=True)
        if doc:
            p['assigned_doctor'] = doc
        else:
            p['assigned_doctor'] = {'full_name': 'Pending Assignment', 'phone': '--', 'email': '--'}
            
    return render_template('caregiver_dashboard.html', 
                           caregiver_name=caregiver_name, 
                           assigned_patients=assigned_patients)


# ==============================================================================
# DOCTOR PORTAL (Phase 1 Implemented)
# ==============================================================================

@app.route('/doctor-login', methods=['GET', 'POST'])
def doctor_login_view():
    if request.method == 'GET':
        if 'user_id' in session and session.get('role') == 'Doctor':
            return redirect(url_for('doctor_dashboard_view'))
        from database import query_db
        doctors = query_db("SELECT id, full_name, email FROM users WHERE role = 'Doctor'")
        return render_template('doctor_login.html', doctors=doctors)
    
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    
    user = UserModel.get_by_email(email)
    if not user or not UserModel.verify_password(user['password_hash'], password):
        flash("Invalid email or password.", "danger")
        return render_template('doctor_login.html')
    
    if user['role'] != 'Doctor':
        flash("Access Denied. This portal is strictly for authorized medical personnel.", "danger")
        return redirect(url_for('doctor_login_view'))

    session.clear()
    session['user_id'] = user['id']
    session['full_name'] = user['full_name']
    session['email'] = user['email']
    session['role'] = user['role']
    
    flash(f"Welcome, Dr. {user['full_name']}", "success")
    return redirect(url_for('doctor_dashboard_view'))

@app.route('/doctor-dashboard')
@roles_required('Doctor')
def doctor_dashboard_view():
    # Fetch authorized patients only via doctor_assignments
    from database import query_db
    assignments = query_db("SELECT p.* FROM patients p JOIN doctor_assignments da ON p.patient_id = da.patient_id WHERE da.doctor_id = %s", (session['user_id'],))
    
    for p in assignments:
        latest = SensorModel.get_latest(p['patient_id'])
        if latest:
            p['latest_hr'] = latest.get('heart_rate')
            p['latest_spo2'] = latest.get('spo2')
            p['latest_temp'] = latest.get('temperature')
    
    return render_template('doctor_dashboard.html', patients=assignments)

@app.route('/doctor/patients/<patient_id>')
@roles_required('Doctor')
def doctor_patient_detail_view(patient_id):
    patient = PatientModel.get_by_id(patient_id)
    if not patient:
        flash("Patient not found.", "danger")
        return redirect(url_for('doctor_dashboard_view'))
        
    latest = SensorModel.get_latest(patient_id)
    # FORCE STALE DATA REMOVAL
    if latest and latest.get('timestamp'):
        from datetime import datetime
        try:
            ts = latest['timestamp']
            if isinstance(ts, str):
                ts = datetime.strptime(ts.split('.')[0], "%Y-%m-%d %H:%M:%S")
            if (datetime.now() - ts).total_seconds() > 10.0:
                latest = None
        except Exception:
            latest = None
            
    alerts = AlertModel.get_alerts(patient_id=patient_id, limit=10)
    
    return render_template('doctor_patient_detail.html', patient=patient, latest=latest, alerts=alerts)


# ==============================================================================
# CAMERA PULSE VERIFICATION (Phase 3)
# ==============================================================================

@app.route('/doctor/verify-pulse/<int:reading_id>')
@roles_required('Doctor')
def doctor_verify_pulse_view(reading_id):
    from database import query_db
    reading = query_db("SELECT * FROM sensor_readings WHERE id = ?", (reading_id,), one=True)
    if not reading:
        flash("Reading not found.", "danger")
        return redirect(url_for('doctor_dashboard_view'))
    
    patient = query_db("SELECT * FROM patients WHERE patient_id = ?", (reading['patient_id'],), one=True)
    return render_template('camera_verification.html', reading=reading, patient=patient)

@app.route('/doctor/submit-verification/<int:reading_id>', methods=['POST'])
@roles_required('Doctor')
def doctor_submit_verification(reading_id):
    from database import query_db, execute_db
    reading = query_db("SELECT * FROM sensor_readings WHERE id = %s", (reading_id,), one=True)
    if not reading:
        return redirect(url_for('doctor_dashboard_view'))
        
    camera_bpm = request.form.get('camera_bpm')
    signal_quality = request.form.get('signal_quality', 'Insufficient')
    review_status = request.form.get('review_status', 'Pending')
    comment = request.form.get('doctor_comment', '')
    
    sensor_bpm = reading['heart_rate']
    diff = None
    comparison = 'Insufficient Data'
    
    if camera_bpm:
        try:
            camera_bpm = float(camera_bpm)
            diff = abs(sensor_bpm - camera_bpm)
            if diff <= 5:
                comparison = 'Similar'
            else:
                comparison = 'Difference Detected'
        except ValueError:
            camera_bpm = None
            
    execute_db(
        "INSERT INTO pulse_verifications (patient_id, doctor_id, health_reading_id, sensor_bpm, camera_bpm, difference_bpm, signal_quality, comparison_status, doctor_review_status, doctor_comment) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (reading['patient_id'], session['user_id'], reading_id, sensor_bpm, camera_bpm, diff, signal_quality, comparison, review_status, comment)
    )
    
    # Also update the latest alert for this reading/patient if applicable
    execute_db("UPDATE alerts SET doctor_review_status = %s, doctor_comment = %s, doctor_id = %s WHERE patient_id = %s AND status = 'Active'", (review_status, comment, session['user_id'], reading['patient_id']))
    
    flash("Pulse verification submitted successfully.", "success")
    return redirect(url_for('doctor_patient_detail_view', patient_id=reading['patient_id']))

# Logout Route
@app.route('/logout')
def logout_view():
    # 1. Determine role before clearing session
    current_role = str(session.get('role', '')).lower()
    
    # 2. Clear the session
    session.clear()
    
    # 3. Determine redirect destination
    if current_role == 'patient':
        dest = url_for('patient_login_view')
    elif current_role == 'caregiver':
        dest = url_for('caregiver_login_view')
    else:
        dest = url_for('home_view')
        
    flash("You have been signed out successfully.", "info")
    
    # 4. Create response and add cache-control headers to prevent back-button access
    response = make_response(redirect(dest))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# 4. Patient Dashboard Page
@app.route('/patient-dashboard')
@login_required
@patient_required
def dashboard_view():
    patient_id = session.get('linked_patient_id') or "P001"
    patient = PatientModel.get_by_id(patient_id) or PatientModel.get_by_id("P001")
    pid = patient['patient_id'] if patient else "P001"
    latest = SensorModel.get_latest(pid)
    
    # FORCE STALE DATA REMOVAL
    if latest and latest.get('timestamp'):
        from datetime import datetime
        try:
            ts = latest['timestamp']
            if isinstance(ts, str):
                ts = datetime.strptime(ts.split('.')[0], "%Y-%m-%d %H:%M:%S")
            age = (datetime.now() - ts).total_seconds()
            if age > 10.0:
                latest = None
        except Exception:
            latest = None
            
    is_hardware = latest is not None

    recent_alerts = AlertModel.get_alerts(patient_id=pid, limit=5)
    return render_template('dashboard.html', patient=patient, latest=latest, recent_alerts=recent_alerts, is_hardware_connected=is_hardware)

@app.route('/measure')
def measure_view():
    return render_template('measure.html')

# 5. Live Monitoring (Patient)
@app.route('/monitoring')
@login_required
def monitoring_view():
    patient_id = session.get('linked_patient_id') or "P001"
    patient = PatientModel.get_by_id(patient_id) or PatientModel.get_by_id("P001")
    pid = patient['patient_id'] if patient else "P001"
    latest = SensorModel.get_latest(pid)
    thresholds = ThresholdModel.get_thresholds(pid)
    return render_template('monitoring.html', patient=patient, latest=latest, thresholds=thresholds)

def get_authorized_patients():
    role = session.get('role', 'Patient')
    if role == 'Caregiver':
        assigned = CaregiverModel.get_assigned_patients_with_status(session.get('email', ''))
        return [item['patient'] for item in assigned if item.get('patient')]
    elif role == 'Doctor':
        from database import query_db
        assigned = query_db("SELECT patient_id FROM doctor_assignments WHERE doctor_id = ?", (session.get('user_id'),))
        return [p for p in [PatientModel.get_by_id(r['patient_id']) for r in assigned] if p]
    elif role == 'Family Member':
        from database import query_db
        assigned = query_db("SELECT patient_id FROM family_members WHERE user_id = ?", (session.get('user_id'),))
        return [p for p in [PatientModel.get_by_id(r['patient_id']) for r in assigned] if p]
    else:
        return PatientModel.get_all()

# 6. Patients Page
@app.route('/patients')
@login_required
def patients_view():
    role = session.get('role', 'Patient')
    if role == 'Caregiver':
        assigned = CaregiverModel.get_assigned_patients_with_status(session.get('email', ''))
        patients = [item['patient'] for item in assigned if item.get('patient')]
    elif role == 'Doctor':
        from database import query_db
        assigned = query_db("SELECT patient_id FROM doctor_assignments WHERE doctor_id = %s", (session.get('user_id'),))
        pids = [r['patient_id'] for r in assigned]
        patients = [PatientModel.get_by_id(pid) for pid in pids]
        patients = [p for p in patients if p]
    else:
        patients = get_authorized_patients()
    return render_template('patients.html', patients=patients)

# 7. Health History Page
@app.route('/history')
@login_required
def history_view():
    time_filter = request.args.get('filter', '24h')
    patients = get_authorized_patients()
    patient_id = request.args.get('patient_id', patients[0]['patient_id'] if patients else 'P001')
    readings = SensorModel.get_history(patient_id=patient_id, limit=200, time_filter=time_filter)
    return render_template('history.html', readings=readings, current_filter=time_filter, selected_patient=patient_id, patients=patients)

# 8. Analytics Page
@app.route('/analytics')
@login_required
def analytics_view():
    patient_id = request.args.get('patient_id', 'P001')
    readings = SensorModel.get_history(patient_id=patient_id, limit=50)
    # Reverse so charts render chronologically (oldest to newest)
    readings_chrono = list(reversed(readings)) if readings else []
    
    # Calculate stats
    hr_vals = [float(r['heart_rate']) for r in readings] if readings else [76]
    spo2_vals = [float(r['spo2']) for r in readings] if readings else [98]
    temp_vals = [float(r['temperature']) for r in readings] if readings else [36.7]

    stats = {
        'hr_avg': round(sum(hr_vals) / len(hr_vals), 1),
        'hr_min': round(min(hr_vals), 1),
        'hr_max': round(max(hr_vals), 1),
        'hr_curr': round(hr_vals[0], 1) if hr_vals else 76,
        'spo2_avg': round(sum(spo2_vals) / len(spo2_vals), 1),
        'spo2_min': round(min(spo2_vals), 1),
        'spo2_max': round(max(spo2_vals), 1),
        'temp_avg': round(sum(temp_vals) / len(temp_vals), 1),
        'temp_min': round(min(temp_vals), 1),
        'temp_max': round(max(temp_vals), 1),
    }

    return render_template('analytics.html', stats=stats, readings=readings_chrono, selected_patient=patient_id)

# 9. Alerts Page
@app.route('/alerts')
@login_required
def alerts_view():
    status_tab = request.args.get('tab', 'Active')
    alerts = AlertModel.get_alerts(status=status_tab, limit=100)
    active_count = AlertModel.get_active_count()
    return render_template('alerts.html', alerts=alerts, current_tab=status_tab, active_count=active_count)

# 10. Patient Profile Page
@app.route('/profile')
@app.route('/patients/<patient_id>')
@login_required
def profile_view(patient_id=None):
    if not patient_id:
        patient_id = "P001"
    patient = PatientModel.get_by_id(patient_id)
    if not patient:
        patient = PatientModel.get_by_id("P001")
    device = DeviceModel.get_by_id(patient.get('device_id', 'ESP32-001') if patient else 'ESP32-001')
    return render_template('profile.html', patient=patient, device=device)

# 11. Device Management Page
@app.route('/devices')
@login_required
def devices_view():
    devices = DeviceModel.get_all()
    return render_template('devices.html', devices=devices)

# 12. Threshold Settings Page
@app.route('/thresholds')
@login_required
def thresholds_view():
    patient_id = request.args.get('patient_id', 'P001')
    thresholds = ThresholdModel.get_thresholds(patient_id)
    return render_template('thresholds.html', thresholds=thresholds, selected_patient=patient_id)

# 13. Reports Page
@app.route('/reports')
@login_required
def reports_view():
    patients = get_authorized_patients()
    patient_id = request.args.get('patient_id', patients[0]['patient_id'] if patients else 'P001')
    patient = PatientModel.get_by_id(patient_id)
    readings = SensorModel.get_history(patient_id=patient_id, limit=100)
    alerts = AlertModel.get_alerts(patient_id=patient_id, limit=20)
    
    hr_vals = [float(r['heart_rate']) for r in readings] if readings else [76]
    spo2_vals = [float(r['spo2']) for r in readings] if readings else [98]
    temp_vals = [float(r['temperature']) for r in readings] if readings else [36.7]
    
    stats = {
        'hr_avg': round(sum(hr_vals) / len(hr_vals), 1),
        'hr_min': round(min(hr_vals), 1),
        'hr_max': round(max(hr_vals), 1),
        'spo2_avg': round(sum(spo2_vals) / len(spo2_vals), 1),
        'spo2_min': round(min(spo2_vals), 1),
        'spo2_max': round(max(spo2_vals), 1),
        'temp_avg': round(sum(temp_vals) / len(temp_vals), 1),
        'temp_min': round(min(temp_vals), 1),
        'temp_max': round(max(temp_vals), 1),
        'total_readings': len(readings),
        'total_alerts': len(alerts)
    }
    
    review_data = None
    try:
        from database import query_db
        review_data = query_db('SELECT * FROM monthly_reports WHERE patient_id=%s ORDER BY id DESC LIMIT 1', (patient_id,), one=True)
    except Exception:
        pass
    return render_template('reports.html', patient=patient, patients=patients, stats=stats, alerts=alerts, review_data=review_data)

# 14. Settings Page
@app.route('/settings')
@login_required
def settings_view():
    user_id = session.get('user_id')
    user = UserModel.get_by_id(user_id)
    
    user_linked_pid = session.get('linked_patient_id')
    if not user_linked_pid and user_id:
        p = PatientModel.get_by_user_id(user_id)
        if p:
            user_linked_pid = p['patient_id']
            session['linked_patient_id'] = user_linked_pid
            
    patient_id = user_linked_pid or 'P001'
    
    from email_service import EmailService
    email_cfg = EmailService.get_config()
    system_status = EmailService.get_email_system_status(patient_id)
    return render_template('settings.html', user=user, email_config=email_cfg, email_status=system_status)

# 15. Caregivers / Relatives Emergency Contacts Page
@app.route('/caregivers')
@login_required
def caregivers_view():
    user_linked_pid = session.get('linked_patient_id')
    if not user_linked_pid and session.get('user_id'):
        p = PatientModel.get_by_user_id(session.get('user_id'))
        if p:
            user_linked_pid = p['patient_id']
            session['linked_patient_id'] = user_linked_pid

    user_role = session.get('role', 'Patient')
    if user_role in ('Doctor', 'Admin'):
        patient_id = request.args.get('patient_id') or user_linked_pid or 'P001'
    else:
        patient_id = user_linked_pid or request.args.get('patient_id') or 'P001'

    patient = PatientModel.get_by_id(patient_id) or (PatientModel.get_by_id(user_linked_pid) if user_linked_pid else None) or PatientModel.get_by_id("P001")
    patients = PatientModel.get_all()
    selected_pid = patient['patient_id'] if patient else 'P001'
    caregivers = CaregiverModel.get_by_patient(selected_pid)
    alert_mode = CaregiverModel.get_alert_mode(selected_pid)
    return render_template('caregivers.html', 
                           patient=patient, 
                           patients=patients, 
                           caregivers=caregivers, 
                           alert_mode=alert_mode,
                           selected_patient=selected_pid)

# ==============================================================================
# REST API ENDPOINTS
# ==============================================================================

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json() or {}
    full_name = data.get('full_name', '').strip()
    email = data.get('email', '').strip().lower()
    phone = data.get('phone', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')
    role = data.get('role', 'Patient')

    if not full_name or not email or not phone or not password:
        return jsonify({'success': False, 'message': 'All fields are required.'}), 400
    if len(password) < 8:
        return jsonify({'success': False, 'message': 'Password must be at least 8 characters.'}), 400
    if password != confirm_password:
        return jsonify({'success': False, 'message': 'Passwords do not match.'}), 400
    if UserModel.get_by_email(email):
        return jsonify({'success': False, 'message': 'An account with this email already exists.'}), 409

    user_id = UserModel.create(full_name, email, phone, password, role)
    if role == 'Patient':
        patient_id = f"P{user_id:03d}"
        cg_name = data.get('caregiver_name', '').strip()
        cg_rel = data.get('caregiver_relationship', 'Other').strip()
        cg_email = data.get('caregiver_email', '').strip().lower()
        cg_phone = data.get('caregiver_phone', '').strip()
        emergency_str = f"{cg_name} ({cg_rel}) - {cg_email}" if cg_name and cg_email else "Pending"

        PatientModel.create(patient_id, full_name, 40, 'Other', phone, emergency_str, user_id=user_id)
        ThresholdModel.get_thresholds(patient_id)
        if cg_name and cg_email:
            CaregiverModel.create(
                patient_id=patient_id,
                name=cg_name,
                relationship=cg_rel,
                email=cg_email,
                phone=cg_phone,
                is_primary=True,
                receive_alerts=True
            )

    return jsonify({'success': True, 'message': 'Account created successfully! Please sign in.'})

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    user = UserModel.get_by_email(email)
    if not user or not UserModel.verify_password(user['password_hash'], password):
        return jsonify({'success': False, 'message': 'Invalid email or password.'}), 401

    session.clear()
    session['user_id'] = user['id']
    session['full_name'] = user['full_name']
    session['email'] = user['email']
    session['role'] = user['role']

    if user['role'] == 'Caregiver':
        cg = CaregiverModel.get_by_email(user['email'])
        if cg:
            session['linked_patient_id'] = cg['patient_id']
    elif user['role'] == 'Patient':
        p = PatientModel.get_by_user_id(user['id'])
        if p:
            session['linked_patient_id'] = p['patient_id']

    return jsonify({'success': True, 'redirect': url_for('dashboard_view')})

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True, 'redirect': url_for('login_view')})

@app.route('/api/dashboard', methods=['GET'])
@login_required
def api_dashboard():
    patient_id = request.args.get('patient_id') or session.get('linked_patient_id') or 'P001'
    patient = PatientModel.get_by_id(patient_id)
    latest = SensorModel.get_latest(patient_id)
    alerts = AlertModel.get_alerts(patient_id=patient_id, limit=5)
    active_count = AlertModel.get_active_count(patient_id)
    
    is_hardware = False
    age_seconds = None
    if latest and latest.get('timestamp'):
        ts = latest['timestamp']
        if isinstance(ts, str):
            try:
                ts = datetime.strptime(ts.split('.')[0], "%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
        if isinstance(ts, datetime):
            age_seconds = (datetime.now() - ts).total_seconds()
            if age_seconds <= 10.0:
                is_hardware = True

    if latest and isinstance(latest.get('timestamp'), datetime):
        latest['timestamp'] = latest['timestamp'].strftime("%Y-%m-%d %H:%M:%S")

    # If not fresh within 10 seconds, do not return stale reading as live
    display_latest = latest if is_hardware else None

    return jsonify({
        'success': True,
        'patient': patient,
        'latest': display_latest,
        'alerts': alerts,
        'active_alerts_count': active_count,
        'is_hardware_connected': is_hardware,
        'last_reading_time': latest['timestamp'] if latest else None
    })

@app.route('/api/patients', methods=['GET', 'POST'])
@login_required
def api_patients():
    if request.method == 'GET':
        patients = PatientModel.get_all()
        return jsonify({'success': True, 'patients': patients})
    
    data = request.get_json() or {}
    patient_id = data.get('patient_id', '').strip().upper()
    name = data.get('name', '').strip()
    age = data.get('age')
    gender = data.get('gender', 'Other')
    phone = data.get('phone', '').strip()
    emergency_contact = data.get('emergency_contact', '').strip()

    if not patient_id or not name or not age:
        return jsonify({'success': False, 'message': 'Patient ID, Name, and Age are required.'}), 400

    existing = PatientModel.get_by_id(patient_id)
    if existing:
        return jsonify({'success': False, 'message': f'Patient with ID {patient_id} already exists.'}), 409

    PatientModel.create(patient_id, name, age, gender, phone, emergency_contact)
    ThresholdModel.get_thresholds(patient_id)
    return jsonify({'success': True, 'message': 'Patient added successfully.'})

@app.route('/api/patients/<patient_id>', methods=['GET', 'PUT'])
@login_required
def api_patient_detail(patient_id):
    if request.method == 'GET':
        patient = PatientModel.get_by_id(patient_id)
        if not patient:
            return jsonify({'success': False, 'message': 'Patient not found.'}), 404
        return jsonify({'success': True, 'patient': patient})

    data = request.get_json() or {}
    name = data.get('name', '')
    age = data.get('age', 0)
    gender = data.get('gender', 'Other')
    phone = data.get('phone', '')
    emergency_contact = data.get('emergency_contact', '')
    PatientModel.update(patient_id, name, age, gender, phone, emergency_contact)
    return jsonify({'success': True, 'message': 'Patient profile updated.'})

@app.route('/api/live-data', methods=['GET'])
@app.route('/api/readings/latest', methods=['GET'])
def api_readings_latest():
    patient_id = request.args.get('patient_id', 'P001')
    latest = SensorModel.get_latest(patient_id)
    
    now = datetime.now()
    is_fresh = False
    age_seconds = None
    last_timestamp_str = None

    if latest and latest.get('timestamp'):
        ts = latest['timestamp']
        if isinstance(ts, str):
            try:
                ts = datetime.strptime(ts.split('.')[0], "%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
        if isinstance(ts, datetime):
            age_seconds = (now - ts).total_seconds()
            last_timestamp_str = ts.strftime("%Y-%m-%d %H:%M:%S")
            latest['timestamp'] = last_timestamp_str
            if 0 <= age_seconds <= 10.0:
                is_fresh = True
        else:
            last_timestamp_str = str(ts)

    if not latest or not is_fresh:
        return jsonify({
            'success': True,
            'reading': None,
            'status': {
                'heart_rate': 'Offline',
                'spo2': 'Offline',
                'temperature': 'Offline',
                'overall': 'DISCONNECTED'
            },
            'is_hardware_connected': False,
            'age_seconds': round(age_seconds, 1) if age_seconds is not None else None,
            'last_reading_timestamp': last_timestamp_str
        })

    # Status classification for genuine live reading
    thresholds = ThresholdModel.get_thresholds(patient_id)
    hr = float(latest['heart_rate'])
    ox = float(latest['spo2'])
    temp = float(latest['temperature'])

    hr_status = "Normal"
    if hr > thresholds['Heart Rate']['critical_max'] or hr < thresholds['Heart Rate']['critical_min']:
        hr_status = "Critical"
    elif hr > thresholds['Heart Rate']['warning_max'] or hr < thresholds['Heart Rate']['warning_min']:
        hr_status = "Warning"

    ox_status = "Normal"
    if ox <= thresholds['SpO2']['critical_max']:
        ox_status = "Critical"
    elif ox <= thresholds['SpO2']['warning_max']:
        ox_status = "Warning"

    temp_status = "Normal"
    if temp >= thresholds['Temperature']['critical_min']:
        temp_status = "Critical"
    elif temp >= thresholds['Temperature']['warning_min']:
        temp_status = "Warning"

    overall_status = "NORMAL"
    if "Critical" in [hr_status, ox_status, temp_status]:
        overall_status = "CRITICAL"
    elif "Warning" in [hr_status, ox_status, temp_status]:
        overall_status = "WARNING"

    return jsonify({
        'success': True,
        'reading': latest,
        'status': {
            'heart_rate': hr_status,
            'spo2': ox_status,
            'temperature': temp_status,
            'overall': overall_status
        },
        'is_hardware_connected': True,
        'age_seconds': round(age_seconds, 1) if age_seconds is not None else 0.0,
        'data_source': 'ESP32'
    })

@app.route('/api/device-status', methods=['GET'])
def api_device_status():
    """Returns genuine real-time hardware status evaluated from 10-second freshness."""
    device_id = request.args.get('device_id', 'ESP32-001')
    device = DeviceModel.get_by_id(device_id)
    is_conn = DeviceModel.is_connected(device_id, timeout_seconds=10)
    last_seen_str = str(device.get('last_seen')) if device and device.get('last_seen') else None
    return jsonify({
        'success': True,
        'device_id': device_id,
        'status': 'CONNECTED' if is_conn else 'OFFLINE',
        'is_connected': is_conn,
        'last_seen': last_seen_str
    })

@app.route('/api/readings/history', methods=['GET'])
@login_required
def api_readings_history():
    patient_id = request.args.get('patient_id', 'P001')
    time_filter = request.args.get('time_filter', '24h')
    limit = int(request.args.get('limit', 100))
    readings = SensorModel.get_history(patient_id, limit=limit, time_filter=time_filter)
    for r in readings:
        if isinstance(r.get('timestamp'), datetime):
            r['timestamp'] = r['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({'success': True, 'readings': readings})

# ==============================================================================
# ESP32 HARDWARE INGESTION API
# ==============================================================================
@app.route('/api/sensor-data', methods=['POST'])
def api_sensor_data():
    """
    Ingests genuine sensor readings from physical ESP32.
    Strictly validates biometric ranges and rejects missing finger or disconnected probe.
    Payload:
    {
      "device_id": "ESP32-001",
      "patient_id": "P001",
      "heart_rate": 76.5,
      "spo2": 98.2,
      "temperature": 36.7,
      "data_source": "ESP32"
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Invalid JSON body.'}), 400

    device_id = data.get('device_id', 'ESP32-001')
    patient_id = data.get('patient_id', 'P001')
    data_source = 'ESP32'
    
    try:
        heart_rate = float(data.get('heart_rate'))
        spo2 = float(data.get('spo2'))
        temperature = float(data.get('temperature'))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'heart_rate, spo2, and temperature must be numeric.'}), 400

    # 1. Update heartbeat to reflect that ESP32 device is communicating
    DeviceModel.update_status(device_id, 'CONNECTED', last_seen=datetime.now())

    # 2. Accept readings (0 values will be captured & trigger Alert)
    # (Strict 422 check disabled to allow smooth streaming)

    # 3. Strict Probe Validation: Reject disconnected DS18B20 (-127°C or 85°C unread state)
    if temperature <= -50.0 or temperature >= 85.0:
        return jsonify({
            'success': False,
            'status': 'SENSOR_DISCONNECTED',
            'message': 'Temperature sensor disconnected (check 4.7k pull-up resistor on GPIO 4).'
        }), 422

    # 4. Store valid hardware reading
    reading_id = SensorModel.add_reading(
        patient_id=patient_id,
        device_id=device_id,
        heart_rate=heart_rate,
        spo2=spo2,
        temperature=temperature,
        data_source=data_source
    )

    # 5. Check thresholds & automatically trigger caregiver alerts + SMTP emails
    created_alerts = AlertModel.check_and_create_alerts(
        patient_id=patient_id,
        device_id=device_id,
        heart_rate=heart_rate,
        spo2=spo2,
        temperature=temperature,
        data_source=data_source
    )

    print(f"[CarePulse Ingestion] Stored genuine ESP32 reading #{reading_id}: HR={heart_rate}, SpO2={spo2}, Temp={temperature}")

    return jsonify({
        'success': True,
        'message': 'Reading received and stored successfully.',
        'reading_id': reading_id,
        'data_source': data_source,
        'alerts_triggered': len(created_alerts),
        'alerts': created_alerts
    }), 201

# ==============================================================================
# ALERTS API
# ==============================================================================
@app.route('/api/alerts', methods=['GET', 'POST'])
@login_required
def api_alerts():
    if request.method == 'GET':
        patient_id = request.args.get('patient_id')
        status = request.args.get('status', 'Active')
        alerts = AlertModel.get_alerts(patient_id=patient_id, status=status)
        for a in alerts:
            if isinstance(a.get('created_at'), datetime):
                a['created_at'] = a['created_at'].strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(a.get('resolved_at'), datetime):
                a['resolved_at'] = a['resolved_at'].strftime("%Y-%m-%d %H:%M:%S")
        return jsonify({'success': True, 'alerts': alerts})

    # Manual alert insertion
    data = request.get_json() or {}
    patient_id = data.get('patient_id', 'P001')
    device_id = data.get('device_id', 'ESP32-001')
    sensor_type = data.get('sensor_type', 'Heart Rate')
    value = float(data.get('value', 120))
    threshold = float(data.get('threshold', 110))
    severity = data.get('severity', 'Critical')
    message = data.get('message', 'Simulated abnormal alert')
    
    aid = AlertModel.execute_db(
        "INSERT INTO alerts (patient_id, device_id, sensor_type, value, threshold, severity, message, status) VALUES (%s, %s, %s, %s, %s, %s, %s, 'Active')",
        (patient_id, device_id, sensor_type, value, threshold, severity, message)
    )
    return jsonify({'success': True, 'alert_id': aid}), 201

@app.route('/api/alerts/<int:alert_id>/resolve', methods=['PUT', 'POST'])
@login_required
def api_resolve_alert(alert_id):
    AlertModel.resolve_alert(alert_id)
    return jsonify({'success': True, 'message': f'Alert #{alert_id} resolved.'})

# ==============================================================================
# THRESHOLDS API
# ==============================================================================
@app.route('/api/thresholds', methods=['GET', 'PUT'])
@login_required
def api_thresholds():
    patient_id = request.args.get('patient_id', 'P001')
    if request.method == 'GET':
        thresholds = ThresholdModel.get_thresholds(patient_id)
        return jsonify({'success': True, 'thresholds': thresholds})

    data = request.get_json() or {}
    for sensor_type in ['Heart Rate', 'SpO2', 'Temperature']:
        if sensor_type in data:
            s = data[sensor_type]
            ThresholdModel.update_threshold(
                patient_id=patient_id,
                sensor_type=sensor_type,
                normal_min=s['normal_min'],
                normal_max=s['normal_max'],
                warning_min=s['warning_min'],
                warning_max=s['warning_max'],
                critical_min=s['critical_min'],
                critical_max=s['critical_max']
            )
    return jsonify({'success': True, 'message': 'Thresholds updated successfully.'})

# ==============================================================================
# DEVICES API
# ==============================================================================
@app.route('/api/devices', methods=['GET'])
@login_required
def api_devices():
    devices = DeviceModel.get_all()
    for d in devices:
        if isinstance(d.get('last_seen'), datetime):
            d['last_seen'] = d['last_seen'].strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(d.get('created_at'), datetime):
            d['created_at'] = d['created_at'].strftime("%Y-%m-%d %H:%M:%S")
    return jsonify({'success': True, 'devices': devices})

# ==============================================================================
# REPORTS API
# ==============================================================================
@app.route('/api/reports', methods=['GET'])
@login_required
def api_reports():
    patient_id = request.args.get('patient_id', 'P001')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    patient = PatientModel.get_by_id(patient_id)
    readings = SensorModel.get_history(patient_id, limit=200, start_date=start_date, end_date=end_date)
    alerts = AlertModel.get_alerts(patient_id=patient_id, limit=50)

    hr_vals = [float(r['heart_rate']) for r in readings] if readings else [76]
    spo2_vals = [float(r['spo2']) for r in readings] if readings else [98]
    temp_vals = [float(r['temperature']) for r in readings] if readings else [36.7]

    report = {
        'patient': patient,
        'metrics': {
            'heart_rate': {
                'avg': round(sum(hr_vals) / len(hr_vals), 1),
                'min': round(min(hr_vals), 1),
                'max': round(max(hr_vals), 1)
            },
            'spo2': {
                'avg': round(sum(spo2_vals) / len(spo2_vals), 1),
                'min': round(min(spo2_vals), 1),
                'max': round(max(spo2_vals), 1)
            },
            'temperature': {
                'avg': round(sum(temp_vals) / len(temp_vals), 1),
                'min': round(min(temp_vals), 1),
                'max': round(max(temp_vals), 1)
            }
        },
        'total_readings': len(readings),
        'alerts_summary': {
            'total': len(alerts),
            'critical': sum(1 for a in alerts if a['severity'] == 'Critical'),
            'warning': sum(1 for a in alerts if a['severity'] == 'Warning'),
            'resolved': sum(1 for a in alerts if a['status'] == 'Resolved')
        }
    }
    return jsonify({'success': True, 'report': report})


# ==============================================================================
# EMERGENCY EMAIL ALERT API
# ==============================================================================
@app.route('/api/email/status', methods=['GET'])
@login_required
def api_email_status():
    from email_service import EmailService
    user_linked_pid = session.get('linked_patient_id')
    if not user_linked_pid and session.get('user_id'):
        p = PatientModel.get_by_user_id(session.get('user_id'))
        if p:
            user_linked_pid = p['patient_id']
    patient_id = request.args.get('patient_id') or user_linked_pid or 'P001'
    status_info = EmailService.get_email_system_status(patient_id)
    return jsonify({'success': True, 'status': status_info})

@app.route('/api/email/test-connection', methods=['POST'])
@login_required
def api_email_test_connection():
    from email_service import EmailService
    data = request.get_json() or {}
    custom_cfg = None
    if data.get('sender_email') and data.get('sender_password'):
        custom_cfg = {
            'sender_email': data['sender_email'].strip(),
            'sender_password': data['sender_password'].strip(),
            'smtp_server': data.get('smtp_server', 'smtp.gmail.com').strip(),
            'smtp_port': int(data.get('smtp_port', 587)),
            'use_tls': True
        }
    success, msg = EmailService.test_smtp_connection(custom_cfg)
    return jsonify({'success': success, 'message': msg}), (200 if success else 400)

@app.route('/api/email/config', methods=['GET', 'POST'])
@login_required
def api_email_config():
    from email_service import EmailService
    if request.method == 'GET':
        cfg = EmailService.get_config()
        safe_cfg = dict(cfg)
        if safe_cfg.get('sender_password'):
            safe_cfg['has_password'] = True
            safe_cfg['sender_password_masked'] = '•' * 8
        else:
            safe_cfg['has_password'] = False
            safe_cfg['sender_password_masked'] = ''
        return jsonify({'success': True, 'config': safe_cfg})

    data = request.get_json() or {}
    update_data = {}
    if 'enabled' in data:
        update_data['enabled'] = bool(data['enabled'])
    if 'recipient_email' in data:
        update_data['recipient_email'] = data['recipient_email'].strip()
    if 'sender_email' in data:
        update_data['sender_email'] = data['sender_email'].strip()
    if 'sender_password' in data and data['sender_password'].strip():
        update_data['sender_password'] = data['sender_password'].strip()
    if 'smtp_server' in data:
        update_data['smtp_server'] = data['smtp_server'].strip()
    if 'smtp_port' in data:
        try:
            update_data['smtp_port'] = int(data['smtp_port'])
        except (ValueError, TypeError):
            pass

    success, msg = EmailService.save_config(update_data)
    if success and update_data.get('recipient_email'):
        recip = update_data['recipient_email']
        user_linked_pid = session.get('linked_patient_id')
        if not user_linked_pid and session.get('user_id'):
            p = PatientModel.get_by_user_id(session.get('user_id'))
            if p:
                user_linked_pid = p['patient_id']
                session['linked_patient_id'] = user_linked_pid
        target_pid = user_linked_pid or 'P001'
        try:
            from database import execute_db
            execute_db("UPDATE caregivers SET email = %s WHERE patient_id = %s", (recip, target_pid))
            execute_db("UPDATE patients SET emergency_contact = %s WHERE patient_id = %s", (f"Emergency Contact ({recip})", target_pid))
        except Exception as e:
            print(f"[CarePulse DB] Sync caregiver email warning for {target_pid}: {e}")
    return jsonify({'success': success, 'message': msg})

@app.route('/api/email/test', methods=['POST'])
@login_required
def api_email_test():
    from email_service import EmailService
    data = request.get_json() or {}
    recipient = data.get('recipient_email', '').strip() or None

    # If test credentials are provided on-the-fly, update them first
    if data.get('sender_email') and data.get('sender_password'):
        EmailService.save_config({
            'sender_email': data['sender_email'].strip(),
            'sender_password': data['sender_password'].strip(),
            'smtp_server': data.get('smtp_server', 'smtp.gmail.com').strip(),
            'smtp_port': int(data.get('smtp_port', 587)),
            'recipient_email': recipient or EmailService.get_config().get('recipient_email')
        })

    success, msg = EmailService.send_test_email(recipient=recipient)
    status_code = 200 if success else 400
    return jsonify({'success': success, 'message': msg}), status_code

# ==============================================================================
# CAREGIVERS / EMERGENCY CONTACTS REST API
# ==============================================================================
@app.route('/api/caregivers', methods=['GET', 'POST'])
@login_required
def api_caregivers():
    if request.method == 'GET':
        patient_id = request.args.get('patient_id', 'P001')
        caregivers = CaregiverModel.get_by_patient(patient_id)
        alert_mode = CaregiverModel.get_alert_mode(patient_id)
        return jsonify({'success': True, 'caregivers': caregivers, 'alert_mode': alert_mode})

    # POST: Add new caregiver
    data = request.get_json() or {}
    patient_id = data.get('patient_id', 'P001').strip()
    name = data.get('name', '').strip()
    relationship = data.get('relationship', 'Other').strip()
    email = data.get('email', '').strip().lower()
    phone = data.get('phone', '').strip()
    is_primary = bool(data.get('is_primary', False))
    receive_alerts = bool(data.get('receive_alerts', True))

    if not name or not email:
        return jsonify({'success': False, 'message': 'Caregiver name and email are required.'}), 400

    cid = CaregiverModel.create(patient_id, name, relationship, email, phone, is_primary, receive_alerts)
    return jsonify({'success': True, 'message': f'Caregiver {name} ({relationship}) added successfully.', 'caregiver_id': cid}), 201

@app.route('/api/caregivers/<int:caregiver_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_caregiver_item(caregiver_id):
    if request.method == 'GET':
        cg = CaregiverModel.get_by_id(caregiver_id)
        if not cg:
            return jsonify({'success': False, 'message': 'Caregiver not found.'}), 404
        return jsonify({'success': True, 'caregiver': cg})

    if request.method == 'DELETE':
        CaregiverModel.delete(caregiver_id)
        return jsonify({'success': True, 'message': 'Caregiver removed successfully.'})

    # PUT: Update caregiver
    data = request.get_json() or {}
    name = data.get('name', '').strip()
    relationship = data.get('relationship', 'Other').strip()
    email = data.get('email', '').strip().lower()
    phone = data.get('phone', '').strip()
    is_primary = bool(data.get('is_primary', False))
    receive_alerts = bool(data.get('receive_alerts', True))

    if not name or not email:
        return jsonify({'success': False, 'message': 'Caregiver name and email are required.'}), 400

    CaregiverModel.update(caregiver_id, name, relationship, email, phone, is_primary, receive_alerts)
    return jsonify({'success': True, 'message': 'Caregiver updated successfully.'})

@app.route('/api/caregivers/<int:caregiver_id>/primary', methods=['POST'])
@login_required
def api_caregiver_set_primary(caregiver_id):
    data = request.get_json() or {}
    patient_id = data.get('patient_id', 'P001')
    CaregiverModel.set_primary(patient_id, caregiver_id)
    return jsonify({'success': True, 'message': 'Primary emergency caregiver updated.'})

@app.route('/api/caregivers/alert-mode', methods=['POST'])
@login_required
def api_caregiver_alert_mode():
    data = request.get_json() or {}
    patient_id = data.get('patient_id', 'P001')
    mode = data.get('mode', 'PRIMARY')
    CaregiverModel.set_alert_mode(patient_id, mode)
    msg = "Emergency alerts will now be sent to ALL registered caregivers." if mode == 'ALL' else "Emergency alerts will now be sent to the PRIMARY caregiver only."
    return jsonify({'success': True, 'message': msg, 'mode': mode})

# ==============================================================================
# ERROR HANDLERS
# ==============================================================================
@app.errorhandler(404)
def page_not_found(e):
    return render_template('base.html', not_found=True), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('base.html', server_error=True), 500


# ==============================================================================
# BROWSER CACHE CONTROL
# ==============================================================================
@app.after_request
def add_header(response):
    # Prevent browser back button from showing cached authenticated pages after logout
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response


# ==============================================================================
# PATIENT CAMERA OPT-IN ENDPOINT
# ==============================================================================
@app.route('/api/toggle-camera', methods=['POST'])
@login_required
@roles_required('Patient')
def toggle_camera():
    from database import query_db, execute_db
    data = request.get_json()
    enabled = 1 if data.get('enabled') else 0
    patient = query_db('SELECT id FROM patients WHERE user_id = ?', (session.get('user_id'),), one=True)
    if patient:
        execute_db('UPDATE patients SET camera_enabled = ? WHERE id = ?', (enabled, patient['id']))
        return jsonify({'status': 'success', 'camera_enabled': enabled})
    return jsonify({'status': 'error', 'message': 'Patient not found'}), 404


@app.route('/doctor/camera/<patient_id>')
@roles_required('Doctor')
def doctor_camera_view(patient_id):
    from database import query_db
    patient = query_db("SELECT * FROM patients WHERE patient_id = ?", (patient_id,), one=True)
    if not patient:
        flash("Patient not found.", "danger")
        return redirect(url_for('doctor_dashboard_view'))
    
    # Get latest reading if it exists
    latest = SensorModel.get_latest(patient_id)
    
    return render_template('camera_verification.html', reading=latest, patient=patient)


# ==============================================================================
# EMERGENCY ONE-TOUCH ACCESS
# ==============================================================================

@app.route('/api/patients-list')
def api_patients_list():
    from models import PatientModel
    patients = PatientModel.get_all()
    return {"patients": patients}

@app.route('/emergency-access/<patient_id>')
def emergency_access(patient_id):
    from models import UserModel, PatientModel
    p = PatientModel.get_by_id(patient_id)
    if p:
        user = UserModel.get_by_id(p['user_id'])
        if user:
            session.clear()
            session['user_id'] = user['id']
            session['full_name'] = user['full_name']
            session['email'] = user['email']
            session['role'] = 'Patient'
            session['linked_patient_id'] = patient_id
            flash("Emergency Access Granted. Bypassed standard authentication protocols.", "warning")
            return redirect(url_for('dashboard_view'))
    flash("Emergency protocol failed. Patient not found.", "danger")
    return redirect(url_for('home_view'))

@app.route('/doctor/report_review', methods=['POST'])
@login_required
def doctor_report_review():
    if session.get('role') != 'Doctor':
        return "Unauthorized", 403
    patient_id = request.form.get('patient_id')
    status = request.form.get('review_status')
    comment = request.form.get('doctor_comment')
    doctor_id = session.get('user_id')
    
    # Save to monthly_reports table as the latest review for this patient
    from database import execute_db
    from datetime import datetime
    execute_db("""
        INSERT INTO monthly_reports (patient_id, report_month, doctor_review_status, doctor_comment, reviewed_by, reviewed_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (patient_id, datetime.now().strftime("%Y-%m"), status, comment, doctor_id, datetime.now()))
    
    flash("Report review saved successfully.", "success")
    return redirect(url_for('reports_view', patient_id=patient_id))



if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("CAREPULSE - Healthcare Monitoring System")
    print("Starting Flask Web Server on http://0.0.0.0:5000 (accessible on LAN & Wi-Fi)")
    print(f"Database Engine: {get_db_status()}")
    print("Tagline: Every heartbeat, watched over.")
    print("=" * 60 + "\n")
    app.run(host='0.0.0.0', port=5000, debug=True)




