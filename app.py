# app.py
import streamlit as st
from database import init_db, login_user
from views.dashboard import render_dashboard
from views.stock_in import render_stock_in
from views.stock_out import render_stock_out
from views.low_stock import render_low_stock
from views.edit_void import render_edit_void
from views.master_items import render_master_items
from views.audit_log import render_audit_log
from views.manage_users import render_manage_users
from views.reminders import render_reminders
from views.schedules import render_schedules

# Set Streamlit page layout
st.set_page_config(
    page_title="Inventory Management System",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize database tables & default admin accounts
init_db()

# Session State Initialization
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_name" not in st.session_state:
    st.session_state.user_name = None
if "user_role" not in st.session_state:
    st.session_state.user_role = None

# --- AUTHENTICATION SCREEN ---
if not st.session_state.authenticated:
    st.title("🔐 Inventory Management System")
    st.subheader("Sign In")

    col1, _ = st.columns([1, 1])
    with col1:
        with st.form("login_form"):
            username_input = st.text_input("Username")
            password_input = st.text_input("Password", type="password")
            submit_login = st.form_submit_button("Sign In")

            if submit_login:
                user = login_user(username_input.strip(), password_input.strip())
                if user:
                    st.session_state.authenticated = True
                    st.session_state.user_name = user["username"]
                    st.session_state.user_role = user["role"]
                    st.toast(f"Welcome back, {user['username']}!", icon="👋")
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

# --- MAIN APPLICATION DASHBOARD ---
else:
    # Sidebar Profile & Logout
    st.sidebar.title("📌 Navigation")
    st.sidebar.markdown(f"**Logged in as:** `{st.session_state.user_name}`")
    st.sidebar.markdown(f"**Role:** `{st.session_state.user_role}`")
    
    if st.sidebar.button("🚪 Logout", key="logout_btn"):
        st.session_state.authenticated = False
        st.session_state.user_name = None
        st.session_state.user_role = None
        st.rerun()

    st.sidebar.divider()

    # Sidebar Navigation Menu
    nav_options = [
        "📊 Dashboard",
        "📥 Stock IN",
        "📤 Stock OUT",
        "⚠️ Low Stock Alerts",
        "📝 Edit / Void Entries",
        "➕ Manage Master Items",
        "📜 Audit Log Ledger",
        "📌 Reminders & Tasks",
        "📅 Schedules & Calendar"
    ]

    # Include User Management for Head Office role
    if st.session_state.user_role == "Head Office":
        nav_options.append("👤 Manage Users")

    choice = st.sidebar.radio("Select View:", nav_options)

    # Route navigation choices to modules
    if choice == "📊 Dashboard":
        render_dashboard()
    elif choice == "📥 Stock IN":
        render_stock_in(st.session_state.user_name, st.session_state.user_role)
    elif choice == "📤 Stock OUT":
        render_stock_out(st.session_state.user_name, st.session_state.user_role)
    elif choice == "⚠️ Low Stock Alerts":
        render_low_stock()
    elif choice == "📝 Edit / Void Entries":
        render_edit_void(st.session_state.user_name, st.session_state.user_role)
    elif choice == "➕ Manage Master Items":
        render_master_items()
    elif choice == "📜 Audit Log Ledger":
        render_audit_log()
    elif choice == "📌 Reminders & Tasks":
        render_reminders(st.session_state.user_name)
    elif choice == "📅 Schedules & Calendar":
        render_schedules(st.session_state.user_name)
    elif choice == "👤 Manage Users":
        render_manage_users()
