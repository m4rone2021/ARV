# database.py
import sqlite3
import os
from contextlib import contextmanager

# Absolute path to the database file
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventory.db")

# Absolute path for uploaded file attachments (Delivery Receipts, Invoices, etc.)
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@contextmanager
def get_db():
    """Provides a transactional database connection context."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Initializes all required database tables and default admin credentials."""
    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'User'
            )
        """)

        # 2. Master Items Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS master_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                unit TEXT NOT NULL,
                current_stock REAL DEFAULT 0.0,
                min_threshold REAL DEFAULT 10.0,
                remarks TEXT
            )
        """)

        # 3. Transactions Table (Stock IN / OUT Ledger)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                type TEXT NOT NULL,
                item_name TEXT NOT NULL,
                category TEXT,
                unit TEXT,
                quantity REAL NOT NULL,
                user_name TEXT NOT NULL,
                remarks TEXT,
                attachment TEXT,
                status TEXT DEFAULT 'ACTIVE'
            )
        """)

        # 4. Schedules & Deliveries Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scheduled_date TEXT NOT NULL,
                item_name TEXT NOT NULL,
                expected_quantity REAL NOT NULL,
                unit TEXT NOT NULL,
                supplier TEXT,
                status TEXT DEFAULT 'PENDING',
                remarks TEXT
            )
        """)

        # 5. Reminders & Tasks Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                due_date TEXT NOT NULL,
                task TEXT NOT NULL,
                assigned_to TEXT,
                status TEXT DEFAULT 'OPEN'
            )
        """)

        # 6. System Audit Logs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                user_name TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT
            )
        """)

        # Seed Default Admin Account if missing (Username: admin | Password: admin123)
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO users (username, password, role)
                VALUES ('admin', 'admin123', 'Admin')
            """)

        conn.commit()

def login_user(username, password):
    """Authenticates a user against the database."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT username, role FROM users 
            WHERE LOWER(username) = LOWER(?) AND password = ?
        """, (username, password))
        row = cursor.fetchone()
        if row:
            return {"username": row["username"], "role": row["role"]}
        return None
