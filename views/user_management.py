# views/user_management.py
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db, hash_password, init_db

def render_user_management(user_name, user_role):
    st.title("👤 User Management")
    st.caption("Manage site operator accounts, permissions, and security credentials.")

    # Restrict view access to Admins only
    if user_role != "Admin":
        st.error("⛔ Access Denied: You must have Administrator privileges to view or modify user credentials.")
        return

    init_db()

    tab_users, tab_add, tab_reset = st.tabs([
        "📋 Registered Users", 
        "➕ Create New User", 
        "🔑 Reset Password"
    ])

    # -------------------------------------------------------------
    # TAB 1: REGISTERED USERS & DELETION
    # -------------------------------------------------------------
    with tab_users:
        st.subheader("System Accounts")
        
        try:
            with get_db() as conn:
                df = pd.read_sql_query("SELECT id, username, role FROM users ORDER BY id ASC", conn)

            if not df.empty:
                df_display = df.rename(columns={
                    "id": "User ID",
                    "username": "Username",
                    "role": "Role / Access Level"
                })
                st.dataframe(df_display, use_container_width=True, hide_index=True)

                st.divider()
                st.subheader("🗑️ Delete User Account")

                # Prevent self-deletion
                deletable_users = df[df["username"] != user_name]["username"].tolist()

                if deletable_users:
                    with st.form("delete_user_form"):
                        target_user = st.selectbox("Select Account to Delete", deletable_users)
                        submit_delete = st.form_submit_button("Delete Account", use_container_width=True)

                        if submit_delete:
                            try:
                                with get_db() as conn:
                                    cursor = conn.cursor()
                                    cursor.execute("DELETE FROM users WHERE username = ?", (target_user,))
                                    conn.commit()
                                    st.success(f"✅ Account **{target_user}** successfully removed.")
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
            col1, col2 = st.columns(2)

            with col1:
                new_username = st.text_input("Username*")
                new_password = st.text_input("Initial Password*", type="password")

            with col2:
                new_role = st.selectbox("Role / Access Level*", ["User", "Admin"])
                confirm_password = st.text_input("Confirm Password*", type="password")

            submit_create = st.form_submit_button("💾 Create User Account", use_container_width=True)

            if submit_create:
                clean_user = new_username.strip()
                if not clean_user or not new_password:
                    st.error("⚠️ Username and password are required.")
                elif new_password != confirm_password:
                    st.error("⚠️ Passwords do not match.")
                else:
                    try:
                        hashed_pass = hash_password(new_password)
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                                (clean_user, hashed_pass, new_role)
                            )
                            conn.commit()
                            st.success(f"✅ User account **{clean_user}** ({new_role}) created successfully.")
                            st.rerun()
                    except sqlite3.IntegrityError:
                        st.error(f"⚠️ Username **{clean_user}** already exists. Please choose a different username.")
                    except Exception as e:
                        st.error(f"Failed to create account: {e}")

    # -------------------------------------------------------------
    # TAB 3: RESET USER PASSWORD
    # -------------------------------------------------------------
    with tab_reset:
        st.subheader("Password Override")

        try:
            with get_db() as conn:
                df_all = pd.read_sql_query("SELECT username FROM users ORDER BY username ASC", conn)
            user_list = df_all["username"].tolist() if not df_all.empty else []
        except Exception:
            user_list = []

        if user_list:
            with st.form("reset_password_form", clear_on_submit=True):
                col1, col2 = st.columns(2)

                with col1:
                    selected_user = st.selectbox("Select Account", user_list)
                    reset_pass = st.text_input("New Password*", type="password")

                with col2:
                    confirm_reset_pass = st.text_input("Confirm New Password*", type="password")

                submit_reset = st.form_submit_button("🔑 Reset Password", use_container_width=True)

                if submit_reset:
                    if not reset_pass:
                        st.error("⚠️ Please enter a new password.")
                    elif reset_pass != confirm_reset_pass:
                        st.error("⚠️ Passwords do not match.")
                    else:
                        try:
                            hashed_reset = hash_password(reset_pass)
                            with get_db() as conn:
                                cursor = conn.cursor()
                                cursor.execute(
                                    "UPDATE users SET password = ? WHERE username = ?",
                                    (hashed_reset, selected_user)
                                )
                                conn.commit()
                                st.success(f"✅ Password for **{selected_user}** updated successfully.")
                        except Exception as e:
                            st.error(f"Failed to reset password: {e}")
        else:
            st.info("No accounts available to update.")
