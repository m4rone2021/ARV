# app.py
import streamlit as st
from database import init_db, get_db

# Views
from views.dashboard import render_dashboard
from views.manage_items import render_manage_items
from views.stock_in import render_stock_in
from views.stock_out import render_stock_out
from views.physical_inventory import render_physical_inventory
from views.schedules import render_schedules
from views.reminders_tasks import render_reminders_tasks
from views.reports import render_reports
from views.user_management import render_user_management

# Page Configuration
st.set_page_config(
    page_title="Inventory Management System",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

def init_session_state():
    """Initialize session state variables for authentication."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "username" not in st.session_state:
        st.session_state.username = ""
    if "user_role" not in st.session_state:
        st.session_state.user_role = ""

def login_screen():
    """Render login form."""
    st.markdown("<h1 style='text-align: center;'>📦 Inventory System Login</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Sign in to access stock monitoring and warehouse workflows.</p>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            username_input = st.text_input("Username").strip()
            password_input = st.text_input("Password", type="password").strip()
            submit_button = st.form_submit_button("Sign In", use_container_width=True)

            if submit_button:
                if not username_input or not password_input:
                    st.error("⚠️ Please enter both username and password.")
                else:
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "SELECT username, role FROM users WHERE username = ? AND password = ?",
                                (username_input, password_input)
                            )
                            user = cursor.fetchone()

                            if user:
                                st.session_state.authenticated = True
                                st.session_state.username = user["username"]
                                st.session_state.user_role = user["role"]
                                st.success("Login successful!")
                                st.rerun()
                            else:
                                st.error("❌ Invalid username or password.")
                    except Exception as e:
                        st.error(f"Database error during login: {e}")

def get_pending_discrepancies_count():
    """Fetch total pending inventory discrepancy count for Admin alert."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM discrepancies WHERE status = 'PENDING'")
            result = cursor.fetchone()
            return result[0] if result else 0
    except Exception:
        return 0

def render_sidebar():
    """Render the application navigation sidebar and user profile."""
    st.sidebar.title("📦 Inventory Portal")
    st.sidebar.markdown(f"**User:** `{st.session_state.username}`")
    st.sidebar.markdown(f"**Role:** `{st.session_state.user_role}`")

    # Admin Alert Badge for Pending Discrepancies
    if st.session_state.user_role == "Admin":
        pending_count = get_pending_discrepancies_count()
        if pending_count > 0:
            st.sidebar.warning(f"🔔 **{pending_count} Discrepancy(s)** awaiting Admin resolution!")

    st.sidebar.divider()

    # Dynamic navigation based on role
    if st.session_state.user_role == "Admin":
        nav_options = [
            "📊 Dashboard",
            "🗂️ manage_items",
            "📥 Stock In",
            "📤 Stock Out",
            "📋 Physical Inventory & Approval",
            "🚚 Schedules & Deliveries",
            "📝 Reminders & Tasks",
            "📈 Reports & Analytics",
            "👥 User Management"
        ]
    else:
        nav_options = [
            "📊 Dashboard",
            "🗂️ Master Catalog",
            "📥 Stock In",
            "📤 Stock Out",
            "📋 Physical Inventory & Approval",
            "🚚 Schedules & Deliveries",
            "📝 Reminders & Tasks",
            "📈 Reports & Analytics"
        ]

    selected_page = st.sidebar.radio("Navigation", nav_options)

    st.sidebar.divider()
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.username = ""
        st.session_state.user_role = ""
        st.rerun()

    return selected_page

def main():
    # Ensure tables exist
    init_db()

    # Initialize session
    init_session_state()

    # Render login or main dashboard
    if not st.session_state.authenticated:
        login_screen()
    else:
        selected_page = render_sidebar()

        # Page Router
        if selected_page == "📊 Dashboard":
            render_dashboard(st.session_state.username, st.session_state.user_role)
        elif selected_page == "🗂️ Master Catalog":
            render_master_catalog(st.session_state.username, st.session_state.user_role)
        elif selected_page == "📥 Stock In":
            render_stock_in(st.session_state.username, st.session_state.user_role)
        elif selected_page == "📤 Stock Out":
            render_stock_out(st.session_state.username, st.session_state.user_role)
        elif selected_page == "📋 Physical Inventory & Approval":
            render_physical_inventory(st.session_state.username, st.session_state.user_role)
        elif selected_page == "🚚 Schedules & Deliveries":
            render_schedules(st.session_state.username, st.session_state.user_role)
        elif selected_page == "📝 Reminders & Tasks":
            render_reminders_tasks(st.session_state.username, st.session_state.user_role)
        elif selected_page == "📈 Reports & Analytics":
            render_reports(st.session_state.username, st.session_state.user_role)
        elif selected_page == "👥 User Management":
            render_user_management(st.session_state.username, st.session_state.user_role)

if __name__ == "__main__":
    main()
