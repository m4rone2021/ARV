# database.py
import sqlite3
import hashlib
import streamlit as st
from contextlib import contextmanager

DB_FILE = "database.db"

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

        # 2. CREATE REMINDERS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                due_date TEXT,
                task TEXT,
                assigned_to TEXT,
                status TEXT DEFAULT 'OPEN'
            )
        """)

        # 3. SEED DEFAULT ADMIN USER IF EMPTY
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            default_admin_pass = hash_password("admin123")
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                ("admin", default_admin_pass, "Admin")
            )

        # 4. SCHEMA AUTO-MIGRATION FOR 'reminders'
        cursor.execute("PRAGMA table_info(reminders);")
        columns_info = cursor.fetchall()
        existing_columns = [col["name"] for col in columns_info]

        if "task" not in existing_columns:
            if "description" in existing_columns:
                cursor.execute("ALTER TABLE reminders RENAME COLUMN description TO task;")
            elif "reminder" in existing_columns:
                cursor.execute("ALTER TABLE reminders RENAME COLUMN reminder TO task;")
            else:
                cursor.execute("ALTER TABLE reminders ADD COLUMN task TEXT;")

        if "due_date" not in existing_columns:
            cursor.execute("ALTER TABLE reminders ADD COLUMN due_date TEXT;")

        if "assigned_to" not in existing_columns:
            cursor.execute("ALTER TABLE reminders ADD COLUMN assigned_to TEXT;")

        if "status" not in existing_columns:
            cursor.execute("ALTER TABLE reminders ADD COLUMN status TEXT DEFAULT 'OPEN';")

        conn.commit()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
