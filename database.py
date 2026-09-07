import sqlite3
import hashlib
import os
import tempfile
import json
from datetime import datetime
import streamlit as st

# Google Drive API Dependencies
try:
    from google.oauth2.credentials import Credentials
    from google.oauth2 import service_account
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False

DB_NAME = "inventory.db"
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# ==========================================
# 1. DATABASE INITIALIZATION & MIGRATIONS
# ==========================================

def get_connection():
    """Returns a connection to the SQLite database with row factory set."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str) -> str:
    """Hashes a plaintext password using SHA-256."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def init_db():
    """Initializes tables, executes structural migrations, and seeds the default admin user."""
    conn = get_connection()
    cursor = conn.cursor()

    # Create Tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'User'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS master_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            unit TEXT DEFAULT 'pcs',
            current_stock REAL DEFAULT 0.0,
            reserved_stock REAL DEFAULT 0.0,
            min_threshold REAL DEFAULT 0.0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            type TEXT CHECK(type IN ('IN', 'OUT', 'ADJUSTMENT')) NOT NULL,
            quantity REAL NOT NULL,
            remarks TEXT,
            user_id INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES master_items(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS discrepancies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            system_qty REAL NOT NULL,
            physical_qty REAL NOT NULL,
            difference REAL NOT NULL,
            status TEXT CHECK(status IN ('PENDING', 'RESOLVED_ADJUSTED', 'REJECTED')) DEFAULT 'PENDING',
            reported_by INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES master_items(id),
            FOREIGN KEY (reported_by) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            destination TEXT NOT NULL,
            driver TEXT,
            priority TEXT DEFAULT 'Normal',
            status TEXT CHECK(status IN ('Pending', 'In Transit', 'Completed', 'Cancelled')) DEFAULT 'Pending',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES master_items(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            assigned_to TEXT,
            due_date TEXT,
            status TEXT CHECK(status IN ('Open', 'Closed')) DEFAULT 'Open',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # Delivery Table Migration Check (handles legacy 'qty' column transition)
    cursor.execute("PRAGMA table_info(deliveries)")
    columns = [col['name'] for col in cursor.fetchall()]
    if 'qty' not in columns:
        try:
            cursor.execute("ALTER TABLE deliveries ADD COLUMN qty REAL DEFAULT 0.0")
            conn.commit()
        except sqlite3.OperationalError:
            pass

    # Default Admin Seed
    admin_pass_hash = hash_password("admin123")
    cursor.execute("""
        INSERT INTO users (username, password, role) 
        VALUES ('admin', ?, 'Admin')
        ON CONFLICT(username) DO UPDATE SET password=excluded.password
    """, (admin_pass_hash,))

    conn.commit()
    conn.close()

# ==========================================
# 2. GOOGLE DRIVE INTEGRATION
# ==========================================

def get_gdrive_service():
    """Multi-tiered auth strategy checking Secrets, OAuth tokens, and local credential files."""
    if not GDRIVE_AVAILABLE:
        return None

    creds = None
    
    # Tier 1: Streamlit Service Account Secrets
    if "gcp_service_account" in st.secrets:
        try:
            service_account_info = dict(st.secrets["gcp_service_account"])
            creds = service_account.Credentials.from_service_account_info(
                service_account_info, scopes=SCOPES
            )
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            st.error(f"Service Account Auth failed: {e}")

    # Tier 2: Streamlit OAuth Token Secrets
    if "gdrive_token" in st.secrets:
        try:
            token_info = dict(st.secrets["gdrive_token"])
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
        except Exception as e:
            st.error(f"Secrets OAuth token parse failed: {e}")

    # Tier 3: Local OAuth Files
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds:
            if os.path.exists('token.json'):
                creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            elif os.path.exists('credentials.json'):
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())

    if creds and creds.valid:
        return build('drive', 'v3', credentials=creds)
    
    return None

def backup_db_to_gdrive():
    """Creates a hot backup via sqlite3 online backup API and syncs to Google Drive."""
    service = get_gdrive_service()
    if not service:
        return False, "Google Drive integration unavailable or unauthenticated."

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"inventory_backup_{timestamp}.db"
        
        temp_dir = tempfile.gettempdir()
        temp_backup_path = os.path.join(temp_dir, backup_filename)

        # SQLite Online Backup API for thread safety
        src_conn = get_connection()
        dst_conn = sqlite3.connect(temp_backup_path)
        with dst_conn:
            src_conn.backup(dst_conn)
        dst_conn.close()
        src_conn.close()

        file_metadata = {
            'name': backup_filename,
            'mimeType': 'application/x-sqlite3'
        }
        
        media = MediaFileUpload(temp_backup_path, mimetype='application/x-sqlite3', resumable=True)
        uploaded_file = service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id'
        ).execute()

        if os.path.exists(temp_backup_path):
            os.remove(temp_backup_path)

        return True, uploaded_file.get('id')

    except Exception as e:
        return False, str(e)

