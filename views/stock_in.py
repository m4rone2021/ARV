import sqlite3
import os
import hashlib
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime

# Google Drive API Dependencies
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False

# 1. Define folder path on local Disk D
DATA_DIR = Path(r"D:\Inventory System Files")

# 2. Create directory automatically if it doesn't exist
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 3. Directories & Configurations
DB_FILE = DATA_DIR / "inventory.db"
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Google Drive Credentials & Configs
SERVICE_ACCOUNT_FILE = DATA_DIR / "service_account.json"
GDRIVE_FOLDER_ID = "1zLtErDbaDuGFMdAfBndU4MgCUC1lDg8J"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


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
# GOOGLE DRIVE INTEGRATION HELPERS
# -----------------------------------------------------------------------------
def get_gdrive_service():
    """Authenticates and returns the Google Drive API service client."""
    if not GDRIVE_AVAILABLE:
        print("⚠️ Google API client libraries not installed. Run: pip install google-api-python-client google-auth")
        return None

    if not SERVICE_ACCOUNT_FILE.exists():
        print(f"⚠️ Service account key not found at: {SERVICE_ACCOUNT_FILE}")
        return None

    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        print(f"❌ Failed to authenticate with Google Drive API: {e}")
        return None


def backup_db_to_gdrive(folder_id: str = None) -> bool:
    """Uploads/backs up the current SQLite database file to Google Drive."""
    service = get_gdrive_service()
    if not service:
        return False

    target_folder = folder_id or GDRIVE_FOLDER_ID
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"inventory_backup_{timestamp}.db"

    file_metadata = {"name": backup_filename}
    if target_folder:
        file_metadata["parents"] = [target_folder]

    try:
        media = MediaFileUpload(str(DB_FILE), mimetype="application/x-sqlite3", resumable=True)
        uploaded_file = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )
        print(f"✅ Database backup uploaded to Drive (File ID: {uploaded_file.get('id')})")
        return True
    except Exception as e:
        print(f"❌ Google Drive upload failed: {e}")
        return False


def upload_file_to_gdrive(file_path: Path, folder_id: str = None) -> str:
    """Uploads arbitrary site attachments (invoices/DRs) to Google Drive and returns a viewable web link."""
    service = get_gdrive_service()
    if not service or not file_path.exists():
        return None

    target_folder = folder_id or GDRIVE_FOLDER_ID
    file_metadata = {"name": file_path.name}
    if target_folder:
        file_metadata["parents"] = [target_folder]

    try:
        media = MediaFileUpload(str(file_path), resumable=True)
        uploaded = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id, webViewLink")
            .execute()
        )
        return uploaded.get("webViewLink")
    except Exception as e:
        print(f"❌ File upload to Drive failed: {e}")
        return None


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
        admin_hashed = hash_password("admin123")

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

        # Schema Migration check
        cursor.execute("PRAGMA table_info(master_items)")
        columns = [column[1] for column in cursor.fetchall()]
        if "reserved_stock" not in columns:
            cursor.execute(
                "ALTER TABLE master_items ADD COLUMN reserved_stock REAL DEFAULT 0.0"
            )

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
            (username, hashed),
        )
        return cursor.fetchone()


if __name__ == "__main__":
    init_db()
    print(f"Database initialized successfully at: {DB_FILE}")
