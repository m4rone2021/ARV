# database.py
import sqlite3
import os
from contextlib import contextmanager

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventory.db")

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
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

        # 3. Transactions Table
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
                remarks TEXT
            )
        """)

        # Insert Default Admin User if missing
        cursor.execute("SELECT id FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO users (username, password, role)
                VALUES ('admin', 'admin123', 'Admin')
            """)

        conn.commit()

def login_user(username, password):
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
