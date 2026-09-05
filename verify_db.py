# verify_db.py
import sys

def run_verification():
    print("🔍 Starting Database & Backup Verification...\n")

    # 1. Test Module Import & Exports
    try:
        import database
        print("✅ Successfully imported 'database.py'")
        
        required_funcs = ["init_db", "login_user", "backup_db_to_gdrive"]
        for func in required_funcs:
            if hasattr(database, func):
                print(f"  └─ Function '{func}' is present.")
            else:
                print(f"  ❌ Missing expected function '{func}'!")
    except Exception as e:
        print(f"❌ Failed to import database.py: {e}")
        sys.exit(1)

    # 2. Test DB Initialization & Schema
    try:
        database.init_db()
        print("\n✅ Database initialized successfully.")
        
        import sqlite3
        conn = sqlite3.connect(database.DB_PATH)
        cursor = conn.cursor()
        
        # Verify tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"  └─ Existing Tables: {tables}")
        
        # Verify admin user
        cursor.execute("SELECT username, role FROM users WHERE username='admin';")
        admin = cursor.fetchone()
        if admin:
            print(f"  └─ Default Admin verified: username='{admin[0]}', role='{admin[1]}'")
        else:
            print("  ❌ Default Admin record missing!")
            
        conn.close()
    except Exception as e:
        print(f"❌ Database initialization check failed: {e}")

    print("\n🎉 Verification Complete!")

if __name__ == "__main__":
    run_verification()
