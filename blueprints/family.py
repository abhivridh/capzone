
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from models import UserModel, PatientModel, SensorModel, AlertModel
from database import query_db

family_bp = Blueprint('family_bp', __name__, url_prefix='/family')

def family_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'Family Member':
            flash("Access restricted to Family Members.", "danger")
            return redirect(url_for('home_view'))
        return f(*args, **kwargs)
    return decorated_function

@family_bp.route('/login', methods=['GET', 'POST'])
def family_login():
    if request.method == 'GET':
        if 'user_id' in session and session.get('role') == 'Family Member':
            return redirect(url_for('family_bp.family_dashboard'))
        from database import query_db
        families = query_db("SELECT id, full_name, email FROM users WHERE role = 'Family Member'")
        return render_template('family_login.html', families=families)
    
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    
    user = UserModel.get_by_email(email)
    if not user or not UserModel.verify_password(user['password_hash'], password):
        flash("Invalid credentials.", "danger")
        return render_template('family_login.html')
    
    if user['role'] != 'Family Member':
        flash("Not a Family Member account.", "danger")
        return redirect(url_for('family_bp.family_login'))

    session.clear()
    session['user_id'] = user['id']
    session['full_name'] = user['full_name']
    session['email'] = user['email']
    session['role'] = user['role']
    
    flash("Welcome back.", "success")
    return redirect(url_for('family_bp.family_dashboard'))

@family_bp.route('/dashboard')
@family_required
def family_dashboard():
    fm_id = session.get('user_id')
    links = query_db("SELECT patient_id FROM family_members WHERE user_id=?", (fm_id,))
    assigned_patients = []
    if links:
        for link in links:
            pid = link['patient_id']
            p = PatientModel.get_by_id(pid)
            latest = SensorModel.get_latest(pid)
            recent_alerts = AlertModel.get_alerts(patient_id=pid, limit=3)
            
            # Fetch Doctor
            doc = query_db("SELECT u.full_name, u.phone, u.email FROM users u JOIN doctor_assignments da ON u.id = da.doctor_id WHERE da.patient_id = ?", (pid,), one=True)
            assigned_doctor = doc if doc else {'full_name': 'Pending Assignment', 'phone': '--', 'email': '--'}
            
            # Check camera status
            cam = query_db("SELECT is_active FROM camera_monitoring_sessions WHERE patient_id = ?", (pid,), one=True)
            cam_active = bool(cam['is_active']) if cam else False
            
            assigned_patients.append({
                'patient': p,
                'latest_reading': latest,
                'recent_alerts': recent_alerts,
                'assigned_doctor': assigned_doctor,
                'camera_active': cam_active
            })
    return render_template('family_dashboard.html', assigned_patients=assigned_patients)

@family_bp.route('/camera/<patient_id>')
@family_required
def family_camera_view(patient_id):
    p = PatientModel.get_by_id(patient_id)
    if not p:
        flash("Patient not found.", "danger")
        return redirect(url_for('family_bp.family_dashboard'))
    
    # We need to fetch the camera_enabled setting manually from raw db because PatientModel might not expose it if not updated.
    p_raw = query_db("SELECT * FROM patients WHERE patient_id = ?", (patient_id,), one=True)
    
    latest = SensorModel.get_latest(patient_id)
    return render_template('camera_verification.html', reading=latest, patient=p_raw)
