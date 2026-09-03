# app.py
import streamlit as st
from database import init_db, get_db

# Import views
from views.manage_items import render_manage_items
from views.stock_in import render_stock_in
from views.stock_out import render_stock_out
from views.schedules import render_schedules
from views.admin_panel import render_admin_panel  # Imported admin panel view

# Page configuration
st.set_page_config(
    page_title="ARV Inventory System",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Database on launch
init_db()

# -------------------------------------------------------------
# SESSION STATE SETUP & EMERGENCY ADMIN BYPASS
# -------------------------------------------------------------
# Temporarily set defaults to True so you bypass the login screen immediately.
if "authenticated" not in st.session_state:
    st.session_state.authenticated = True  # Bypass login screen
if "user_name" not in st.session_state:
    st.session_state.user_name = "admin"
if "user_role" not in st.session_state:
    st.session_state.user_role = "Admin"

# -------------------------------------------------------------
# AUTHENTICATION SCREEN
# -------------------------------------------------------------
if not st.session_state.authenticated:
    st.title("🔐 ARV Inventory Management System")
    st.caption("Please log in to access the system.")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("User Login")
            username = st.text_input("Username").strip()
            password = st.text_input("Password", type="password").strip()
            login_btn = st.form_submit_button("Login", use_container_width=True)

            if login_btn:
                if not username or not password:
                    st.error("⚠️ Please enter both username and password.")
                else:
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT username, role FROM users WHERE username = ? AND password = ?", 
                                (username, password)
                            )
                            user = cursor.fetchone()
                            
                            if user:
                                st.session_state.authenticated = True
                                st.session_state.user_name = user["username"]
                                st.session_state.user_role = user["role"]
                                st.success("Login successful!")
                                st.rerun()
                            else:
                                st.error("❌ Invalid Username or Password.")
                    except Exception as e:
                        st.error(f"Error during login: {e}")

# -------------------------------------------------------------
# MAIN APPLICATION INTERFACE
# -------------------------------------------------------------
else:
    # Sidebar Navigation
    st.sidebar.title("📦 ARV Inventory")
    st.sidebar.markdown(f"**Logged in as:** `{st.session_state.user_name}`")
    st.sidebar.markdown(f"**Role:** `{st.session_state.user_role}`")
    st.sidebar.divider()

    menu_options = [
        "Manage Items",
        "Stock In",
        "Stock Out",
        "Schedules & Deliveries"
    ]

    # Show Admin Control option exclusively to users with the Admin role
    if st.session_state.user_role == "Admin":
        menu_options.append("🔑 Admin Control")

    page = st.sidebar.radio("Navigation Menu", menu_options)

    st.sidebar.divider()
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_name = ""
        st.session_state.user_role = ""
        st.rerun()

    # Route Page Views
    if page == "Manage Items":
        render_manage_items(st.session_state.user_name, st.session_state.user_role)
        
    elif page == "Stock In":
        render_stock_in(st.session_state.user_name, st.session_state.user_role)
        
    elif page == "Stock Out":
        render_stock_out(st.session_state.user_name, st.session_state.user_role)
        
    elif page == "Schedules & Deliveries":
        render_schedules(st.session_state.user_name, st.session_state.user_role)

    elif page == "🔑 Admin Control":
        render_admin_panel(st.session_state.user_name, st.session_state.user_role)
