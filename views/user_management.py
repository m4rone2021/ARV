import pandas as pd
import streamlit as st

from database import hash_password, sb


def apply_orange_theme():
    st.markdown(
        """
        <style>
            :root {
                --primary-orange: #FF6F00;
                --hover-orange: #E65100;
                --light-orange-bg: #FFF3E0;
                --border-orange: #FFB74D;
            }
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
            button[data-baseweb="tab"]:hover {
                background-color: var(--light-orange-bg);
                color: var(--hover-orange) !important;
            }
            button[data-baseweb="tab"][aria-selected="true"] {
                background-color: var(--primary-orange) !important;
                color: #FFFFFF !important;
                border-color: var(--primary-orange) !important;
            }
            div[data-baseweb="tab-highlight"] {
                background-color: var(--hover-orange) !important;
            }
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
    apply_orange_theme()

    st.title("👤 User Management")
    st.caption("Manage site operator accounts, permissions, and security credentials.")

    if user_role != "Admin":
        st.error("⛔ Access Denied: You must have Administrator privileges to view or modify user credentials.")
        return

    # Flash notifications
    if "user_mgmt_flash" in st.session_state:
        msg_type, msg_text = st.session_state.pop("user_mgmt_flash")
        if msg_type == "success":
            st.success(msg_text)
        elif msg_type == "error":
            st.error(msg_text)

    tab_users, tab_add, tab_reset = st.tabs(
        ["📋 Registered Users", "➕ Create New User", "🔑 Reset Password"]
    )

    # ================================================================
    # TAB 1: REGISTERED USERS
    # ================================================================
    with tab_users:
        st.subheader("System Accounts")

        try:
            res = sb().table("users").select("id, username, role, is_active, created_at, last_login_at").order("username").execute()
            df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error fetching users: {e}")
            df = pd.DataFrame()

        if not df.empty:
            df_display = df.rename(columns={
                "id": "User ID",
                "username": "Username",
                "role": "Role / Access Level",
                "is_active": "Active",
                "created_at": "Created",
                "last_login_at": "Last Login",
            })
            st.dataframe(df_display, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("🗑️ Delete User Account")

            deletable_users = df[df["username"] != user_name]["username"].tolist()

            if deletable_users:
                with st.form("delete_user_form", clear_on_submit=True):
                    target_user = st.selectbox("Select Account to Delete", deletable_users)
                    submit_delete = st.form_submit_button("🗑️ Delete Account", use_container_width=True)

                    if submit_delete:
                        try:
                            # Get target's role
                            t_res = sb().table("users").select("id, role").eq("username", target_user).limit(1).execute()
                            if not t_res.data:
                                st.error(f"User {target_user} not found.")
                                st.stop()
                            target = t_res.data[0]
                            target_role = target["role"]

                            if target_role == "Admin":
                                a_res = sb().table("users").select("id", count="exact").eq("role", "Admin").execute()
                                if (a_res.count or 0) <= 1:
                                    st.error("⚠️ Action Blocked: Cannot delete the last remaining Administrator account.")
                                    st.stop()

                            sb().table("users").delete().eq("id", target["id"]).execute()

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

    # ================================================================
    # TAB 2: CREATE NEW USER
    # ================================================================
    with tab_add:
        st.subheader("Add Site Account")

        with st.form("create_user_form", clear_on_submit=True):
            new_username = st.text_input("Username*")
            new_role = st.selectbox("Role / Access Level*", ["User", "Admin"])
            new_password = st.text_input("Initial Password*", type="password")
            confirm_password = st.text_input("Confirm Password*", type="password")

            submit_create = st.form_submit_button("💾 Create User Account", use_container_width=True)

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
                        hashed = hash_password(new_password)
                        sb().table("users").insert({
                            "username": clean_user,
                            "password_hash": hashed,
                            "role": new_role,
                            "is_active": True,
                        }).execute()

                        st.session_state["user_mgmt_flash"] = (
                            "success",
                            f"✅ User account **{clean_user}** ({new_role}) created successfully.",
                        )
                        st.rerun()
                    except Exception as e:
                        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                            st.error(f"⚠️ Username **{clean_user}** already exists. Please choose a different username.")
                        else:
                            st.error(f"Failed to create account: {e}")

    # ================================================================
    # TAB 3: RESET PASSWORD
    # ================================================================
    with tab_reset:
        st.subheader("Password Override")

        try:
            res = sb().table("users").select("id, username").order("username").execute()
            users_df = pd.DataFrame(res.data or [])
            user_list = users_df["username"].tolist() if not users_df.empty else []
        except Exception:
            user_list = []

        if user_list:
            with st.form("reset_password_form", clear_on_submit=True):
                selected_user = st.selectbox("Select Account", user_list)
                reset_pass = st.text_input("New Password*", type="password")
                confirm_reset_pass = st.text_input("Confirm New Password*", type="password")

                submit_reset = st.form_submit_button("🔑 Reset Password", use_container_width=True)

                if submit_reset:
                    if not reset_pass:
                        st.error("⚠️ Please enter a new password.")
                    elif len(reset_pass) < 6:
                        st.error("⚠️ Password must be at least 6 characters long.")
                    elif reset_pass != confirm_reset_pass:
                        st.error("⚠️ Passwords do not match.")
                    else:
                        try:
                            hashed = hash_password(reset_pass)
                            sb().table("users").update(
                                {"password_hash": hashed}
                            ).eq("username", selected_user).execute()

                            st.session_state["user_mgmt_flash"] = (
                                "success",
                                f"✅ Password for **{selected_user}** updated successfully.",
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to reset password: {e}")
        else:
            st.info("No accounts available to update.")
