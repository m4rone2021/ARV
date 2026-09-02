import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# Initialize Database Connection
conn = sqlite3.connect("inventory.db", check_same_thread=False)
cursor = conn.cursor()

# --- DATABASE SETUP ---
cursor.execute("""
CREATE TABLE IF NOT EXISTS master_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT UNIQUE,
    category TEXT,
    unit TEXT,
    current_stock REAL,
    min_threshold REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    item_name TEXT,
    type TEXT,
    quantity REAL,
    user_role TEXT,
    remarks TEXT
)
""")

# User Management Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT
)
""")

# Seed Default Admin Account if no users exist
cursor.execute("SELECT COUNT(*) FROM users")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                   ("admin", "admin123", "Head Office"))
conn.commit()


# --- SESSION STATE INITIALIZATION ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
if "username" not in st.session_state:
    st.session_state["username"] = None
if "user_role" not in st.session_state:
    st.session_state["user_role"] = None


# --- LOGIN SCREEN ---
if not st.session_state["logged_in"]:
    st.title("🏗️ Construction Site Inventory")
    st.subheader("Sign In")

    input_username = st.text_input("Username")
    input_password = st.text_input("Password", type="password")

    if st.button("Log In"):
        user = cursor.execute("SELECT username, role FROM users WHERE username = ? AND password = ?", 
                              (input_username.strip(), input_password.strip())).fetchone()
        if user:
            st.session_state["logged_in"] = True
            st.session_state["username"] = user[0]
            st.session_state["user_role"] = user[1]
            st.success(f"Welcome back, {user[0]}!")
            st.rerun()
        else:
            st.error("Invalid username or password.")

# --- MAIN APPLICATION (LOGGED IN) ---
else:
    # Sidebar Profile & Logout
    st.sidebar.markdown(f"**Logged in as:** `{st.session_state['username']}`")
    st.sidebar.markdown(f"**Role:** `{st.session_state['user_role']}`")
    
    if st.sidebar.button("Log Out"):
        st.session_state["logged_in"] = False
        st.session_state["username"] = None
        st.session_state["user_role"] = None
        st.rerun()

    st.title("🏗️ Construction Site Inventory System")

    # Dynamic Tabs Based on Role
    if st.session_state["user_role"] == "Materials Supervisor":
        tab1, tab2, tab3 = st.tabs(["📋 Current Inventory", "+ Stock In", "- Stock Out"])
    else:  # Head Office Admin
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📋 Current Inventory", 
            "+ Stock In", 
            "- Stock Out", 
            "➕ Add Master Item", 
            "📜 Audit Log",
            "👤 Manage Users"
        ])

    # Tab 1: Current Inventory
    with tab1:
        st.subheader("Inventory Status")
        df_items = pd.read_sql_query("SELECT item_name, category, unit, current_stock, min_threshold FROM master_items", conn)
        
        if not df_items.empty:
            def highlight_low_stock(row):
                return ['background-color: #ffcccc' if row['current_stock'] <= row['min_threshold'] else '' for _ in row]

            st.dataframe(df_items.style.apply(highlight_low_stock, axis=1), use_container_width=True)
        else:
            st.info("No items found in Master Inventory.")

    # Tab 2: Stock In
    with tab2:
        st.subheader("Log Stock Delivery (Receiving)")
        items = [row[0] for row in cursor.execute("SELECT item_name FROM master_items").fetchall()]
        if items:
            item_selected = st.selectbox("Select Item to Receive", items, key="in_item")
            qty_in = st.number_input("Quantity Received", min_value=0.1, step=1.0, key="in_qty")
            remarks_in = st.text_input("Delivery Receipt / Remarks", key="in_rem")

            if st.button("Submit Stock In"):
                cursor.execute("UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?", (qty_in, item_selected))
                cursor.execute("INSERT INTO transactions (timestamp, item_name, type, quantity, user_role, remarks) VALUES (?, ?, ?, ?, ?, ?)",
                               (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item_selected, "IN", qty_in, st.session_state["username"], remarks_in))
                conn.commit()
                st.success(f"Added {qty_in} to {item_selected}")
                st.rerun()
        else:
            st.warning("Please add items to Master Inventory first.")

    # Tab 3: Stock Out
    with tab3:
        st.subheader("Log Stock Issuance")
        items = [row[0] for row in cursor.execute("SELECT item_name FROM master_items").fetchall()]
        if items:
            item_selected = st.selectbox("Select Item to Issue", items, key="out_item")
            qty_out = st.number_input("Quantity Issued", min_value=0.1, step=1.0, key="out_qty")
            remarks_out = st.text_input("Issued To / Equipment ID", key="out_rem")

            if st.button("Submit Stock Out"):
                curr_stock = cursor.execute("SELECT current_stock FROM master_items WHERE item_name = ?", (item_selected,)).fetchone()[0]
                if qty_out > curr_stock:
                    st.error("Insufficient stock!")
                else:
                    cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", (qty_out, item_selected))
                    cursor.execute("INSERT INTO transactions (timestamp, item_name, type, quantity, user_role, remarks) VALUES (?, ?, ?, ?, ?, ?)",
                                   (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item_selected, "OUT", qty_out, st.session_state["username"], remarks_out))
                    conn.commit()
                    st.success(f"Issued {qty_out} of {item_selected}")
                    st.rerun()

    # Head Office Only Tabs
    if st.session_state["user_role"] == "Head Office":
        # Tab 4: Add Master Item
        with tab4:
            st.subheader("Add New Master Item")
            new_name = st.text_input("Item Name")
            new_cat = st.selectbox("Category", ["1. Fuel & Oils", "2. Construction Materials", "3. Steel / Rebar", "4. Consumables"])
            new_unit = st.text_input("Unit of Measure (e.g., Liters, Bags, Pcs)")
            init_stock = st.number_input("Initial Stock", min_value=0.0, step=1.0)
            min_thresh = st.number_input("Minimum Alert Threshold", min_value=0.0, step=1.0)

            if st.button("Save New Item"):
                if new_name:
                    try:
                        cursor.execute("INSERT INTO master_items (item_name, category, unit, current_stock, min_threshold) VALUES (?, ?, ?, ?, ?)",
                                       (new_name, new_cat, new_unit, init_stock, min_thresh))
                        conn.commit()
                        st.success(f"Added '{new_name}' to inventory master!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Item name already exists.")
                else:
                    st.error("Item name cannot be empty.")

        # Tab 5: Audit Log
        with tab5:
            st.subheader("Transaction Audit Log")
            df_tx = pd.read_sql_query("SELECT * FROM transactions ORDER BY id DESC", conn)
            st.dataframe(df_tx, use_container_width=True)

        # Tab 6: User Management (Create New Users)
        with tab6:
            st.subheader("Create New System User")
            
            with st.form("create_user_form"):
                new_username = st.text_input("New Username")
                new_password = st.text_input("Assign Password", type="password")
                assigned_role = st.selectbox("Assign User Role", ["Materials Supervisor", "Head Office"])
                submit_user = st.form_submit_button("Create Account")

            if submit_user:
                if new_username.strip() and new_password.strip():
                    try:
                        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                                       (new_username.strip(), new_password.strip(), assigned_role))
                        conn.commit()
                        st.success(f"Successfully created account for '{new_username}' as {assigned_role}!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Username already exists. Please choose a different one.")
                else:
                    st.error("Username and password fields cannot be blank.")

            st.markdown("---")
            st.subheader("Existing Accounts")
            df_users = pd.read_sql_query("SELECT id, username, role FROM users", conn)
            st.dataframe(df_users, use_container_width=True)
