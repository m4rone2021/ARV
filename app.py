import sys
import os
import io
import tempfile
from pathlib import Path
import streamlit as st

# Ensure root workspace directory is on sys.path for Cloud execution
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Core database imports
from database import (
    init_db,
    login_user,
    backup_db_to_gdrive,
    get_drive_service,
    create_test_file_in_gdrive,
    DB_FILE,
)

# Page Configuration
st.set_page_config(
    page_title="ARV Site Inventory System",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------------------------------------------------------
# GOOGLE DRIVE AUTOMATIC RESTORE ON STARTUP
# -----------------------------------------------------------------------------
def restore_latest_db_from_gdrive():
    """Downloads the most recent database backup from Google Drive if local DB is missing/empty."""
    if DB_FILE.exists() and DB_FILE.stat().st_size > 0:
        return  # Local database exists and is valid

    service, auth_type = get_drive_service()
    if not service:
        return

    try:
        folder_id = st.secrets.get("google_drive", {}).get("folder_id", None) if st and hasattr(st, "secrets") else None
        query = f"'{folder_id}' in parents and name contains 'inventory_backup_' and trashed = false" if folder_id else "name contains 'inventory_backup_' and trashed = false"

        results = service.files().list(
            q=query,
            orderBy="createdTime desc",
            pageSize=1,
            fields="files(id, name)"
        ).execute()

        files = results.get('files', [])
        if files:
            latest_file = files[0]
            file_id = latest_file['id']
            
            from googleapiclient.http import MediaIoBaseDownload
            request = service.files().get_media(fileId=file_id)
            
            with open(DB_FILE, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            print(f"[Drive Sync] Successfully restored {latest_file['name']} from Google Drive.")
    except Exception as e:
        print(f"[Drive Sync Error] Failed to restore database on startup: {e}")


# Restore remote DB first, then initialize schema
restore_latest_db_from_gdrive()
init_db()

# Initialize Session States
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "user_role" not in st.session_state:
    st.session_state.user_role = "User"

# Global Site Categories List
if "categories" not in st.session_state:
    st.session_state.categories = [
        "Fuel & Oils",
        "Construction Materials",
        "Steel / Rebar",
        "Nails & Fasteners",
        "Cutting & Grinding Consumables",
        "Welding Supplies & PPE",
        "General Site Supplies",
    ]


# -----------------------------------------------------------------------------
# LOGIN VIEW
# -----------------------------------------------------------------------------
def render_login():
    st.markdown(
        "<h1 style='text-align: center;'>🏗️ ARV Construction Site Inventory</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<h4 style='text-align: center; color: gray;'>Material Tracking & Warehouse Management</h4>",
        unsafe_allow_html=True,
    )
    st.write("---")

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.subheader("🔑 Sign In")
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input(
                "Password", type="password", placeholder="Enter your password"
            )
            submit = st.form_submit_button("Login", use_container_width=True)

            if submit:
                if not username.strip() or not password.strip():
                    st.error("⚠️ Please enter both Username and Password.")
                else:
                    user_data = login_user(username.strip(), password.strip())
                    if user_data:
                        st.session_state.logged_in = True
                        st.session_state.user_name = user_data["username"]
                        st.session_state.user_role = user_data["role"]

                        # Backup database to Google Drive upon Admin login
                        if user_data["role"] == "Admin":
                            try:
                                backup_db_to_gdrive()
                            except Exception as e:
                                st.warning(f"⚠️ Initial Admin backup warning: {e}")

                        st.toast(
                            f"Welcome back, {user_data['username']}!", icon="👋"
                        )
                        st.rerun()
                    else:
                        st.error("❌ Invalid Username or Password.")

        st.caption("Default Admin Credentials: **admin** / **admin123**")


# -----------------------------------------------------------------------------
# MAIN APPLICATION & NAVIGATION
# -----------------------------------------------------------------------------
def render_app():
    # Sidebar Header
    st.sidebar.markdown(f"### 👤 Logged in: **{st.session_state.user_name}**")
    st.sidebar.caption(f"Role: **{st.session_state.user_role}**")
    st.sidebar.divider()

    # NAVIGATION OPTIONS WITH ICONS
    menu_map = {
        "📊 Dashboard": "Dashboard",
        "📦 Manage Master Items": "Manage Master Items",
        "📥 Stock IN": "Stock IN",
        "📤 Stock OUT": "Stock OUT",
        "⚠️ Low Stock Alerts": "Low Stock Alerts",
        "🚚 Schedules & Deliveries": "Schedules & Deliveries",
        "📝 Reminders & Tasks": "Reminders & Tasks",
        "📜 Transaction Ledger": "Transaction Ledger",
    }

    # Add Admin-only view options
    if st.session_state.user_role == "Admin":
        menu_map["👥 User Management"] = "User Management"

    selected_label = st.sidebar.radio(
        "Main Menu", list(menu_map.keys()), index=0
    )
    choice = menu_map[selected_label]

    st.sidebar.divider()

    # Admin Utilities / Test Tools
    if st.session_state.user_role == "Admin":
        st.sidebar.subheader("🛠️ Admin Tools")
        
        # 1. Manual DB Backup Button
        if st.sidebar.button("💾 Backup Database to Drive", use_container_width=True):
            with st.spinner("Backing up SQLite DB to Google Drive..."):
                try:
                    file_id = backup_db_to_gdrive()
                    if file_id:
                        st.sidebar.success("✅ Backup upload complete!")
                except Exception as e:
                    st.sidebar.error(f"❌ Backup failed: {e}")

        # 2. Test Drive Upload Button
        if st.sidebar.button("🧪 Generate Test File in Drive", use_container_width=True):
            with st.spinner("Uploading test file to Google Drive..."):
                try:
                    file_id = create_test_file_in_gdrive()
                    if file_id:
                        st.sidebar.success(f"✅ Success! ID: {file_id[:8]}...")
                    else:
                        st.sidebar.error("❌ Failed to create file.")
                except Exception as e:
                    st.sidebar.error(f"❌ Error: {e}")
                    
        st.sidebar.divider()

    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.user_name = ""
        st.session_state.user_role = "User"
        st.rerun()

    # Lazy router import with error fallback
    try:
        if choice == "Dashboard":
            from views.dashboard import render_dashboard
            render_dashboard(st.session_state.user_name, st.session_state.user_role)
        elif choice == "Manage Master Items":
            from views.manage_items import render_manage_items
            render_manage_items(st.session_state.user_name, st.session_state.user_role)
        elif choice == "Stock IN":
            from views.stock_in import render_stock_in
            render_stock_in(st.session_state.user_name, st.session_state.user_role)
        elif choice == "Stock OUT":
            from views.stock_out import render_stock_out
            render_stock_out(st.session_state.user_name, st.session_state.user_role)
        elif choice == "Low Stock Alerts":
            from views.low_stock import render_low_stock
            render_low_stock(st.session_state.user_name, st.session_state.user_role)
        elif choice == "Schedules & Deliveries":
            from views.schedules import render_schedules
            render_schedules(st.session_state.user_name, st.session_state.user_role)
        elif choice == "Reminders & Tasks":
            from views.reminders import render_reminders
            render_reminders(st.session_state.user_name, st.session_state.user_role)
        elif choice == "Transaction Ledger":
            from views.audit_log import render_audit_log
            render_audit_log(st.session_state.user_name, st.session_state.user_role)
        elif choice == "User Management" and st.session_state.user_role == "Admin":
            from views.user_management import render_user_management
            render_user_management(st.session_state.user_name, st.session_state.user_role)
    except ModuleNotFoundError as e:
        st.error(
            f"⚠️ Navigation error: Missing view module ({e.name}). Please ensure all view files exist in the `/views` folder."
        )
    except Exception as e:
        st.error(f"An unexpected error occurred while loading view '{choice}': {e}")


# Entry Point
if __name__ == "__main__":
    if not st.session_state.logged_in:
        render_login()
    else:
        render_app()
