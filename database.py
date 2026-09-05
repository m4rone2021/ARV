import sqlite3
import os
import io
import hashlib
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime

# -----------------------------------------------------------------------------
# DYNAMIC ENVIRONMENT & PATH CONFIGURATION
# -----------------------------------------------------------------------------
# Detect environment: Use D: locally if available, otherwise default to local ./data folder
LOCAL_WIN_DIR = Path(r"D:\Inventory System Files")

if LOCAL_WIN_DIR.exists() or os.name == "nt":
    DATA_DIR = LOCAL_WIN_DIR
else:
    # Fallback directory for Streamlit Cloud / Linux
    DATA_DIR = Path("./data")

DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = DATA_DIR / "inventory.db"


def hash_password(password: str) -> str:
    """Hashes passwords using SHA-256 for secure database storage."""
    return hashlib.sha256(password.encode()).hexdigest()


@contextmanager
def get_db():
    """Context manager for managing SQLite database connections cleanly."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# GOOGLE DRIVE INTEGRATION & TESTING
# -----------------------------------------------------------------------------
def get_drive_service():
    """
    Authenticates and builds Google Drive API service.
    Supports local credentials.json/token.json or Streamlit Secrets in Cloud.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        SCOPES = ['https://www.googleapis.com/auth/drive']
        creds = None

        # Check for saved local token
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif os.path.exists('credentials.json'):
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
            else:
                print("[Drive Warning] Neither credentials.json nor token.json found.")
                return None

        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"[Drive Auth Error] {e}")
        return None


def create_test_file_in_gdrive():
    """Creates a sample test document in Google Drive for verification."""
    service = get_drive_service()
    if not service:
        print("[Test File Error] Could not initialize Drive service.")
        return None

    try:
        from googleapiclient.http import MediaIoBaseUpload

        file_metadata = {
            'name': 'Project_Alpha_Specs.txt',
            'mimeType': 'text/plain',
            'description': 'Integration Test File'
        }

        file_content = (
            "PROJECT ALPHA SPECIFICATIONS\n"
            "----------------------------\n"
            "Project Alpha budget is $50,000 using vendor ACME Corp.\n"
            "Key Deliverable: Automated inventory sync module.\n"
            "Target Date: Q4 2026."
        )

        media = MediaIoBaseUpload(
            io.BytesIO(file_content.encode('utf-8')),
            mimetype='text/plain',
            resumable=True
        )

        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()

        print(f"[Test Upload Success] File ID: {file.get('id')}")
        return file.get('id')
    except Exception as e:
        print(f"[Test Upload Error] {e}")
        return None


def backup_db_to_gdrive():
    """Uploads/Backs up the local inventory.db to Google Drive."""
    if not DB_FILE.exists():
        print(f"[Backup Warning] Database file not found at {DB_FILE}")
        return False

    service = get_drive_service()
    if not service:
        print("[Backup Error] Drive service unavailable.")
        return False

    try:
        from googleapiclient.http import MediaFileUpload

        backup_filename = f"inventory_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        file_metadata = {'name': backup_filename}
        
        media = MediaFileUpload(str(DB_FILE), mimetype='application/x-sqlite3', resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()

        print(f"[Backup Success] Uploaded {backup_filename} (ID: {file.get('id')})")
        return True
    except Exception as e:
        print(f"[Backup Error] Failed to backup: {e}")
        return False


# -----------------------------------------------------------------------------
# DATABASE INITIALIZATION & SCHEMA
# -----------------------------------------------------------------------------
def init_db():
    """Initializes database tables, default admin credentials, and handles schema updates."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
        """)

        # Default admin password hashed
        admin_hashed = hash_password('admin123')

        # Update or create default admin
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        existing_admin = cursor.fetchone()

        if existing_admin:
            cursor.execute("""
                UPDATE users 
                SET password = ?, role = 'Admin' 
                WHERE username = 'admin'
            """, (admin_hashed,))
        else:
            cursor.execute("""
                INSERT INTO users (username, password, role) 
                VALUES ('admin', ?, 'Admin')
            """, (admin_hashed,))

        # Master Items Catalog
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS master_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                unit TEXT NOT NULL,
                current_stock REAL DEFAULT 0.0,
                reserved_stock REAL DEFAULT 0.0,
                min_threshold REAL DEFAULT 10.0,
                remarks TEXT
            )
        """)

        # Schema Migration: Ensure reserved_stock column exists in master_items for existing DBs
        cursor.execute("PRAGMA table_info(master_items)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'reserved_stock' not in columns:
            cursor.execute("ALTER TABLE master_items ADD COLUMN reserved_stock REAL DEFAULT 0.0")

        # Transactions Log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                type TEXT NOT NULL,
                item_name TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit TEXT NOT NULL,
                handled_by TEXT NOT NULL,
                notes TEXT
            )
        """)

        # Physical Inventory Discrepancies
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS discrepancies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                item_name TEXT NOT NULL,
                system_stock REAL NOT NULL,
                physical_count REAL NOT NULL,
                variance REAL NOT NULL,
                unit TEXT NOT NULL,
                submitted_by TEXT NOT NULL,
                submission_notes TEXT,
                status TEXT DEFAULT 'PENDING',
                resolved_by TEXT,
                resolved_timestamp DATETIME,
                resolution_notes TEXT
            )
        """)

        # Deliveries Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                expected_quantity REAL NOT NULL,
                unit TEXT NOT NULL,
                supplier TEXT,
                expected_date DATE NOT NULL,
                status TEXT DEFAULT 'PENDING',
                notes TEXT
            )
        """)

        # Tasks Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_description TEXT NOT NULL,
                assigned_to TEXT NOT NULL,
                due_date DATE,
                status TEXT DEFAULT 'OPEN',
                created_by TEXT NOT NULL
            )
        """)

        conn.commit()


def login_user(username, password):
    """Authenticates a user against the database using hashed passwords."""
    hashed = hash_password(password)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT username, role FROM users WHERE username = ? AND password = ?",
            (username, hashed)
        )
        return cursor.fetchone()


if __name__ == "__main__":
    init_db()
    print(f"Database initialized successfully at: {DB_FILE}")
