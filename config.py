import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

class Config:
    """Base configuration for CarePulse application."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'carepulse_super_secret_jwt_and_session_key_2026')
    
    # MySQL Database credentials
    MYSQL_HOST = os.environ.get('MYSQL_HOST', '127.0.0.1')
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'carepulse')
    
    # SQLite Fallback path (used automatically if MySQL server is unreachable)
    SQLITE_DB = os.environ.get('SQLITE_DB', os.path.join(os.path.dirname(__file__), 'carepulse.db'))
    

    # SMTP Gmail Alert Configuration
    SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
    ALERT_FROM_EMAIL = os.environ.get('ALERT_FROM_EMAIL', os.environ.get('SMTP_USERNAME', ''))
    ALERT_EMAIL_ENABLED = os.environ.get('ALERT_EMAIL_ENABLED', 'true').lower() in ('true', '1', 'yes')
