import sqlite3
import os
import io
import hashlib
import tempfile
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime

# Streamlit import for secrets retrieval in Cloud
try:
    import streamlit as st
except ImportError:
    st = None

# -----------------------------------------------------------------------------
# EXPORTED MODULE API
# -----------------------------------------------------------------------------
__all__ = [
    "init_db",
    "login_user",
    "backup_db_to_gdrive",
    "upload_file_to_gdrive",
    "get_drive_service",
    "create_test_file_in_gdrive",
    "get_db",
    "register_item",
    "add_stock_transaction",
    "resolve_discrepancy",
    "DB_FILE",
    "UPLOAD_DIR",
]

# -----------------------------------------------------------------------------
# DYNAMIC ENVIRONMENT & PATH CONFIGURATION
# -----------------------------------------------------------------------------
LOCAL_WIN_DIR = Path(r"D:\Inventory System Files")

if LOCAL_WIN_DIR.exists() or os.name == "nt":
    DATA_DIR = LOCAL_WIN_DIR
else:
    # Fallback directory for Streamlit Cloud / Linux
    DATA_DIR = Path("./data")

DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_FILE = DATA_DIR / "inventory.db"

# Local uploads directory configuration
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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
def clean_private_key(key_str: str) -> str:
    """Sanitizes raw private key strings into valid multi-line PEM format."""
    if not key_str:
        return key_str

    key_str = key_str.strip('\'" ')
    if "\\n" in key_str:
        key_str = key_str.replace("\\n", "\n")

    if "-----BEGIN PRIVATE KEY-----" in key_str and not key_str.startswith("-----BEGIN PRIVATE KEY-----"):
        key_str = "-----BEGIN PRIVATE KEY-----" + key_str.split("-----BEGIN PRIVATE KEY-----")[-1]

    return key_str.strip()


def get_drive_service():
    """
    Authenticates and builds Google Drive API service.
    Supports Streamlit Secrets or local token/credentials.
    """
    SCOPES = ['https://www.googleapis.com/auth/drive']

    # 1. STREAMLIT CLOUD: GCP Service Account
    if st and hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict:
                creds_dict["private_key"] = clean_private_key(creds_dict["private_key"])

            creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=SCOPES
            )
            return build('drive', 'v3', credentials=creds), "Service Account"
        except Exception as e:
            print(f"[Drive Warning] Streamlit Service Account Auth failed: {e}")

    # 2. STREAMLIT CLOUD: User OAuth Refresh Token
    if st and hasattr(st, "secrets") and "gdrive_token" in st.secrets:
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            token_info = dict(st.secrets["gdrive_token"])
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            return build('drive', 'v3', credentials=creds), "OAuth Token"
        except Exception as e:
            print(f"[Drive Warning] Streamlit OAuth Token Auth failed: {e}")

    # 3. LOCAL ENVIRONMENT: token.json / credentials.json
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = None
        if os.path.exists('token.json'):
            try:
                creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            except Exception as e:
                print(f"[Drive Warning] Invalid token.json deleted: {e}")
                os.remove('token.json')

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif os.path.exists('credentials.json'):
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
            else:
                print("[Drive Warning] No valid credentials found.")
                return None, None

        return build('drive', 'v3', credentials=creds), "Local Credentials"
    except Exception as e:
        print(f"[Drive Auth Error] {e}")
        return None, None


def upload_file_to_gdrive(file_bytes: bytes, file_name: str, mime_type: str = "application/octet-stream") -> str | None:
    """Uploads raw file bytes to Google Drive and returns the shareable webViewLink."""
    service, auth_type = get_drive_service()
    if not service:
        print("[Drive Upload Error] Could not initialize Drive service.")
        return None

    try:
        from googleapiclient.http import MediaIoBaseUpload

        folder_id = None
        if st and hasattr(st, "secrets"):
            folder_id = st.secrets.get("google_drive", {}).get("folder_id", None)

        file_metadata = {'name': file_name}
        if folder_id:
            file_metadata['parents'] = [folder_id]

        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes),
            mimetype=mime_type,
            resumable=True
        )

        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()

        web_link = file.get('webViewLink')
        print(f"[Drive Upload Success] File '{file_name}' uploaded via {auth_type}. Link: {web_link}")
        return web_link

    except Exception as e:
        print(f"[Drive Upload Error] Failed to upload '{file_name}': {e}")
        return None


def create_test_file_in_gdrive():
    """Creates a sample test document in Google Drive for verification."""
    file_content = (
        "PROJECT ALPHA SPECIFICATIONS\n"
        "----------------------------\n"
        "Project Alpha budget is $50,000 using vendor ACME Corp.\n"
        "Key Deliverable: Automated inventory sync module."
    )
    return upload_file_to_gdrive(file_content.encode('utf-8'), 'Project_Alpha_Specs.txt', 'text/plain')


