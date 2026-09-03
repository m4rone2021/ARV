# database.py
import os
import sqlite3
import hashlib
import streamlit as st
from contextlib import contextmanager

DB_FILE = "inventory.db"  # Standard database file for ARV Inventory System
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")

# Ensure upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)

@contextmanager
def get_db():
    """Context manager for handling SQLite database connections safely."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def hash_password(password: str) -> str:
    """Hashes passwords using SHA-256 for secure storage and comparison."""
    return hashlib.sha256(password.encode()).hexdigest()

def login_user(username: str, password: str):
    """
    Authenticates a user against the users table in the SQLite database.
    Returns a dict with user details if successful, or None if invalid.
    """
    hashed_pwd = hash_password(password)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, role FROM users WHERE username = ? AND password = ?",
            (username.strip(), hashed_pwd)
        )
        user = cursor.fetchone()
        
        if user:
            return {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"]
            }
        return None

def init_db():
    """Initializes database tables, creates default admin user, and runs auto-migrations."""
    with get_db() as conn:
        cursor = conn.cursor()

        # 1. CREATE USERS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'User'
            )
        """)

        # 2. CREATE MASTER ITEMS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS master_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                unit TEXT NOT NULL,
                current_stock REAL DEFAULT 0.0,
                min_threshold REAL DEFAULT 0.0,
                remarks TEXT
            )
        """)

        # 3. CREATE TRANSACTIONS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                type TEXT NOT NULL,
                item_name TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit TEXT NOT NULL,
                handled_by TEXT,
                notes TEXT
            )
        """)

        # 4. CREATE REMINDERS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                due_date TEXT,
                task TEXT,
                assigned_to TEXT,
                status TEXT DEFAULT 'OPEN'
            )
        """)

        # 5. CREATE SCHEDULES TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scheduled_date TEXT,
                item_name TEXT,
                expected_quantity REAL,
                unit TEXT,
                supplier TEXT,
                status TEXT DEFAULT 'PENDING',
                remarks TEXT
            )
        """)

        # 6. SEED DEFAULT ADMIN USER IF EMPTY
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            default_admin_pass = hash_password("admin123")
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                ("admin", default_admin_pass, "Admin")
            )

        # 7. SCHEMA AUTO-MIGRATIONS
        # Ensure remarks column exists on master_items
        cursor.execute("PRAGMA table_info(master_items);")
        mi_cols = [col["name"] for col in cursor.fetchall()]
        if "remarks" not in mi_cols:
            cursor.execute("ALTER TABLE master_items ADD COLUMN remarks TEXT;")

        # Ensure task, due_date, assigned_to, status exist on reminders
        cursor.execute("PRAGMA table_info(reminders);")
        rem_cols = [col["name"] for col in cursor.fetchall()]

        if "task" not in rem_cols:
            if "description" in rem_cols:
                cursor.execute("ALTER TABLE reminders RENAME COLUMN description TO task;")
            elif "reminder" in rem_cols:
                cursor.execute("ALTER TABLE reminders RENAME COLUMN reminder TO task;")
            else:
                cursor.execute("ALTER TABLE reminders ADD COLUMN task TEXT;")

        if "due_date" not in rem_cols:
            cursor.execute("ALTER TABLE reminders ADD COLUMN due_date TEXT;")

        if "assigned_to" not in rem_cols:
            cursor.execute("ALTER TABLE reminders ADD COLUMN assigned_to TEXT;")

        if "status" not in rem_cols:
            cursor.execute("ALTER TABLE reminders ADD COLUMN status TEXT DEFAULT 'OPEN';")

        conn.commit()

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
        status TEXT DEFAULT 'PENDING', -- PENDING, APPROVED, REJECTED
        resolved_by TEXT,
        resolved_timestamp DATETIME,
        resolution_notes TEXT
    )
""")

if __name__ == "__main__":
    init_db()
    print("Database auto-migration complete.")
