# database.py
import os
import sqlite3
import bcrypt

# 1. Define upload directory for stored receipt photos / attachments
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_db():
    """Returns a SQLite connection configured with dict-like row access and WAL mode."""
    conn = sqlite3.connect("inventory.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable Write-Ahead Logging for improved concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def hash_password(password: str) -> str:
    """Hashes a plain text password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def check_password(password: str, stored_password: str) -> bool:
    """
    Verifies a plain text password against a stored bcrypt hash.
    Safely handles legacy/unhashed plain-text strings to avoid ValueError crashes.
    """
    if not stored_password:
        return False
    
    # Check if the stored string is a valid bcrypt hash
    if stored_password.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8'))
        except ValueError:
            return False
            
    # Fallback comparison if legacy password in DB is stored as plain text
    return password == stored_password

def init_db():
    """Initializes tables, migrates missing columns, and seeds initial accounts."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Master Items Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS master_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                unit TEXT NOT NULL,
                current_stock REAL DEFAULT 0,
                min_threshold REAL DEFAULT 10
            )
        """)

        # 2. Transactions Ledger Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                item_name TEXT NOT NULL,
                type TEXT NOT NULL,
                quantity REAL NOT NULL,
                user_name TEXT NOT NULL,
                user_role TEXT,
                driver_details TEXT,
                issued_to TEXT,
                project_name TEXT,
                purpose TEXT,
                remarks TEXT,
                photo_path TEXT,
                edit_status TEXT DEFAULT 'ACTIVE'
            )
        """)

        # 3. Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
        """)

        # 4. Reminders & Tasks Table
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

        # 5. Schedules & Deliveries Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL,
                title TEXT NOT NULL,
                event_date TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                location_details TEXT,
                notes TEXT,
                timestamp TEXT NOT NULL
            )
        """)

        # --- SAFE DYNAMIC COLUMN MIGRATIONS ---
        # Ensures existing inventory.db files acquire new columns without crashing
        cursor.execute("PRAGMA table_info(transactions)")
        existing_cols = [row[1] for row in cursor.fetchall()]

        required_cols = {
            "driver_details": "TEXT",
            "issued_to": "TEXT",
            "project_name": "TEXT",
            "purpose": "TEXT",
            "remarks": "TEXT",
            "photo_path": "TEXT",
            "edit_status": "TEXT DEFAULT 'ACTIVE'"
        }

        for col_name, col_type in required_cols.items():
            if col_name not in existing_cols:
                cursor.execute(f"ALTER TABLE transactions ADD COLUMN {col_name} {col_type}")

        # --- SEED DEFAULT USER ACCOUNTS ---
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            default_admin_pass = hash_password("admin123")
            default_super_pass = hash_password("super123")
            
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                ("admin", default_admin_pass, "Head Office")
            )
            cursor.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                ("supervisor", default_super_pass, "Materials Supervisor")
            )

        conn.commit()

def login_user(username: str, password: str):
    """
    Validates user credentials against stored passwords in the DB.
    Automatically upgrades plain-text passwords to bcrypt hashes upon successful login.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, password, role FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        
        if user and check_password(password, user["password"]):
            # Auto-upgrade plain text passwords to bcrypt hashes in DB if needed
            if not user["password"].startswith(("$2a$", "$2b$", "$2y$")):
                new_hash = hash_password(password)
                cursor.execute("UPDATE users SET password = ? WHERE id = ?", (new_hash, user["id"]))
                conn.commit()

            return {"username": user["username"], "role": user["role"]}
            
        return None