# ==========================================
# 3. CORE BUSINESS LOGIC FUNCTIONS
# ==========================================

def login_user(username, password):
    """Authenticates credentials against SHA-256 hashed password."""
    conn = get_connection()
    cursor = conn.cursor()
    hashed = hash_password(password)
    cursor.execute("SELECT id, username, role FROM users WHERE username = ? AND password = ?", (username, hashed))
    user = cursor.fetchone()
    conn.close()
    return user

def register_item(sku, name, category, unit, min_threshold):
    """Registers a new master item and triggers auto-sync."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO master_items (sku, name, category, unit, min_threshold)
            VALUES (?, ?, ?, ?, ?)
        """, (sku, name, category, unit, min_threshold))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        success = False
    finally:
        conn.close()

    if success:
        backup_db_to_gdrive()
    return success

def add_stock_transaction(item_id, trans_type, quantity, remarks, user_id):
    """Processes atomic stock alterations and appends to immutable ledger."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO transactions (item_id, type, quantity, remarks, user_id)
            VALUES (?, ?, ?, ?, ?)
        """, (item_id, trans_type, quantity, remarks, user_id))

        if trans_type == 'IN':
            cursor.execute("UPDATE master_items SET current_stock = current_stock + ? WHERE id = ?", (quantity, item_id))
        elif trans_type == 'OUT':
            cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE id = ?", (quantity, item_id))
        elif trans_type == 'ADJUSTMENT':
            cursor.execute("UPDATE master_items SET current_stock = ? WHERE id = ?", (quantity, item_id))

        conn.commit()
        success = True
    except Exception:
        conn.rollback()
        success = False
    finally:
        conn.close()

    if success:
        backup_db_to_gdrive()
    return success

def update_dispatch_status(delivery_id, new_status):
    """Manages delivery status lifecycle and recalculates stock reservations."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT item_id, qty, status FROM deliveries WHERE id = ?", (delivery_id,))
        delivery = cursor.fetchone()

        if not delivery:
            conn.close()
            return False

        item_id = delivery['item_id']
        qty = delivery['qty']
        old_status = delivery['status']

        if old_status != new_status:
            # Transitions leaving 'Pending' status release reservations
            if old_status == 'Pending':
                cursor.execute("UPDATE master_items SET reserved_stock = MAX(0, reserved_stock - ?) WHERE id = ?", (qty, item_id))

            # Transitions entering 'Pending' reserve stock
            if new_status == 'Pending':
                cursor.execute("UPDATE master_items SET reserved_stock = reserved_stock + ? WHERE id = ?", (qty, item_id))

            # Completing a delivery consumes stock
            if new_status == 'Completed' and old_status != 'Completed':
                cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE id = ?", (qty, item_id))

            cursor.execute("UPDATE deliveries SET status = ? WHERE id = ?", (new_status, delivery_id))
            conn.commit()

        success = True
    except Exception:
        conn.rollback()
        success = False
    finally:
        conn.close()

    if success:
        backup_db_to_gdrive()
    return success

def resolve_discrepancy(discrepancy_id, action, user_id):
    """Resolves inventory audit discrepancies with option to override physical counts."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT item_id, physical_qty, status FROM discrepancies WHERE id = ?", (discrepancy_id,))
        disc = cursor.fetchone()

        if not disc or disc['status'] != 'PENDING':
            conn.close()
            return False

        item_id = disc['item_id']
        physical_qty = disc['physical_qty']

        if action == 'APPROVE':
            cursor.execute("UPDATE master_items SET current_stock = ? WHERE id = ?", (physical_qty, item_id))
            cursor.execute("UPDATE discrepancies SET status = 'RESOLVED_ADJUSTED' WHERE id = ?", (discrepancy_id,))
            cursor.execute("""
                INSERT INTO transactions (item_id, type, quantity, remarks, user_id)
                VALUES (?, 'ADJUSTMENT', ?, 'Resolved via Audit Approval', ?)
            """, (item_id, physical_qty, user_id))
        elif action == 'REJECT':
            cursor.execute("UPDATE discrepancies SET status = 'REJECTED' WHERE id = ?", (discrepancy_id,))

        conn.commit()
        success = True
    except Exception:
        conn.rollback()
        success = False
    finally:
        conn.close()

    if success:
        backup_db_to_gdrive()
    return success

# Ensures initialization if imported directly
if __name__ == "__main__":
    init_db()
