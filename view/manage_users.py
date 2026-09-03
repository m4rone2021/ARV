# views/manage_users.py
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db, hash_password

def render_manage_users():
    st.title("👤 User Account Management")
    st.caption("Register new team accounts, set user access roles, and view current platform accounts.")

    tab_create, tab_list = st.tabs(["➕ Create New User", "📋 Existing Users List"])

    # TAB 1: CREATE NEW USER
    with tab_create:
        st.subheader("Register New User Account")
        with st.form("create_user_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                new_user = st.text_input("Username", placeholder="e.g., jdoe")
                new_pass = st.text_input("Password", type="password")
            
            with col2:
                new_role = st.selectbox(
                    "User Role", 
                    ["Materials Supervisor", "Head Office"],
                    help="Head Office accounts have admin access to manage users."
                )

            submit_user = st.form_submit_button("👤 Register User Account")

            if submit_user:
                if not new_user.strip() or not new_pass.strip():
                    st.error("Please supply both a valid username and password.")
                else:
                    try:
                        hashed = hash_password(new_pass.strip())
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                                (new_user.strip(), hashed, new_role)
                            )
                            conn.commit()
                            st.toast(f"✅ Registered user '{new_user.strip()}'!", icon="👤")
                            st.success(f"User account **{new_user.strip()}** successfully created!")
                            st.rerun()
                    except sqlite3.IntegrityError:
                        st.error(f"❌ Username '{new_user.strip()}' is already taken. Please choose another.")
                    except sqlite3.OperationalError:
                        st.error("Database is currently busy. Please try again.")

    # TAB 2: EXISTING USERS LIST
    with tab_list:
        st.subheader("Registered System Users")
        with get_db() as conn:
            df_users = pd.read_sql_query("SELECT id, username, role FROM users ORDER BY id ASC", conn)

        if not df_users.empty:
            display_users = df_users.rename(columns={
                "id": "User ID",
                "username": "Username",
                "role": "Assigned Role"
            })
            st.dataframe(display_users, use_container_width=True, hide_index=True)
        else:
            st.info("No user records found.")
