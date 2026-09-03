# app.py
import streamlit as st
from database import init_db, login_user

# Import view functions from the views module directory
from views.dashboard import render_dashboard
from views.stock_in import render_stock_in
# from views.stock_out import render_stock_out
# from views.low_stock import render_low_stock
# ... import remaining view renderers here

# 1. PAGE SETUP & DATABASE INITIALIZATION
st.set_page_config(
    page_title="Site Materials & Inventory Ledger",
    page_icon="📦",
    layout="wide"
)

init_db()

# 2. SESSION & AUTHENTICATION MANAGEMENT
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_name = ""
    st.session_state.user_role = ""

if not st.session_state.logged_in:
    st.title("🔒 Site Materials & Inventory Login")
    with st.form("login_form"):
        u_input = st.text_input("Username")
        p_input = st.text_input("Password", type="password")
        submit_login = st.form_submit_button("Sign In")
        
        if submit_login:
            user_data = login_user(u_input.strip(), p_input.strip())
            if user_data:
                st.session_state.logged_in = True
                st.session_state.user_name = user_data["username"]
                st.session_state.user_role = user_data["role"]
                st.success(f"Welcome back, {user_data['username']}!")
                st.rerun()
            else:
                st.error("Invalid username or password.")
    st.stop()

# 3. NAVIGATION ROUTER
user_name = st.session_state.user_name
user_role = st.session_state.user_role

st.sidebar.title("📦 Navigation")
st.sidebar.markdown(f"**User:** {user_name}  \n**Role:** `{user_role}`")

menu_options = [
    "📊 Dashboard Overview",
    "📥 Stock Receipt (IN)",
    "📤 Material Issue (OUT)",
    "⚠️ Low Stock Alerts",
    "📝 Edit/Void Transactions",
    "➕ Manage Master Items",
    "📜 Master Audit Log",
    "⏰ Reminders",
    "📅 Schedule"
]

if user_role == "Head Office":
    menu_options.insert(7, "👤 Manage Users")

selected_menu = st.sidebar.radio("Go to:", menu_options)

if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.session_state.user_name = ""
    st.session_state.user_role = ""
    st.rerun()

# 4. DISPATCH VIEW ROUTING
if selected_menu == "📊 Dashboard Overview":
    render_dashboard()

elif selected_menu == "📥 Stock Receipt (IN)":
    render_stock_in(user_name, user_role)

# Add remaining conditional routes here to delegate rendering to views/ modules
