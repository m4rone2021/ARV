# database.py
import sqlite3
import streamlit as st
from contextlib import contextmanager

DB_FILE = "database.db"  # Change to your SQLite filename if different (e.g. 'inventory.db')


@contextmanager
def get_db():
    """Context manager for handling SQLite database connections safely."""
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initializes tables and automatically migrates/updates missing or mismatched columns."""
    with get_db() as conn:
        cursor = conn.cursor()

        # -------------------------------------------------------------
        # 1. CREATE TABLES IF THEY DO NOT EXIST
        # -------------------------------------------------------------
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                due_date TEXT,
                task TEXT,
                assigned_to TEXT,
                status TEXT DEFAULT 'OPEN'
            )
        """
        )

        # -------------------------------------------------------------
        # 2. SCHEMA AUTO-MIGRATION FOR 'reminders'
        # -------------------------------------------------------------
        cursor.execute("PRAGMA table_info(reminders);")
        columns_info = cursor.fetchall()
        existing_columns = [col["name"] for col in columns_info]

        # Standardize the task description column
        if "task" not in existing_columns:
            if "description" in existing_columns:
                cursor.execute(
                    "ALTER TABLE reminders RENAME COLUMN description TO task;"
                )
            elif "reminder" in existing_columns:
                cursor.execute(
                    "ALTER TABLE reminders RENAME COLUMN reminder TO task;"
                )
            else:
                cursor.execute("ALTER TABLE reminders ADD COLUMN task TEXT;")

        # Ensure due_date column exists
        if "due_date" not in existing_columns:
            cursor.execute("ALTER TABLE reminders ADD COLUMN due_date TEXT;")

        # Ensure assigned_to column exists
        if "assigned_to" not in existing_columns:
            cursor.execute("ALTER TABLE reminders ADD COLUMN assigned_to TEXT;")

        # Ensure status column exists
        if "status" not in existing_columns:
            cursor.execute(
                "ALTER TABLE reminders ADD COLUMN status TEXT DEFAULT 'OPEN';"
            )

        conn.commit()


if __name__ == "__main__":
    init_db()
    print("Database initialized and migrated successfully.")