def backup_db_to_gdrive():
    """Uploads/Backs up the local inventory.db to Google Drive using a safe online dump."""
    if not DB_FILE.exists():
        print(f"[Backup Warning] Database file not found at {DB_FILE}")
        return None

    temp_backup_path = None
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"inventory_backup_{timestamp}.db"
        temp_dir = tempfile.gettempdir()
        temp_backup_path = Path(temp_dir) / backup_filename

        src_conn = sqlite3.connect(DB_FILE)
        bck_conn = sqlite3.connect(temp_backup_path)
        with bck_conn:
            src_conn.backup(bck_conn)
        bck_conn.close()
        src_conn.close()

        with open(temp_backup_path, 'rb') as f:
            file_bytes = f.read()

        return upload_file_to_gdrive(file_bytes, backup_filename, 'application/x-sqlite3')

    except Exception as e:
        print(f"[Backup Error] Failed to backup: {e}")
        return None
    finally:
        if temp_backup_path and temp_backup_path.exists():
            temp_backup_path.unlink()


# -----------------------------------------------------------------------------
# TRANSACTION & SYNCHRONIZATION HANDLERS
# -----------------------------------------------------------------------------
def register_item(item_name: str, category: str, unit: str, initial_stock: float = 0.0, min_threshold: float = 10.0, remarks: str = ""):
    """Registers a new item in the master catalog and syncs the updated DB to Google Drive."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO master_items (item_name, category, unit, current_stock, min_threshold, remarks)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (item_name, category, unit, initial_stock, min_threshold, remarks))
        conn.commit()

    print(f"[DB Update] Item '{item_name}' added.")
    backup_db_to_gdrive()


def add_stock_transaction(trans_type: str, item_name: str, quantity: float, unit: str, handled_by: str, notes: str = ""):
    """
    Executes stock transactions (IN, OUT, ADJUSTMENT), updates stock levels atomically,
    logs the transaction record, and triggers an automated Drive sync.
    """
    trans_type = trans_type.upper()
    if trans_type not in ["IN", "OUT", "ADJUSTMENT"]:
        raise ValueError("Transaction type must be 'IN', 'OUT', or 'ADJUSTMENT'")

    with get_db() as conn:
        cursor = conn.cursor()

        # Check item existence
        cursor.execute("SELECT current_stock FROM master_items WHERE item_name = ?", (item_name,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Item '{item_name}' does not exist in master catalog.")

        current_stock = row["current_stock"]

        # Calculate new stock level
        if trans_type == "IN":
            new_stock = current_stock + quantity
        elif trans_type == "OUT":
            if current_stock < quantity:
                raise ValueError(f"Insufficient stock for '{item_name}'. Current: {current_stock}, Requested: {quantity}")
            new_stock = current_stock - quantity
        elif trans_type == "ADJUSTMENT":
            new_stock = quantity

        # Update master stock
        cursor.execute("UPDATE master_items SET current_stock = ? WHERE item_name = ?", (new_stock, item_name))

        # Log transaction record
        cursor.execute("""
            INSERT INTO transactions (type, item_name, quantity, unit, handled_by, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (trans_type, item_name, quantity, unit, handled_by, notes))

        conn.commit()

    print(f"[DB Update] Transaction '{trans_type}' recorded for {item_name}. New stock: {new_stock}")
    backup_db_to_gdrive()


def resolve_discrepancy(discrepancy_id: int, resolved_by: str, resolution_notes: str, approve_adjustment: bool = True):
    """Resolves pending stock discrepancies, adjusts real inventory if approved, and triggers sync."""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM discrepancies WHERE id = ?", (discrepancy_id,))
        disc = cursor.fetchone()

        if not disc:
            raise ValueError(f"Discrepancy record {discrepancy_id} not found.")

        status = "RESOLVED_ADJUSTED" if approve_adjustment else "REJECTED"

        cursor.execute("""
            UPDATE discrepancies 
            SET status = ?, resolved_by = ?, resolved_timestamp = CURRENT_TIMESTAMP, resolution_notes = ?
            WHERE id = ?
        """, (status, resolved_by, resolution_notes, discrepancy_id))

        if approve_adjustment:
            cursor.execute("UPDATE master_items SET current_stock = ? WHERE item_name = ?", (disc["physical_count"], disc["item_name"]))
            cursor.execute("""
                INSERT INTO transactions (type, item_name, quantity, unit, handled_by, notes)
                VALUES ('ADJUSTMENT', ?, ?, ?, ?, ?)
            """, (disc["item_name"], disc["physical_count"], disc["unit"], resolved_by, f"Discrepancy Audit #{discrepancy_id}: {resolution_notes}"))

        conn.commit()

    print(f"[DB Update] Discrepancy #{discrepancy_id} marked as {status}.")
    backup_db_to_gdrive()


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

        admin_hashed = hash_password('admin123')
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
