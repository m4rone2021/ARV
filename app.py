import sys
from pathlib import Path

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from database import (
    AuthError,
    ConfigError,
    NetworkError,
    ARVError,
    change_password,
    create_test_file_in_gdrive,
    log_user_action,
    login_user,
    sb,
)

st.set_page_config(
    page_title="ARV Site Inventory System",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Session state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "user_role" not in st.session_state:
    st.session_state.user_role = "User"
if "must_change_password" not in st.session_state:
    st.session_state.must_change_password = False
if "flash_msg" not in st.session_state:
    st.session_state.flash_msg = None


def _show_flash():
    """Display and clear any pending flash message (survives st.rerun)."""
    msg = st.session_state.get("flash_msg")
    if not msg:
        return
    level, text = msg
    if level == "success":
        st.success(text)
    elif level == "warning":
        st.warning(text)
    elif level == "error":
        st.error(text)
    elif level == "info":
        st.info(text)
    st.session_state.flash_msg = None


def _friendly_error(e: Exception) -> str:
    """Convert an exception into a user-facing message."""
    if isinstance(e, ConfigError):
        return (
            "⚙️ Configuration error — the app is not properly connected. "
            "Please contact an administrator."
        )
    if isinstance(e, NetworkError):
        return (
            "🌐 Cannot reach the database right now. "
            "Please check your connection and try again."
        )
    if isinstance(e, AuthError):
        return f"❌ {e}"
    if isinstance(e, ARVError):
        return f"⚠️ {e}"
    return f"⚠️ Something went wrong: {e}"


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
        _show_flash()

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
                    try:
                        user_data = login_user(username.strip(), password.strip())
                    except AuthError as e:
                        log_user_action(
                            username.strip()[:100], "LOGIN_FAILED", "Invalid credentials"
                        )
                        st.error(f"❌ {e}")
                        user_data = None
                    except (ConfigError, NetworkError) as e:
                        log_user_action(
                            username.strip()[:100],
                            "LOGIN_FAILED",
                            f"Infrastructure error: {type(e).__name__}",
                        )
                        st.error(_friendly_error(e))
                        user_data = None
                    except ARVError as e:
                        st.error(_friendly_error(e))
                        user_data = None
                    except Exception as e:
                        # Unexpected error — log it but don't leak the traceback
                        print(f"[render_login] Unexpected error: {e}")
                        st.error(
                            "⚠️ Unexpected error during login. "
                            "Please contact an administrator."
                        )
                        user_data = None

                    if user_data:
                        st.session_state.logged_in = True
                        st.session_state.user_name = user_data["username"]
                        st.session_state.user_role = user_data["role"]
                        st.session_state.must_change_password = user_data.get(
                            "must_change_password", False
                        )

                        log_user_action(
                            user_data["username"], "LOGIN", "Successful login"
                        )

                        st.toast(
                            f"Welcome back, {user_data['username']}!", icon="👋"
                        )
                        st.rerun()


def render_force_password_change():
    st.markdown(
        "<h1 style='text-align: center;'>🔐 Password Change Required</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align: center; color: gray;'>Your account is using a temporary password. "
        "Please set a new password to continue.</p>",
        unsafe_allow_html=True,
    )
    st.write("---")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.info(f"👤 Signed in as: **{st.session_state.user_name}**")

        with st.form("change_pw_form", clear_on_submit=False):
            new_pw = st.text_input("New Password*", type="password")
            confirm_pw = st.text_input("Confirm New Password*", type="password")

            st.caption(
                "Password must be **at least 8 characters**, contain at least "
                "**one letter** and **one number**."
            )

            submit = st.form_submit_button(
                "🔐 Set New Password", use_container_width=True
            )

            if submit:
                # Client-side pre-checks (mirror server-side policy)
                if not new_pw:
                    st.error("⚠️ Please enter a new password.")
                elif len(new_pw) < 8:
                    st.error("⚠️ Password must be at least 8 characters long.")
                elif not any(c.isalpha() for c in new_pw):
                    st.error("⚠️ Password must contain at least one letter.")
                elif not any(c.isdigit() for c in new_pw):
                    st.error("⚠️ Password must contain at least one number.")
                elif new_pw != confirm_pw:
                    st.error("⚠️ Passwords do not match.")
                else:
                    try:
                        change_password(st.session_state.user_name, new_pw)
                        log_user_action(
                            st.session_state.user_name,
                            "PASSWORD_CHANGED",
                            "User set a new password after forced change",
                        )
                        st.session_state.must_change_password = False
                        st.session_state.flash_msg = (
                            "success",
                            "✅ Password changed successfully! Welcome to ARV.",
                        )
                        st.rerun()
                    except ValueError as e:
                        st.error(f"⚠️ {e}")
                    except (ConfigError, NetworkError) as e:
                        st.error(_friendly_error(e))
                    except ARVError as e:
                        st.error(_friendly_error(e))
                    except Exception as e:
                        print(f"[change_password] Unexpected: {e}")
                        st.error(
                            "⚠️ Failed to change password. Please try again or "
                            "contact an administrator."
                        )

        st.divider()
        if st.button("🚪 Cancel and Logout", use_container_width=True):
            log_user_action(
                st.session_state.user_name,
                "LOGOUT",
                "Cancelled forced password change",
            )
            st.session_state.logged_in = False
            st.session_state.user_name = ""
            st.session_state.user_role = "User"
            st.session_state.must_change_password = False
            st.rerun()


def render_app():
    st.sidebar.markdown(f"### 👤 Logged in: **{st.session_state.user_name}**")
    st.sidebar.caption(f"Role: **{st.session_state.user_role}**")
    st.sidebar.divider()

    menu_map = {
        "📊 Dashboard": "Dashboard",
        "📋 Physical Inventory": "Physical Inventory",
        "📦 Manage Master Items": "Manage Master Items",
        "📥 Stock IN": "Stock IN",
        "📤 Stock OUT": "Stock OUT",
        "⚠️ Low Stock Alerts": "Low Stock Alerts",
        "🚚 Schedules & Deliveries": "Schedules & Deliveries",
        "📝 Reminders & Tasks": "Reminders & Tasks",
        "📜 Transaction Ledger": "Transaction Ledger",
        "📝 Edit / Void Transactions": "Edit / Void Transactions",
    }
    if st.session_state.user_role == "Admin":
        menu_map["👥 User Management"] = "User Management"

    selected_label = st.sidebar.radio("Main Menu", list(menu_map.keys()), index=0)
    choice = menu_map[selected_label]

    st.sidebar.divider()

    if st.session_state.user_role == "Admin":
        st.sidebar.subheader("🛠️ Admin Tools")
        if st.sidebar.button("🧪 Test Drive Upload", use_container_width=True):
            with st.spinner("Uploading test file to Google Drive..."):
                try:
                    file_id = create_test_file_in_gdrive()
                    if file_id:
                        st.sidebar.success("✅ Drive auth works!")
                    else:
                        st.sidebar.error(
                            "❌ Drive upload failed. Check credentials or folder ID."
                        )
                except Exception as e:
                    print(f"[Drive test] {e}")
                    st.sidebar.error(
                        "❌ Drive upload error. See server logs for details."
                    )
        st.sidebar.divider()

    if st.sidebar.button("🚪 Logout", use_container_width=True):
        log_user_action(st.session_state.user_name, "LOGOUT", "User logged out")
        st.session_state.logged_in = False
        st.session_state.user_name = ""
        st.session_state.user_role = "User"
        st.session_state.must_change_password = False
        st.rerun()

    # Flash message from previous rerun
    _show_flash()

    try:
        if choice == "Dashboard":
            from views.dashboard import render_dashboard
            render_dashboard(st.session_state.user_name, st.session_state.user_role)
        elif choice == "Manage Master Items":
            from views.manage_items import render_manage_items
            render_manage_items(st.session_state.user_name, st.session_state.user_role)
        elif choice == "Physical Inventory":
            from views.physical_inventory import render_physical_inventory
            render_physical_inventory(st.session_state.user_name, st.session_state.user_role)
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
        elif choice == "Edit / Void Transactions":
            from views.edit_void import render_edit_void
            render_edit_void(st.session_state.user_name, st.session_state.user_role)
        elif choice == "User Management" and st.session_state.user_role == "Admin":
            from views.user_management import render_user_management
            render_user_management(st.session_state.user_name, st.session_state.user_role)
    except ModuleNotFoundError as e:
        st.error(f"⚠️ Navigation error: Missing view module ({e.name}).")
    except Exception as e:
        # Log view crashes so we can diagnose later
        try:
            log_user_action(
                st.session_state.user_name,
                "VIEW_ERROR",
                f"{choice}: {type(e).__name__}: {str(e)[:300]}",
            )
        except Exception:
            pass
        print(f"[render_app] View '{choice}' crashed: {e}")
        st.error(
            f"⚠️ An error occurred while loading **{choice}**. "
            "The error has been logged. Please try again or contact an administrator."
        )


if __name__ == "__main__":
    if not st.session_state.logged_in:
        render_login()
    elif st.session_state.must_change_password:
        render_force_password_change()
    else:
        render_app()
