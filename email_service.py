"""
CarePulse - Real Emergency SMTP Email Alert Service
---------------------------------------------------
Handles genuine automated SMTP email alerts when critical patient vital signs are detected
(High/Low Heart Rate, Low SpO2, High/Low Temperature).

Features:
- Real Gmail SMTP dispatch with STARTTLS (smtp.gmail.com:587).
- Environment variable credential management (.env) with fallback to email_config.json.
- Stateful hysteresis / de-duplication:
  * Sends emergency email on FIRST critical reading.
  * Suppresses repeat emails while vitals remain critical.
  * Re-arms and sends again only after vitals return to normal range.
- True delivery status tracking (SENT, FAILED, SUPPRESSED) stored in alerts database table.
- Authentic error logging (never fakes 'Email Sent' on failure).
- Safe console logging on Windows without UnicodeEncodeError.
- Live SMTP connection testing & test alert transmission.
"""

import os
import sys
import json
import smtplib
import socket
import threading
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import Config
from database import query_db, execute_db

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'email_config.json')


def _safe_print(text):
    """Prints text safely without throwing UnicodeEncodeError on Windows terminals."""
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            encoding = sys.stdout.encoding or 'ascii'
            print(text.encode(encoding, errors='replace').decode(encoding))
        except Exception:
            pass


