import sqlite3
import pandas as pd
import streamlit as st
from database import backup_db_to_gdrive, get_db, hash_password, init_db


def apply_orange_theme():
    st.markdown(
        """
        <style>
            /* Primary theme colors - Orange Variation */
            :root {
                --primary-orange: #FF6F00;
                --hover-orange: #E65100;
                --light-orange-bg: #FFF3E0;
                --border-orange: #FFB74D;
            }

            /* Style Streamlit Tabs */
            button[data-baseweb="tab"] {
                background-color: #FAFAFA;
                border-radius: 8px 8px 0px 0px;
                padding: 10px 16px;
                color: #555555 !important;
                font-weight: 600;
                border: 1px solid #E0E0E0;
                border-bottom: none;
                margin-right: 4px;
            }

            /* Hover state for tabs */
            button[data-baseweb="tab"]:hover {
                background-color: var(--light-orange-bg);
                color: var(--hover-orange) !important;
            }

            /* Active Selected Tab */
            button[data-baseweb="tab"][aria-selected="true"] {
                background-color: var(--primary-orange) !important;
                color: #FFFFFF !important;
                border-color: var(--primary-orange) !important;
            }

            /* Active Tab highlight bar below text */
            div[data-baseweb="tab-highlight"] {
                background-color: var(--hover-orange) !important;
            }

            /* Form Submit Buttons - Orange Theme */
            div.stButton > button[kind="primary"],
            div.stFormSubmitButton > button {
                background-color: var(--primary-orange) !important;
                color: white !important;
                border: none !important;
                border-radius: 6px;
                font-weight: 600;
            }

            div.stButton > button[kind="primary"]:hover,
            div.stFormSubmitButton > button:hover {
                background-color: var(--hover-orange) !important;
                box-shadow: 0px 4px 10px rgba(230, 81, 0, 0.3);
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_user_management(user_name, user_role):
    # Apply Orange Theme Styling
    apply_orange_theme()

    st.title("👤 User Management")
    st.caption("Manage site operator accounts, permissions, and security credentials.")

    # Restrict view access to Admins only
    if user_role != "Admin":
        st.error(
            "⛔ Access Denied: You must have Administrator privileges to view or modify user credentials."
        )
        return

    init_db()

    # Flash notification queue for post-rerun messages
    if "user_mgmt_flash" in st.session_state:
        msg_type, msg_text = st.session_state.pop("user_mgmt_flash")
        if msg_type == "success":
            st.success(msg_text)
        elif msg_type == "error":
            st.error(msg_text)

    tab_users, tab_add, tab_reset = st.tabs(
        ["📋 Registered Users", "➕ Create New User", "🔑 Reset Password"]
    )

    # -------------------------------------------------------------
    # TAB 1: REGISTERED USERS & DELETION
    # -------------------------------------------------------------
    with tab_users:
        st.subheader("System Accounts")

        try:
            with get_db() as conn:
                df = pd.read_sql_query(
                    "SELECT id, username, role FROM users ORDER BY id ASC", conn
                )

            if not df.empty:
                df_display = df.rename(
                    columns={
                        "id": "User ID",
                        "username": "Username",
                        "role": "Role / Access Level",
                    }
                )
                st.dataframe(
                    df_display,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "User ID": st.column_config.NumberColumn("User ID", format="%d"),
                        "Username": st.column_config.TextColumn("Username"),
                        "Role / Access Level": st.column_config.TextColumn("Role / Access Level"),
                    }
                )

                st.divider()
                st.subheader("🗑️ Delete User Account")

                # Prevent self-deletion
                deletable_users = df[df["username"] != user_name]["username"].tolist()

                if deletable_users:
                    with st.form("delete_user_form", clear_on_submit=True):
                        target_user = st.selectbox(
                            "Select Account to Delete", deletable_users
                        )
                        submit_delete = st.form_submit_button(
                            "🗑️ Delete Account", use_container_width=True
                        )

                        if submit_delete:
                            try:
                                with get_db() as conn:
                                    cursor = conn.cursor()

                                    # Check target user role to prevent removing the last admin
                                    cursor.execute(
                                        "SELECT role FROM users WHERE username = ?",
                                        (target_user,),
                                    )
                                    row = cursor.fetchone()
                                    target_role = row[0] if row else None

                                    if target_role == "Admin":
                                        cursor.execute(
                                            "SELECT COUNT(*) FROM users WHERE role = 'Admin'"
                                        )
                                        admin_count = cursor.fetchone()[0]

                                        if admin_count <= 1:
                                            st.error(
                                                "⚠️ Action Blocked: Cannot delete the last remaining Administrator account."
                                            )
                                            st.stop()

                                    cursor.execute(
                                        "DELETE FROM users WHERE username = ?",
                                        (target_user,),
                                    )
                                    conn.commit()

                                # Sync updated database state to Google Drive
                                backup_db_to_gdrive()

                                st.session_state["user_mgmt_flash"] = (
                                    "success",
                                    f"✅ Account **{target_user}** successfully removed.",
                                )
                                st.rerun()

                            except Exception as e:
                                st.error(f"Failed to delete account: {e}")
                else:
                    st.info("No other user accounts available for deletion.")
            else:
                st.warning("No user accounts found.")

        except Exception as e:
            st.error(f"Error fetching users: {e}")

    # -------------------------------------------------------------
    # TAB 2: CREATE NEW USER
    # -------------------------------------------------------------
    with tab_add:
        st.subheader("Add Site Account")

        with st.form("create_user_form", clear_on_submit=True):
            new_username = st.text_input("Username*")
            new_role = st.selectbox("Role / Access Level*", ["User", "Admin"])
            new_password = st.text_input(
                "Initial Password*", type="password"
            )
            confirm_password = st.text_input(
                "Confirm Password*", type="password"
            )

            submit_create = st.form_submit_button(
                "💾 Create User Account", use_container_width=True
            )

            if submit_create:
                clean_user = new_username.strip()
                if not clean_user or not new_password:
                    st.error("⚠️ Username and password are required.")
                elif len(new_password) < 6:
                    st.error("⚠️ Password must be at least 6 characters long.")
                elif new_password != confirm_password:
                    st.error("⚠️ Passwords do not match.")
                else:
                    try:
                        hashed_pass = hash_password(new_password)
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                                (clean_user, hashed_pass, new_role),
                            )
                            conn.commit()

                        # Sync updated database state to Google Drive
                        backup_db_to_gdrive()

                        st.session_state["user_mgmt_flash"] = (
                            "success",
                            f"✅ User account **{clean_user}** ({new_role}) created successfully.",
                        )
                        st.rerun()

                    except sqlite3.IntegrityError:
                        st.error(
                            f"⚠️ Username **{clean_user}** already exists. Please choose a different username."
                        )
                    except Exception as e:
                        st.error(f"Failed to create account: {e}")

    # -------------------------------------------------------------
    # TAB 3: RESET USER PASSWORD
    # -------------------------------------------------------------
    with tab_reset:
        st.subheader("Password Override")

        try:
            with get_db() as conn:
                df_all = pd.read_sql_query(
                    "SELECT username FROM users ORDER BY username ASC", conn
                )
            user_list = df_all["username"].tolist() if not df_all.empty else []
        except Exception:
            user_list = []

        if user_list:
            with st.form("reset_password_form", clear_on_submit=True):
                selected_user = st.selectbox("Select Account", user_list)
                reset_pass = st.text_input("New Password*", type="password")
                confirm_reset_pass = st.text_input(
                    "Confirm New Password*", type="password"
                )

                submit_reset = st.form_submit_button(
                    "🔑 Reset Password", use_container_width=True
                )

                if submit_reset:
                    if not reset_pass:
                        st.error("⚠️ Please enter a new password.")
                    elif len(reset_pass) < 6:
                        st.error("⚠️ Password must be at least 6 characters long.")
                    elif reset_pass != confirm_reset_pass:
                        st.error("⚠️ Passwords do not match.")
                    else:
                        try:
                            hashed_reset = hash_password(reset_pass)
                            with get_db() as conn:
                                cursor = conn.cursor()
                                cursor.execute(
                                    "UPDATE users SET password = ? WHERE username = ?",
                                    (hashed_reset, selected_user),
                                )
                                conn.commit()

                            # Sync updated database state to Google Drive
                            backup_db_to_gdrive()

                            st.session_state["user_mgmt_flash"] = (
                                "success",
                                f"✅ Password for **{selected_user}** updated successfully.",
                            )
                            st.rerun()

                        except Exception as e:
                            st.error(f"Failed to reset password: {e}")
        else:
            st.info("No accounts available to update.")
