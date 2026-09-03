# database.py
import sqlite3
import os
import bcrypt
from contextlib import contextmanager

DB_FILE = "inventory_system.db"
UPLOAD_DIR = "uploaded_proofs"

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

@contextmanager
def get_db():
    """Context manager for thread-safe SQLite database connections with timeout."""
    conn = sqlite3.connect(DB_FILE, timeout=20.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, stored_password: str) -> bool:
    if not stored_password:
        return False
    if stored_password.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(plain_password.encode('utf-8'), stored_password.encode('utf-8'))
        except (ValueError, TypeError):
            return False
    return plain_password == stored_password

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS master_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                unit TEXT NOT NULL,
                current_stock REAL DEFAULT 0,
                min_threshold REAL DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                item_name TEXT NOT NULL,
                type TEXT NOT NULL,
                quantity REAL NOT NULL,
                user_name TEXT NOT NULL,
                user_role TEXT NOT NULL,
                driver_details TEXT,
                issued_to TEXT,
                project_name TEXT,
                purpose TEXT,
                remarks TEXT,
                photo_path TEXT,
                edit_status TEXT DEFAULT 'NORMAL'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL,
                title TEXT NOT NULL,
                due_date TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING',
                timestamp TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL,
                title TEXT NOT NULL,
                event_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                location_details TEXT,
                notes TEXT,
                timestamp TEXT NOT NULL
            )
        """)
        
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            hashed_admin = hash_password("admin123")
            hashed_super = hash_password("super123")
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ('admin', hashed_admin, 'Head Office'))
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ('supervisor', hashed_super, 'Materials Supervisor'))
        
        conn.commit()

def login_user(username, password):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, password, role FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        
        if user and verify_password(password, user["password"]):
            if not user["password"].startswith(("$2a$", "$2b$", "$2y$")):
                new_hash = hash_password(password)
                cursor.execute("UPDATE users SET password = ? WHERE username = ?", (new_hash, username))
                conn.commit()
            return {"username": user["username"], "role": user["role"]}
            
    return None
