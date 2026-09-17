
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash
from models import UserModel, PatientModel, DeviceModel
from database import query_db, execute_db
import bcrypt

admin_bp = Blueprint('admin_bp', __name__, url_prefix='/admin')

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'Admin':
            flash("Access restricted to Administrators.", "danger")
            return redirect(url_for('home_view'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'GET':
        if 'user_id' in session and session.get('role') == 'Admin':
            return redirect(url_for('admin_bp.admin_dashboard'))
        return render_template('admin_login.html')
    
    login_id = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    
    user = UserModel.get_by_email(login_id)
    if not user:
        # Check by username or admin role
        user = query_db("SELECT * FROM users WHERE LOWER(full_name) = %s OR LOWER(email) = %s", (login_id, login_id), one=True)
        if not user and login_id in ('admin', 'administrator', 'carepulse_admin'):
            user = query_db("SELECT * FROM users WHERE role = 'Admin' LIMIT 1", one=True)
    if not user or not UserModel.verify_password(user['password_hash'], password):
        flash("Invalid admin credentials.", "danger")
        return render_template('admin_login.html')
    
    if user['role'] != 'Admin':
        flash("Not an Admin account.", "danger")
        return redirect(url_for('admin_bp.admin_login'))

    session.clear()
    session['user_id'] = user['id']
    session['full_name'] = user['full_name']
    session['email'] = user['email']
    session['role'] = user['role']
    
    flash("Welcome, Admin.", "success")
    return redirect(url_for('admin_bp.admin_dashboard'))

@admin_bp.route('/dashboard')
@admin_required
def admin_dashboard():
    users = query_db("SELECT * FROM users")
    patients = query_db("SELECT * FROM patients")
    devices = query_db("SELECT * FROM devices")
    alerts = query_db("SELECT * FROM alerts WHERE status='Active'")
    return render_template('admin_dashboard.html', users=users, patients=patients, devices=devices, alerts=alerts)

@admin_bp.route('/users')
@admin_required
def manage_users():
    users = query_db("SELECT * FROM users")
    
    # Build a lookup for patient_id -> Patient User Name
    patients = query_db("SELECT p.patient_id, u.full_name FROM patients p JOIN users u ON p.user_id = u.id")
    pid_to_name = {p['patient_id']: p['full_name'] for p in patients}
    uid_to_pid = {p['user_id']: p['patient_id'] for p in query_db("SELECT user_id, patient_id FROM patients")}
    
    # Mappings
    doctor_assigns = query_db("SELECT doctor_id, patient_id FROM doctor_assignments")
    doc_map = {d['doctor_id']: d['patient_id'] for d in doctor_assigns}
    doc_reverse = {d['patient_id']: d['doctor_id'] for d in doctor_assigns}
    
    email_to_uid = {u['email'].lower(): u['id'] for u in users}
    cg_assigns = query_db("SELECT email, patient_id FROM caregivers")
    cg_map = {}
    for c in cg_assigns:
        uid = email_to_uid.get(c['email'].lower())
        if uid:
            cg_map[uid] = c['patient_id']
    cg_reverse = {v: k for k, v in cg_map.items()}
    
    fam_assigns = query_db("SELECT user_id, patient_id FROM family_members WHERE user_id IS NOT NULL")
    fam_map = {f['user_id']: f['patient_id'] for f in fam_assigns}
    fam_reverse = {f['patient_id']: f['user_id'] for f in fam_assigns}
    
    uid_to_name = {u['id']: u['full_name'] for u in users}
    
    enhanced_users = []
    for u in users:
        u_dict = dict(u)
        relations = []
        uid = u_dict['id']
        role = u_dict['role']
        
        if role == 'Patient':
            pid = uid_to_pid.get(uid)
            if pid:
                doc_uid = doc_reverse.get(pid)
                if doc_uid: relations.append(f"Doctor: {uid_to_name.get(doc_uid)}")
                fam_uid = fam_reverse.get(pid)
                if fam_uid: relations.append(f"Family: {uid_to_name.get(fam_uid)}")
        elif role == 'Doctor':
            pid = doc_map.get(uid)
            if pid:
                relations.append(f"Patient: {pid_to_name.get(pid, pid)}")
                fam_uid = fam_reverse.get(pid)
                if fam_uid: relations.append(f"Family: {uid_to_name.get(fam_uid)}")
                cg_uid = cg_reverse.get(pid)
                if cg_uid: relations.append(f"Caregiver: {uid_to_name.get(cg_uid)}")
        elif role == 'Caregiver':
            pid = cg_map.get(uid)
            if pid:
                relations.append(f"Patient: {pid_to_name.get(pid, pid)}")
                doc_uid = doc_reverse.get(pid)
                if doc_uid: relations.append(f"Doctor: {uid_to_name.get(doc_uid)}")
                fam_uid = fam_reverse.get(pid)
                if fam_uid: relations.append(f"Family: {uid_to_name.get(fam_uid)}")
        elif role == 'Family Member':
            pid = fam_map.get(uid)
            if pid:
                relations.append(f"Patient: {pid_to_name.get(pid, pid)}")
                doc_uid = doc_reverse.get(pid)
                if doc_uid: relations.append(f"Doctor: {uid_to_name.get(doc_uid)}")
                cg_uid = cg_reverse.get(pid)
                if cg_uid: relations.append(f"Caregiver: {uid_to_name.get(cg_uid)}")
            
        u_dict['relations'] = " | ".join(relations) if relations else "None"
        enhanced_users.append(u_dict)
        
    return render_template('admin_users.html', users=enhanced_users)

@admin_bp.route('/users/edit', methods=['POST'])
@admin_required
def edit_user():
    user_id = request.form.get('user_id')
    full_name = request.form.get('full_name')
    email = request.form.get('email')
    role = request.form.get('role')
    
    if user_id and full_name and email and role:
        execute_db('UPDATE users SET full_name = ?, email = ?, role = ? WHERE id = ?', (full_name, email, role, user_id))
        flash('User updated successfully.', 'success')
    else:
        flash('Missing fields.', 'danger')
        
    return redirect(url_for('admin_bp.manage_users'))



@admin_bp.route('/api/toggle-camera', methods=['POST'])
@admin_required
def admin_toggle_camera():
    data = request.get_json()
    enabled = 1 if data.get('enabled') else 0
    patient_id = data.get('patient_id')
    execute_db('UPDATE patients SET camera_enabled = ? WHERE patient_id = ?', (enabled, patient_id))
    return jsonify({'status': 'success'})

@admin_bp.route('/users/delete', methods=['POST'])
@admin_required
def delete_user():
    user_id = request.form.get('user_id')
    if user_id:
        # Also clean up relationships if needed, but for now just delete the user
        execute_db('DELETE FROM users WHERE id = ?', (user_id,))
        flash('User deleted successfully.', 'success')
    else:
        flash('Missing user ID.', 'danger')
    return redirect(url_for('admin_bp.manage_users'))

@admin_bp.route('/users/add', methods=['POST'])
@admin_required
def add_user():
    full_name = request.form.get('full_name')
    email = request.form.get('email')
    password = request.form.get('password')
    role = request.form.get('role')
    
    if full_name and email and password and role:
        from models import UserModel
        try:
            UserModel.create(full_name, email, '0000000000', password, role, is_verified=1)
            flash('User created successfully.', 'success')
        except Exception as e:
            flash(f'Error creating user: {e}', 'danger')
    else:
        flash('Missing fields.', 'danger')
    return redirect(url_for('admin_bp.manage_users'))

@admin_bp.route('/users/toggle_verify', methods=['POST'])
@admin_required
def toggle_verify():
    user_id = request.form.get('user_id')
    status = request.form.get('status')
    if user_id and status is not None:
        new_status = 1 if status == '1' else 0
        execute_db('UPDATE users SET is_verified = ? WHERE id = ?', (new_status, user_id))
        flash('User verification status updated.', 'success')
    return redirect(url_for('admin_bp.manage_users'))
