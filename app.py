import streamlit as st
import pandas as pd

from database import init_db, get_db

# Import existing views
from views.manage_items import render_manage_items
from views.stock_in import render_stock_in
from views.stock_out import render_stock_out
from views.schedules import render_schedules

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
# SESSION STATE SETUP
# -------------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "user_role" not in st.session_state:
    st.session_state.user_role = ""

# -------------------------------------------------------------
# ADMIN PANEL VIEW
# -------------------------------------------------------------
def render_admin_panel(user_name, user_role):
    if user_role != "Admin":
        st.error("🚫 Access Denied: Admin privileges required.")
        return

    st.title("🔑 Admin Control Panel")
    st.caption("Manage application users and credentials.")

    tab_users, tab_create = st.tabs(["👥 Active Users", "➕ Create New User"])

    with tab_users:
        try:
            with get_db() as conn:
                df = pd.read_sql_query("SELECT id, username, role FROM users ORDER BY id ASC", conn)
            
            st.dataframe(df, use_container_width=True, hide_index=True)
            
            st.divider()
            st.subheader("Reset User Password")
            with st.form("reset_pwd_form"):
                user_list = df["username"].tolist() if not df.empty else []
                target_user = st.selectbox("Select User", user_list)
                new_password = st.text_input("New Password", type="password").strip()
                reset_btn = st.form_submit_button("Reset Password")

                if reset_btn:
                    if not new_password:
                        st.error("Password cannot be empty.")
                    else:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("UPDATE users SET password = ? WHERE username = ?", (new_password, target_user))
                            conn.commit()
                            st.success(f"Password updated for user `{target_user}`!")
        except Exception as e:
            st.error(f"Error loading user list: {e}")

    with tab_create:
        with st.form("create_user_form"):
            new_username = st.text_input("Username*").strip()
            new_password = st.text_input("Password*", type="password").strip()
            new_role = st.selectbox("Role*", ["Staff", "Admin"])
            create_btn = st.form_submit_button("Create User", use_container_width=True)

            if create_btn:
                if not new_username or not new_password:
                    st.error("Please fill in all required fields.")
                else:
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                                           (new_username, new_password, new_role))
                            conn.commit()
                            st.success(f"User `{new_username}` created with role `{new_role}`!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error creating user: {e}")

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

    # Dynamically expose Admin Control menu for Admin users
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
