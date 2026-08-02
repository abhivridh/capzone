"""
CarePulse Database Setup Script
Run this script to initialize the MySQL database and seed initial demo data.
Usage: python setup_database.py
"""
import sys
from database import init_db, query_db, get_db_status

def main():
    print("=" * 60)
    print("CAREPULSE - Healthcare Monitoring System")
    print("Database Initializer & Health Check")
    print("=" * 60)
    
    print("\n[1/3] Connecting to database...")
    engine = init_db()
    print(f"      -> Active Database Engine: {engine}")
    
    print("\n[2/3] Verifying database tables and seed records...")
    users = query_db("SELECT COUNT(*) as count FROM users", one=True)
    patients = query_db("SELECT COUNT(*) as count FROM patients", one=True)
    devices = query_db("SELECT COUNT(*) as count FROM devices", one=True)
    readings = query_db("SELECT COUNT(*) as count FROM sensor_readings", one=True)
    alerts = query_db("SELECT COUNT(*) as count FROM alerts", one=True)
    thresholds = query_db("SELECT COUNT(*) as count FROM thresholds", one=True)
    
    print(f"      - Users count:           {users['count'] if users else 0}")
    print(f"      - Patients count:        {patients['count'] if patients else 0}")
    print(f"      - Devices count:         {devices['count'] if devices else 0}")
    print(f"      - Sensor readings count: {readings['count'] if readings else 0}")
    print(f"      - Alerts count:          {alerts['count'] if alerts else 0}")
    print(f"      - Thresholds count:      {thresholds['count'] if thresholds else 0}")
    
    print("\n[3/3] Demo accounts available:")
    print("      * Patient Demo:  demo@carepulse.com   / demo1234")
    print("      * Doctor Demo:   doctor@carepulse.com / demo1234")
    print("      * Admin Demo:    admin@carepulse.com  / demo1234")
    print("\n" + "=" * 60)
    print("Database setup complete! You can now start CarePulse with:")
    print("python app.py")
    print("=" * 60)

if __name__ == '__main__':
    main()
