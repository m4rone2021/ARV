# app.py
import streamlit as st
from database import init_db, login_user, backup_db_to_gdrive

# Page Configuration
st.set_page_config(
    page_title="ARV Site Inventory System",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
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
        "General Site Supplies",
    ]

# Ensure DB & Tables exist on startup
init_db()


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
                            backup_db_to_gdrive()

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