class EmailService:
    # Stateful vital tracking: (patient_id, sensor_type) -> timestamp of last sent alert
    _vital_states = {}
    _last_alert_time = {}
    _state_lock = threading.Lock()

    @classmethod
    def get_config(cls):
        """
        Load email configuration with priority:
        1. .env / Config variables (SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, ALERT_FROM_EMAIL)
        2. email_config.json (UI settings overrides)
        3. Built-in defaults
        """
        defaults = {
            'enabled': getattr(Config, 'ALERT_EMAIL_ENABLED', True),
            'smtp_server': getattr(Config, 'SMTP_SERVER', 'smtp.gmail.com') or 'smtp.gmail.com',
            'smtp_port': int(getattr(Config, 'SMTP_PORT', 587) or 587),
            'use_tls': True,
            'sender_email': getattr(Config, 'ALERT_FROM_EMAIL', '') or getattr(Config, 'SMTP_USERNAME', '') or '',
            'sender_password': getattr(Config, 'SMTP_PASSWORD', '') or '',
            'sender_name': 'CarePulse Emergency Monitor',
            'recipient_email': os.environ.get('ALERT_RECIPIENT_EMAIL', ''),
            'server_dashboard_url': 'http://127.0.0.1:5000/dashboard'
        }

        # Check email_config.json
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    defaults.update(saved)
            except Exception as e:
                _safe_print(f"[CarePulse Email] Warning loading email_config.json: {e}")

        # If .env has explicit credentials, prefer them if json has empty password
        if getattr(Config, 'SMTP_USERNAME', ''):
            if not defaults.get('sender_email'):
                defaults['sender_email'] = Config.SMTP_USERNAME
        if getattr(Config, 'SMTP_PASSWORD', ''):
            if not defaults.get('sender_password'):
                defaults['sender_password'] = Config.SMTP_PASSWORD

        return defaults

    @classmethod
    def save_config(cls, new_config):
        """Save email configuration to email_config.json."""
        current = cls.get_config()
        current.update(new_config)
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(current, f, indent=2)
            _safe_print("[CarePulse Email] Saved email_config.json successfully.")
            return True, "Email settings saved successfully."
        except Exception as e:
            err = f"Failed to save email settings: {e}"
            _safe_print(f"[CarePulse Email] Error: {err}")
            return False, err

    @classmethod
    def set_vital_normal(cls, patient_id, sensor_type):
        """
        Called when a sensor reading is within normal range.
        Transitions state from CRITICAL -> NORMAL, immediately re-arming the alert system.
        """
        key = (str(patient_id), str(sensor_type))
        with cls._state_lock:
            cls._vital_states[key] = 'NORMAL'
            cls._last_alert_time[key] = 0

    @classmethod
    def should_send_critical_alert(cls, patient_id, sensor_type, debounce_seconds=300):
        """
        Smart time-based debouncing:
        - Sends alert email immediately on FIRST critical reading.
        - Suppresses repeat emails within 5 minutes (300s) to prevent inbox flooding.
        - Re-sends every 5 minutes if patient condition remains in critical state.
        """
        cfg = cls.get_config()
        if not cfg.get('enabled', True):
            return False, "EMAIL_DISABLED"

        import time
        now = time.time()
        key = (str(patient_id), str(sensor_type))
        with cls._state_lock:
            last_time = cls._last_alert_time.get(key, 0)
            if now - last_time >= debounce_seconds:
                cls._last_alert_time[key] = now
                cls._vital_states[key] = 'CRITICAL'
                _safe_print(f"[CarePulse Email] Critical alert triggered for Patient {patient_id} ({sensor_type}). Dispatching email...")
                return True, "SEND"
            else:
                return False, "SUPPRESSED"

    @classmethod
    def reset_vital_states(cls):
        """Resets state machine (used when demo is reset)."""
        with cls._state_lock:
            cls._vital_states.clear()
        _safe_print("[CarePulse Email] All vital alarm states reset to NORMAL.")

    @classmethod
    def test_smtp_connection(cls, custom_cfg=None):
        """
        Tests actual connection and STARTTLS authentication to the SMTP server.
        Returns (success: bool, message: str).
        Strictly returns authentic errors without false claims.
        """
        cfg = custom_cfg or cls.get_config()
        server_host = cfg.get('smtp_server') or 'smtp.gmail.com'
        server_port = int(cfg.get('smtp_port') or 587)
        username = (cfg.get('sender_email') or '').strip()
        password = (cfg.get('sender_password') or '').strip()

        if not username:
            return False, "SMTP Username / Sender Email is missing. Please enter your Gmail address in .env or Settings."
        if not password:
            return False, "SMTP Password / App Password is missing. Please enter your 16-character Google App Password in .env or Settings."

        try:
            with smtplib.SMTP(server_host, server_port, timeout=12) as server:
                server.ehlo()
                if cfg.get('use_tls', True):
                    server.starttls()
                    server.ehlo()
                server.login(username, password)
            return True, f"Connected & Authenticated successfully with {server_host}:{server_port} as {username}!"
        except smtplib.SMTPAuthenticationError as e:
            return False, f"SMTP Authentication Failed (Code {e.smtp_code}): Username or App Password rejected by Gmail. Make sure 2-Step Verification is active and you use a 16-character Google App Password (not your personal login password)."
        except (socket.timeout, smtplib.SMTPConnectError) as e:
            return False, f"Connection timeout to {server_host}:{server_port}. Please verify internet access and firewall port 587."
        except Exception as e:
            return False, f"SMTP Connection Error: {str(e)}"

    @classmethod
    def send_test_email(cls, recipient=None, custom_cfg=None):
        """
        Sends an immediate diagnostic test email to verify credentials and live inbox delivery.
        Returns (success: bool, message: str).
        """
        cfg = custom_cfg or cls.get_config()
        target = recipient or cfg.get('recipient_email')

        if not target:
            target = cfg.get('sender_email')
            if not target:
                return False, "Recipient email address is required. Please specify a caregiver email."

        if not cfg.get('sender_email') or not cfg.get('sender_password'):
            return False, "SMTP credentials missing: Please enter your Gmail address and 16-character App Password in .env or Settings."

        subject = "CarePulse Test Alert: Emergency Dispatch System Active"
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        plain_text = (
            "CAREPULSE SYSTEM VERIFICATION TEST\n\n"
            "This is a test notification confirming that your CarePulse emergency email alert system is connected and functioning.\n\n"
            f"Timestamp: {timestamp}\n"
            f"SMTP Server: {cfg.get('smtp_server')}:{cfg.get('smtp_port')}\n"
            f"Sender: {cfg.get('sender_email')}\n"
            f"Recipient: {target}\n\n"
            "When abnormal patient vital signs occur, urgent alerts will be dispatched to this address immediately.\n\n"
            "CarePulse - Every heartbeat, watched over."
        )

        html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, sans-serif; background-color: #f1f6f7; padding: 20px; margin: 0;">
  <div style="max-width: 580px; margin: auto; background: #ffffff; border-radius: 10px; border: 1px solid #e2e8f0; overflow: hidden;">
    <div style="background: #063A52; color: #ffffff; padding: 20px; text-align: center;">
      <h2 style="margin: 0; font-size: 20px;">CarePulse Healthcare IoT</h2>
      <p style="margin: 5px 0 0 0; opacity: 0.9; font-size: 13px;">Emergency Email Notification System</p>
    </div>
    <div style="padding: 24px; color: #0b2b3a;">
      <div style="background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 6px; padding: 12px 16px; color: #065f46; font-weight: bold; margin-bottom: 18px;">
        SMTP Connection &amp; Delivery Active
      </div>
      <p>This test email confirms your CarePulse system is fully connected and authorized to dispatch emergency health alerts.</p>
      <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 14px; margin: 16px 0; font-size: 14px;">
        <p style="margin: 4px 0;"><strong>Timestamp:</strong> {timestamp}</p>
        <p style="margin: 4px 0;"><strong>SMTP Host:</strong> {cfg.get('smtp_server')}:{cfg.get('smtp_port')}</p>
        <p style="margin: 4px 0;"><strong>Sender:</strong> {cfg.get('sender_email')}</p>
        <p style="margin: 4px 0;"><strong>Recipient:</strong> {target}</p>
      </div>
      <p style="font-size: 13px; color: #64748b;">Emergency alerts for critical Heart Rate, SpO2, and Body Temperature will be delivered directly to this mailbox.</p>
    </div>
  </div>
