# app.py
import sys
import os
import streamlit as st

# 1. Force project root into system path to resolve module import issues on Streamlit Cloud
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# 2. Page Configuration (Must be the first Streamlit command)
st.set_page_config(
    page_title="Inventory Management System",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 3. Local Package & Database Imports
from database import init_db, login_user
from views.dashboard import render_dashboard
from views.stock_in import render_stock_in
from views.stock_out import render_stock_out
from views.manage_items import render_manage_items

# 4. Initialize Database Tables & Schema Migrations
try:
    init_db()
except Exception as e:
    st.error(f"Failed to initialize database: {e}")

# 5. Initialize Session State Variables
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_name" not in st.session_state:
    st.session_state.user_name = None
if "user_role" not in st.session_state:
    st.session_state.user_role = None

# -------------------------------------------------------------
# LOGIN VIEW
# -------------------------------------------------------------
def render_login():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center;'>📦 Inventory Portal</h1>", unsafe_allow_html=True)
        st.caption("Sign in to manage stock dispatches, receipts, and material logs.")
        
        with st.form("login_form"):
            username_input = st.text_input("Username")
            password_input = st.text_input("Password", type="password")
            submit_login = st.form_submit_button("🔓 Sign In", use_container_width=True)

            if submit_login:
                if not username_input.strip() or not password_input.strip():
                    st.error("Please enter both username and password.")
                else:
                    user = login_user(username_input.strip(), password_input.strip())
                    if user:
                        st.session_state.authenticated = True
                        st.session_state.user_name = user["username"]
                        st.session_state.user_role = user["role"]
                        st.toast(f"Welcome back, {user['username']}!", icon="👋")
                        st.rerun()
                    else:
                        st.error("❌ Invalid username or password.")

# -------------------------------------------------------------
# MAIN APPLICATION ROUTING
# -------------------------------------------------------------
if not st.session_state.authenticated:
    render_login()
else:
    # Sidebar Profile & Logout
    st.sidebar.title(f"👤 {st.session_state.user_name}")
    st.sidebar.caption(f"Role: **{st.session_state.user_role}**")
    
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_name = None
        st.session_state.user_role = None
        st.rerun()

    st.sidebar.divider()

    # Sidebar Navigation Menu
    menu_options = [
        "📊 Dashboard",
        "📥 Stock IN",
        "📤 Stock OUT",
        "📦 Manage Master Items"
    ]
    
    selected_page = st.sidebar.radio("Navigation Menu", menu_options)

    # Route to Views
    if selected_page == "📊 Dashboard":
        render_dashboard(st.session_state.user_name, st.session_state.user_role)
        
    elif selected_page == "📥 Stock IN":
        render_stock_in(st.session_state.user_name, st.session_state.user_role)
        
    elif selected_page == "📤 Stock OUT":
        render_stock_out(st.session_state.user_name, st.session_state.user_role)
        
    elif selected_page == "📦 Manage Master Items":
        render_manage_items(st.session_state.user_name, st.session_state.user_role)
