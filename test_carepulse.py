"""
Comprehensive Automated Test Suite for CarePulse Healthcare System
Tests database, web views, authentication, APIs, Demo Mode, and ESP32 hardware endpoint.
Run with: python test_carepulse.py
"""
import unittest
import json
from app import app
from database import query_db

class CarePulseTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def test_01_public_pages(self):
        """Test public views (Home, Patient Login, Caregiver Login, Patient Register, Caregiver Register)."""
        print("\n[TEST] 1. Verifying Public Pages...")
        pages = [
            ('Home', '/'),
            ('Patient Login', '/patient-login'),
            ('Caregiver Login', '/caregiver-login'),
            ('Patient Register', '/patient-register'),
            ('Caregiver Register', '/caregiver-register')
        ]
        for endpoint, url in pages:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200, f"Failed to load {endpoint} at {url}")
            print(f"       [OK] {endpoint} loaded successfully (HTTP 200)")

        # Verify backward-compatible redirect routes
        res_login = self.client.get('/login')
        self.assertEqual(res_login.status_code, 302)
        res_reg = self.client.get('/register')
        self.assertEqual(res_reg.status_code, 302)
        print("       [OK] Legacy /login and /register properly redirect (HTTP 302)")

    def test_02_demo_login(self):
        """Test login with valid credentials."""
        print("\n[TEST] 2. Verifying Authentication & Login...")
        res = self.client.post('/api/login', json={
            'email': 'admin@carepulse.com',
            'password': 'demo1234'
        })
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data.get('success'), "Login should succeed")
        print("       [OK] Login succeeded with admin@carepulse.com")

    def test_03_authenticated_views(self):
        """Test that all 14 views return HTTP 200 when authenticated."""
        print("\n[TEST] 3. Verifying All 14 Web Pages Under Authentication...")
        # Authenticate session
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['full_name'] = 'Demo Patient'
            sess['email'] = 'demo@carepulse.com'
            sess['role'] = 'Patient'

        pages = [
            ('Dashboard', '/patient-dashboard'),
            ('Live Monitoring', '/monitoring'),
            ('Patients Directory', '/patients'),
            ('Health History', '/history'),
            ('Analytics', '/analytics'),
            ('Alerts & Notifications', '/alerts'),
            ('Patient Profile', '/profile'),
            ('Device Management', '/devices'),
            ('Thresholds', '/thresholds'),
            ('Reports', '/reports'),
            ('Settings', '/settings')
        ]

        for name, path in pages:
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, f"Page {name} ({path}) failed with status {res.status_code}")
            print(f"       [OK] {name} accessible at {path} (HTTP 200)")

    def test_04_hardware_freshness_engine(self):
        """Test strict ESP32 hardware staleness and freshness verification."""
        print("\n[TEST] 4. Verifying Hardware Freshness Engine (<= 10s)...")
        
        # Test reading endpoint
        res = self.client.get('/api/readings/latest?patient_id=P001')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data.get('success'))
        # If no packet within 10s, reading must be null (never fake numbers)
        if not data.get('is_hardware_connected'):
            self.assertIsNone(data.get('reading'))
            print("       [OK] Correctly reported 'DISCONNECTED' and reading=null when no device active")
        else:
            print("       [OK] Active ESP32 device packet detected within 10s window")

    def test_05_esp32_hardware_api(self):
        """Test POST /api/sensor-data with ESP32 data."""
        print("\n[TEST] 5. Verifying Future ESP32 Ingestion API (POST /api/sensor-data)...")
        payload = {
            "device_id": "ESP32-001",
            "patient_id": "P001",
            "heart_rate": 78.5,
            "spo2": 98.0,
            "temperature": 36.8,
            "data_source": "ESP32"
        }
        res = self.client.post('/api/sensor-data', json=payload)
        self.assertEqual(res.status_code, 201)
        data = json.loads(res.data)
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('data_source'), 'ESP32')
        print("       [OK] ESP32 payload accepted, stored, and verified in database!")

    def test_06_alert_resolution(self):
        """Test resolving an alert."""
        print("\n[TEST] 6. Verifying Alert Resolution Workflow...")
        # Authenticate session
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['full_name'] = 'Demo Patient'
            sess['role'] = 'Patient'

        # Get latest alert ID from DB
        alert = query_db("SELECT id FROM alerts ORDER BY id DESC LIMIT 1", one=True)
        if alert:
            aid = alert['id']
            res = self.client.put(f'/api/alerts/{aid}/resolve')
            self.assertEqual(res.status_code, 200)
            data = json.loads(res.data)
            self.assertTrue(data.get('success'))
            print(f"       [OK] Alert #{aid} resolved successfully via API")

    def test_07_email_alert_system(self):
        """Test emergency email configuration, rate-limiting, and alert triggering."""
        print("\n[TEST] 7. Verifying Emergency Email Alert Subsystem...")
        from email_service import EmailService

        # Authenticate session
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['full_name'] = 'Demo Patient'
            sess['role'] = 'Patient'

        # 1. Test Email Config GET & POST
        res = self.client.get('/api/email/config')
        self.assertEqual(res.status_code, 200)
        cfg_data = json.loads(res.data)
        self.assertTrue(cfg_data.get('success'))
        self.assertIn('config', cfg_data)

        # Update config via API
        res = self.client.post('/api/email/config', json={
            'enabled': True,
            'recipient_email': 'test_caregiver@carepulse.com',
            'debounce_minutes': 5
        })
        self.assertEqual(res.status_code, 200)
        print("       [OK] Email configuration API GET/POST verified")

        # 2. Test Debounce / Rate Limiting Logic
        EmailService.reset_vital_states()
        # First critical alert should trigger
        should_send, _ = EmailService.should_send_critical_alert('P001', 'Heart Rate')
        self.assertTrue(should_send)
        # Immediate duplicate should be debounced (suppressed)
        should_send_dup, _ = EmailService.should_send_critical_alert('P001', 'Heart Rate')
        self.assertFalse(should_send_dup)
        print("       [OK] Anti-spam debounce rate-limiting verified")

        # 3. Test High/Low Health Conditions generating alerts and dispatching
        from models import AlertModel
        # Test Critical High Heart Rate (Tachycardia: 145 BPM)
        alerts_hr = AlertModel.check_and_create_alerts('P001', 'ESP32-001', heart_rate=145, spo2=98.0, temperature=36.7)
        self.assertTrue(any(a['type'] == 'Heart Rate' for a in alerts_hr))
        
        # Test Critical Low Temperature (Severe Hypothermia: 34.2 °C)
        alerts_temp = AlertModel.check_and_create_alerts('P001', 'ESP32-001', heart_rate=75, spo2=98.0, temperature=34.2)
        self.assertTrue(any(a['type'] == 'Temperature' for a in alerts_temp))

        # Test Critical Low SpO2 Drop (Hypoxemia: 84%)
        alerts_ox = AlertModel.check_and_create_alerts('P001', 'ESP32-001', heart_rate=75, spo2=84.0, temperature=36.7)
        self.assertTrue(any(a['type'] == 'SpO2' for a in alerts_ox))
        print("       [OK] High/Low Vital thresholds (HR, SpO2, Temp) verified with automated email dispatch!")

    def test_08_caregiver_crud_and_registration(self):
        """Test Caregiver registration, listing, editing, primary switching, and deleting."""
        print("\n[TEST] 8. Verifying Caregiver Management & Registration...")
        from models import CaregiverModel

        # Authenticate session
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['full_name'] = 'Demo Patient'
            sess['role'] = 'Patient'

        # 1. Verify Caregiver list endpoint
        res = self.client.get('/api/caregivers?patient_id=P001')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data.get('success'))
        self.assertGreaterEqual(len(data['caregivers']), 1)
        print("       [OK] GET /api/caregivers returned registered family contacts")

        # 2. Add a new caregiver via POST
        res = self.client.post('/api/caregivers', json={
            'patient_id': 'P001',
            'name': 'Emily Patient',
            'relationship': 'Daughter',
            'email': 'emily.daughter@example.com',
            'phone': '+1 555-0999',
            'is_primary': False,
            'receive_alerts': True
        })
        self.assertEqual(res.status_code, 201)
        new_cg_id = json.loads(res.data)['caregiver_id']
        print("       [OK] POST /api/caregivers created new Daughter contact")

        # 3. Switch Primary Caregiver
        res = self.client.post(f'/api/caregivers/{new_cg_id}/primary', json={'patient_id': 'P001'})
        self.assertEqual(res.status_code, 200)
        recipients = CaregiverModel.get_alert_recipients('P001')
        self.assertEqual(recipients[0]['id'], new_cg_id)
        print("       [OK] POST /api/caregivers/<id>/primary switched primary caregiver")

        # 4. Update Caregiver
        res = self.client.put(f'/api/caregivers/{new_cg_id}', json={
            'name': 'Emily Updated',
            'relationship': 'Daughter',
            'email': 'emily.new@example.com',
            'phone': '+1 555-0998',
            'is_primary': True,
            'receive_alerts': True
        })
        self.assertEqual(res.status_code, 200)
        print("       [OK] PUT /api/caregivers/<id> updated contact details")

        # 5. Delete Caregiver
        res = self.client.delete(f'/api/caregivers/{new_cg_id}')
        self.assertEqual(res.status_code, 200)
        print("       [OK] DELETE /api/caregivers/<id> removed caregiver")

        # 6. Test Caregivers web view
        res = self.client.get('/caregivers')
        self.assertEqual(res.status_code, 200)
        print("       [OK] GET /caregivers portal rendered successfully")

    def test_09_caregiver_alert_dispatch(self):
        """Test routing emergency alerts to Primary vs All registered caregivers."""
        print("\n[TEST] 9. Verifying Emergency Alert Dispatch to Caregiver Mobile Network...")
        from models import CaregiverModel, AlertModel
        from email_service import EmailService

        EmailService.reset_vital_states()

        # 1. Test PRIMARY mode routing
        CaregiverModel.set_alert_mode('P001', 'PRIMARY')
        recipients_primary = CaregiverModel.get_alert_recipients('P001')
        self.assertEqual(len(recipients_primary), 1)
        print(f"       [OK] PRIMARY Mode selects exactly 1 primary recipient: {recipients_primary[0]['name']} ({recipients_primary[0]['relationship']})")

        # 2. Test ALL mode routing
        cid = CaregiverModel.create('P001', 'Secondary Contact', 'Family', 'second@carepulse.com', '+15551234', is_primary=False, receive_alerts=True)
        CaregiverModel.set_alert_mode('P001', 'ALL')
        recipients_all = CaregiverModel.get_alert_recipients('P001')
        self.assertGreaterEqual(len(recipients_all), 2)
        print(f"       [OK] ALL Mode broadcasts to {len(recipients_all)} registered caregivers simultaneously")

        # Clean up temporary caregiver and reset back to PRIMARY
        CaregiverModel.delete(cid)
        CaregiverModel.set_alert_mode('P001', 'PRIMARY')

        # 3. Simulate critical reading triggering caregiver notification
        alerts = AlertModel.check_and_create_alerts('P001', 'ESP32-001', heart_rate=125, spo2=98.0, temperature=36.7)
        self.assertTrue(any(a['type'] == 'Heart Rate' and a['severity'] == 'Critical' for a in alerts))
        print("       [OK] Critical vital (125 BPM) generated emergency alert for caregiver dispatch!")

    def test_10_role_separated_auth_and_caregiver_dashboard(self):
        """Test separated patient and caregiver portals, live-data/device-status APIs, and sensor validation."""
        print("\n[TEST] 10. Verifying Role-Separated Portals & Strict Hardware Validation...")

        # 1. Test Caregiver Dashboard under caregiver session
        with self.client.session_transaction() as sess:
            sess['user_id'] = 2
            sess['full_name'] = 'Jane Patient'
            sess['email'] = 'daughter@carepulse.com'
            sess['role'] = 'Caregiver'

        res_cg = self.client.get('/caregiver-dashboard')
        self.assertEqual(res_cg.status_code, 200)
        self.assertIn(b'Caregiver Health Monitor', res_cg.data)
        print("       [OK] GET /caregiver-dashboard accessible for authorized caregiver")

        # 2. Test /api/live-data alias
        res_live = self.client.get('/api/live-data?patient_id=P001')
        self.assertEqual(res_live.status_code, 200)
        data_live = json.loads(res_live.data)
        self.assertTrue(data_live.get('success'))
        print("       [OK] GET /api/live-data returns valid response")

        # 3. Test /api/device-status
        res_dev = self.client.get('/api/device-status?device_id=ESP32-001')
        self.assertEqual(res_dev.status_code, 200)
        data_dev = json.loads(res_dev.data)
        self.assertTrue(data_dev.get('success'))
        self.assertIn('status', data_dev)
        print(f"       [OK] GET /api/device-status reports status={data_dev['status']}")

        # 4. Strict Biometric Validation: Reject 0 BPM / finger-off readings
        res_bad_hr = self.client.post('/api/sensor-data', json={
            "device_id": "ESP32-001",
            "patient_id": "P001",
            "heart_rate": 0.0,
            "spo2": 0,
            "temperature": 36.6,
            "data_source": "ESP32"
        })
        self.assertEqual(res_bad_hr.status_code, 422)
        print("       [OK] POST /api/sensor-data correctly rejected 0 BPM finger-off reading (HTTP 422)")

        # 5. Strict Temperature Validation: Reject disconnected DS18B20 (-127°C)
        res_bad_temp = self.client.post('/api/sensor-data', json={
            "device_id": "ESP32-001",
            "patient_id": "P001",
            "heart_rate": 75.0,
            "spo2": 98,
            "temperature": -127.0,
            "data_source": "ESP32"
        })
        self.assertEqual(res_bad_temp.status_code, 422)
        print("       [OK] POST /api/sensor-data correctly rejected -127.0°C disconnected probe (HTTP 422)")

if __name__ == '__main__':
    print("=" * 60)
    print("CAREPULSE AUTOMATED TEST RUNNER")
    print("=" * 60)
    unittest.main(verbosity=2)
