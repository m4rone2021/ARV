# app.py
import streamlit as st
from database import init_db, login_user

# Page Configuration
st.set_page_config(
    page_title="ARV Site Inventory System",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
        "General Site Supplies"
    ]

# Ensure DB & Tables exist on load
init_db()


# -----------------------------------------------------------------------------
# LOGIN PAGE
# -----------------------------------------------------------------------------
def render_login():
    st.markdown("<h1 style='text-align: center;'>🏗️ ARV Construction Site Inventory</h1>", unsafe_allow_html=True)
    st.markdown("<h4 style='text-align: center; color: gray;'>Material Tracking & Warehouse Management</h4>", unsafe_allow_html=True)
    st.write("---")

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.subheader("🔑 Sign In")
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submit = st.form_submit_button("Login", use_container_width=True)

            if submit:
                if not username.strip() or not password.strip():
                    st.error("⚠️ Please fill in both Username and Password.")
                else:
                    user_data = login_user(username.strip(), password.strip())
                    if user_data:
                        st.session_state.logged_in = True
                        st.session_state.user_name = user_data["username"]
                        st.session_state.user_role = user_data["role"]
                        st.success(f"Welcome back, {user_data['username']}!")
                        st.rerun()
                    else:
                        st.error("❌ Invalid Username or Password.")

        st.caption("Default Admin Credentials: **admin** / **admin123**")


# -----------------------------------------------------------------------------
# MAIN APPLICATION
# -----------------------------------------------------------------------------
def render_app():
    # Lazy Imports for Views
    from views.dashboard import render_dashboard
    from views.manage_items import render_manage_items
    from views.stock_in import render_stock_in
    from views.stock_out import render_stock_out
    from views.low_stock import render_low_stock
    from views.schedules import render_schedules
    from views.reminders import render_reminders
    from views.audit_log import render_audit_log

    # Sidebar Navigation
    st.sidebar.markdown(f"### 👤 Logged in as: **{st.session_state.user_name}**")
    st.sidebar.caption(f"Role: **{st.session_state.user_role}**")
    st.sidebar.divider()

    menu_options = [
        "📊 Executive Dashboard",
        "📦 Manage Master Items",
        "📥 Stock IN Receive",
        "📤 Stock OUT Dispatch",
        "⚠️ Low Stock Alerts",
        "📅 Schedules & Deliveries",
        "📝 Reminders & Tasks",
        "📜 Transaction Ledger & Audit"
    ]

    choice = st.sidebar.radio("Navigation", menu_options)

    st.sidebar.divider()
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.user_name = ""
        st.session_state.user_role = "User"
        st.rerun()

    # View Router
    if choice == "📊 Executive Dashboard":
        render_dashboard(st.session_state.user_name, st.session_state.user_role)
    elif choice == "📦 Manage Master Items":
        render_manage_items(st.session_state.user_name, st.session_state.user_role)
    elif choice == "📥 Stock IN Receive":
        render_stock_in(st.session_state.user_name, st.session_state.user_role)
    elif choice == "📤 Stock OUT Dispatch":
        render_stock_out(st.session_state.user_name, st.session_state.user_role)
    elif choice == "⚠️ Low Stock Alerts":
        render_low_stock(st.session_state.user_name, st.session_state.user_role)
    elif choice == "📅 Schedules & Deliveries":
        render_schedules(st.session_state.user_name, st.session_state.user_role)
    elif choice == "📝 Reminders & Tasks":
        render_reminders(st.session_state.user_name, st.session_state.user_role)
    elif choice == "📜 Transaction Ledger & Audit":
        render_audit_log(st.session_state.user_name, st.session_state.user_role)


# -----------------------------------------------------------------------------
# APP ENTRY POINT
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    if not st.session_state.logged_in:
        render_login()
    else:
        render_app()
