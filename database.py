import sqlite3
import os
import hashlib
from contextlib import contextmanager

DB_FILE = "inventory.db"

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

def init_db():
    """Initializes database tables and default admin credentials."""
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
                min_threshold REAL DEFAULT 10.0,
                remarks TEXT
            )
        """)

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
    print("Database initialized successfully.")