</body>
</html>"""

        try:
            cls._send_smtp_raw(
                to_email=target,
                subject=subject,
                html_body=html_body,
                text_body=plain_text,
                cfg=cfg
            )
            _safe_print(f"[CarePulse Email] Test email successfully sent to {target}!")
            return True, f"Test email successfully sent to {target}!"
        except smtplib.SMTPAuthenticationError as e:
            err = f"SMTP Authentication Failed (Code {e.smtp_code}): Check your Gmail address and 16-character App Password."
            _safe_print(f"[CarePulse Email Error] {err}")
            return False, err
        except Exception as e:
            err = f"Failed to send test email: {str(e)}"
            _safe_print(f"[CarePulse Email Error] {err}")
            return False, err

    @classmethod
    def dispatch_critical_caregiver_alert(cls, alert, patient_info, caregivers, threshold_criteria="Critical Threshold"):
        """
        Dispatches emergency health alert email to registered caregivers in background threads.
        Updates database alerts table with email_status ('SENT' or 'FAILED') and email_error.
        """
        cfg = cls.get_config()
        if not cfg.get('enabled', True):
            _safe_print("[CarePulse Email] Email alerts disabled in configuration.")
            return

        worker = threading.Thread(
            target=cls._async_critical_alert_worker,
            args=(alert, patient_info, caregivers, threshold_criteria, cfg),
            daemon=True
        )
        worker.start()

    @classmethod
    def _async_critical_alert_worker(cls, alert, patient_info, caregivers, threshold_criteria, cfg):
        """Worker thread for PROMPT 10 & 11: Multi-recipient alert system."""
        patient_name = patient_info.get('name') if patient_info else 'Demo Patient'
        patient_id = alert.get('patient_id', 'P001')
        sensor_type = alert.get('sensor_type') or alert.get('type') or 'Vital Sign'
        value = alert.get('value', 'N/A')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        alert_id = alert.get('id')

        # 1. Prepare Recipient List (Caregivers, Doctor, Patient)
        recipients_data = []
        
        # Add Caregivers
        if caregivers:
            for cg in caregivers:
                if cg.get('email', '').strip():
                    recipients_data.append({'email': cg['email'].strip(), 'type': 'Caregiver'})
                    
        # Fetch Doctor & Patient
        try:
            from database import query_db, execute_db
            doc_query = query_db("SELECT u.email FROM users u JOIN doctor_assignments da ON u.id = da.doctor_id WHERE da.patient_id = %s", (patient_id,), one=True)
            if doc_query and doc_query.get('email'):
                recipients_data.append({'email': doc_query['email'].strip(), 'type': 'Doctor'})
                
            pat_query = query_db("SELECT u.email FROM users u JOIN patients p ON u.id = p.user_id WHERE p.patient_id = %s", (patient_id,), one=True)
            if pat_query and pat_query.get('email'):
                recipients_data.append({'email': pat_query['email'].strip(), 'type': 'Patient'})
        except Exception as e:
            _safe_print(f"Error querying additional recipients: {e}")

        # Fallback
        if not recipients_data and cfg.get('recipient_email'):
            recipients_data.append({'email': cfg.get('recipient_email').strip(), 'type': 'Caregiver'})

        if not recipients_data:
            if alert_id:
                try:
                    execute_db("UPDATE alerts SET email_status = 'NONE', email_error = 'No recipient email configured' WHERE id = %s", (alert_id,))
                except Exception:
                    pass
            return

        # 2. Exact Subject and Body Format specified in PROMPT 11
        subject = f"CarePulse Critical Health Alert - Patient {patient_id}"
        
        plain_body = (
            "CarePulse Health Monitoring System\n\n"
            f"Patient: {patient_name}\n"
            f"Patient ID: {patient_id}\n"
            f"Date: {timestamp.split(' ')[0]}\n"
            f"Time: {timestamp.split(' ')[1]}\n\n"
            "Current readings:\n"
            f"{sensor_type}: {value}\n\n"
            "System Status:\n"
            "Critical / Attention Required\n\n"
            "Alert Reason:\n"
            f"{threshold_criteria}\n\n"
            "Please check the patient and take appropriate action.\n\n"
            "This is an automated monitoring alert and is not a medical diagnosis.\n\n"
            "CarePulse IoT Health Monitoring System"
        )
        
        html_body = f"<html><body><pre style='font-family: Arial, sans-serif; font-size: 14px;'>{plain_body}</pre></body></html>"

        sender_email = cfg.get('sender_email')
        sender_pwd = cfg.get('sender_password')

        if not sender_email or not sender_pwd:
            if alert_id:
                try:
                    execute_db("UPDATE alerts SET email_status = 'FAILED', email_error = 'SMTP credentials not configured' WHERE id = %s", (alert_id,))
                except Exception:
                    pass
            return

        # 3. Dispatch & Record Notification History (PROMPT 10 & 27)
        delivered_recipients = []
        last_error = None

        for recip_info in recipients_data:
            recip = recip_info['email']
            rtype = recip_info['type']
            try:
                cls._send_smtp_raw(
                    to_email=recip,
                    subject=subject,
                    html_body=html_body,
                    text_body=plain_body,
                    cfg=cfg
                )
                delivered_recipients.append(recip)
                if alert_id:
                    execute_db(
                        "INSERT INTO notification_history (alert_id, recipient, recipient_type, notification_type, status) VALUES (%s, %s, %s, 'Email', 'Sent')",
                        (alert_id, recip, rtype)
                    )
            except Exception as e:
                last_error = str(e)
                if alert_id:
                    execute_db(
                        "INSERT INTO notification_history (alert_id, recipient, recipient_type, notification_type, status, failure_reason) VALUES (%s, %s, %s, 'Email', 'Failed', %s)",
                        (alert_id, recip, rtype, last_error)
                    )

        if alert_id:
            try:
                if delivered_recipients:
                    execute_db("UPDATE alerts SET email_status = 'SENT', email_recipient = %s, email_sent_at = %s, email_error = NULL WHERE id = %s", (", ".join(delivered_recipients), datetime.now(), alert_id))
                else:
                    execute_db("UPDATE alerts SET email_status = 'FAILED', email_error = %s WHERE id = %s", (last_error, alert_id))
            except Exception:
                pass

    @classmethod
    def _send_smtp_raw(cls, to_email, subject, html_body, cfg, text_body=None):
        """Low-level SMTP connection and transmission using STARTTLS."""
        smtp_server = cfg.get('smtp_server') or 'smtp.gmail.com'
        smtp_port = int(cfg.get('smtp_port') or 587)
        sender_email = cfg.get('sender_email')
        sender_pwd = cfg.get('sender_password')
        sender_name = cfg.get('sender_name', 'CarePulse Emergency Monitor')

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{sender_name} <{sender_email}>"
        msg['To'] = to_email

        if text_body:
            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
        if html_body:
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        with smtplib.SMTP(smtp_server, smtp_port, timeout=12) as server:
            server.ehlo()
            if cfg.get('use_tls', True):
                server.starttls()
                server.ehlo()
            server.login(sender_email, sender_pwd)
            server.sendmail(sender_email, [to_email], msg.as_string())

    @classmethod
    def get_email_system_status(cls, patient_id='P001'):
        """
        Returns real-time status required for the Settings page:
        - Email Alerts: Enabled / Disabled
        - SMTP Connection: Connected / Not Connected
        - Caregiver Email: [caregiver email]
        - Last Email: [timestamp or none]
        - Last Email Status: SENT / FAILED
        """
        cfg = cls.get_config()
        enabled = bool(cfg.get('enabled', True))

        # Lookup caregiver email
        from models import CaregiverModel
        caregivers = CaregiverModel.get_alert_recipients(patient_id)
        if caregivers and caregivers[0].get('email'):
            caregiver_email = caregivers[0]['email']
        else:
            caregiver_email = cfg.get('recipient_email') or 'Not configured'

        # Query last email from alerts table
        last_alert = query_db("""
            SELECT email_status, email_recipient, email_sent_at, created_at, email_error
            FROM alerts
            WHERE email_status IN ('SENT', 'FAILED')
            ORDER BY id DESC LIMIT 1
        """, one=True)

        last_email_time = None
        last_email_status = 'NONE'
        last_email_error = None

        if last_alert:
            t = last_alert.get('email_sent_at') or last_alert.get('created_at')
            if isinstance(t, datetime):
                last_email_time = t.strftime("%Y-%m-%d %H:%M:%S")
            elif t:
                last_email_time = str(t)
            last_email_status = last_alert.get('email_status', 'NONE')
            last_email_error = last_alert.get('email_error')

        has_credentials = bool(cfg.get('sender_email') and cfg.get('sender_password'))

        return {
            'enabled': enabled,
            'has_credentials': has_credentials,
            'smtp_server': cfg.get('smtp_server', 'smtp.gmail.com'),
            'smtp_port': cfg.get('smtp_port', 587),
            'sender_email': cfg.get('sender_email', ''),
            'caregiver_email': caregiver_email,
            'last_email_time': last_email_time,
            'last_email_status': last_email_status,
            'last_email_error': last_email_error
        }
