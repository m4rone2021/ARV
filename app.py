# app.py
import streamlit as st
from database import init_db, login_user

# 1. Page Configuration
st.set_page_config(
    page_title="ARV Site Inventory System",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. Database Initialization
init_db()


# 3. Session State Initialization
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "user_role" not in st.session_state:
    st.session_state.user_role = ""


# 4. Login View
def render_login():
    st.markdown("<h2 style='text-align: center;'>📦 ARV Site Inventory System</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Please enter your credentials to access the system.</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login", use_container_width=True)

            if submit:
                if not username.strip() or not password.strip():
                    st.error("⚠️ Please enter both username and password.")
                else:
                    user = login_user(username, password)
                    if user:
                        st.session_state.authenticated = True
                        st.session_state.user_name = user["username"]
                        st.session_state.user_role = user["role"]
                        st.success(f"Welcome back, {user['username']}!")
                        st.rerun()
                    else:
                        st.error("❌ Invalid Username or Password. Default admin credentials: admin / admin123")


# 5. Main Application & View Routing
def render_app():
    # Sidebar Header & User Info
    st.sidebar.title("📦 ARV Inventory")
    st.sidebar.write(f"👤 **User:** {st.session_state.user_name}")
    st.sidebar.write(f"🛡️ **Role:** {st.session_state.user_role}")
    st.sidebar.divider()

    # Sidebar Navigation Menu
    menu_options = [
        "Dashboard",
        "Manage Items",
        "Stock In",
        "Stock Out",
        "Low Stock Alerts",
        "Schedules & Deliveries",
        "Reminders & Tasks",
        "Audit Log",
    ]

    # Include User Management for Admin users
    if st.session_state.user_role == "Admin":
        menu_options.append("User Management")

    menu_choice = st.sidebar.radio("Navigation", menu_options)
    st.sidebar.divider()

    # Logout Button
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_name = ""
        st.session_state.user_role = ""
        st.rerun()

    # View Routing Engine
    if menu_choice == "Dashboard":
        from views.dashboard import render_dashboard
        render_dashboard(st.session_state.user_name, st.session_state.user_role)

    elif menu_choice == "Manage Items":
        from views.manage_items import render_manage_items
        render_manage_items(st.session_state.user_name, st.session_state.user_role)

    elif menu_choice == "Stock In":
        from views.stock_in import render_stock_in
        render_stock_in(st.session_state.user_name, st.session_state.user_role)

    elif menu_choice == "Stock Out":
        from views.stock_out import render_stock_out
        render_stock_out(st.session_state.user_name, st.session_state.user_role)

    elif menu_choice == "Low Stock Alerts":
        from views.low_stock import render_low_stock
        render_low_stock(st.session_state.user_name, st.session_state.user_role)

    elif menu_choice == "Schedules & Deliveries":
        from views.schedules import render_schedules
        render_schedules(st.session_state.user_name, st.session_state.user_role)

    elif menu_choice == "Reminders & Tasks":
        from views.reminders import render_reminders
        render_reminders(st.session_state.user_name, st.session_state.user_role)

    elif menu_choice == "Audit Log":
        from views.audit_log import render_audit_log
        render_audit_log(st.session_state.user_name, st.session_state.user_role)

    elif menu_choice == "User Management" and st.session_state.user_role == "Admin":
        from views.user_management import render_user_management
        render_user_management(st.session_state.user_name, st.session_state.user_role)


# 6. Main Entry Point
if not st.session_state.authenticated:
    render_login()
else:
    render_app()
