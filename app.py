import streamlit as st
import sqlite3
import pandas as pd
import os
import bcrypt
from datetime import datetime, time
from contextlib import contextmanager

# ==========================================
# 1. CONSTANTS & DATABASE CONFIGURATION
# ==========================================
DB_FILE = "inventory_system.db"
UPLOAD_DIR = "uploaded_proofs"

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

st.set_page_config(
    page_title="Site Materials & Inventory Ledger",
    page_icon="📦",
    layout="wide"
)

@contextmanager
def get_db():
    """Context manager for thread-safe SQLite database connections with timeout."""
    conn = sqlite3.connect(DB_FILE, timeout=20.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# ==========================================
# 2. HELPER & SECURITY FUNCTIONS
# ==========================================
def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, stored_password: str) -> bool:
    """Check plaintext password against a stored bcrypt hash with fallback for legacy plain text."""
    if not stored_password:
        return False
        
    # Check if stored string has standard bcrypt prefix ($2a$, $2b$, or $2y$)
    if stored_password.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(plain_password.encode('utf-8'), stored_password.encode('utf-8'))
        except (ValueError, TypeError):
            return False
            
    # Fallback for old plain-text entries in database
    return plain_password == stored_password

def init_db():
    """Initialize database tables, pragmas, and default seed data."""
    with get_db() as conn:
        cursor = conn.cursor()
        # Enable Write-Ahead Logging for better concurrent read/write handling
        cursor.execute("PRAGMA journal_mode=WAL;")
        
        # Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
        """)
        
        # Master Items Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS master_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                unit TEXT NOT NULL,
                current_stock REAL DEFAULT 0,
                min_threshold REAL DEFAULT 0
            )
        """)

        # Transactions Audit Ledger Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                item_name TEXT NOT NULL,
                type TEXT NOT NULL, -- 'IN', 'OUT', or 'ADJUSTMENT'
                quantity REAL NOT NULL,
                user_name TEXT NOT NULL,
                user_role TEXT NOT NULL,
                driver_details TEXT,
                issued_to TEXT,
                project_name TEXT,
                purpose TEXT,
                remarks TEXT,
                photo_path TEXT,
                edit_status TEXT DEFAULT 'NORMAL'
            )
        """)

        # Reminders Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL,
                title TEXT NOT NULL,
                due_date TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING',
                timestamp TEXT NOT NULL
            )
        """)

        # Schedules Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL,
                title TEXT NOT NULL,
                event_date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                location_details TEXT,
                notes TEXT,
                timestamp TEXT NOT NULL
            )
        """)
        
        # Seed default admin and supervisor accounts if table is empty
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            hashed_admin = hash_password("admin123")
            hashed_super = hash_password("super123")
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ('admin', hashed_admin, 'Head Office'))
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ('supervisor', hashed_super, 'Materials Supervisor'))
        
        conn.commit()

def login_user(username, password):
    """Verify user login and auto-upgrade legacy plain-text passwords to bcrypt hashes."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, password, role FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        
        if user and verify_password(password, user["password"]):
            # Auto-migrate plain text password to bcrypt hash if needed
            if not user["password"].startswith(("$2a$", "$2b$", "$2y$")):
                new_hash = hash_password(password)
                cursor.execute("UPDATE users SET password = ? WHERE username = ?", (new_hash, username))
                conn.commit()
                
            return {"username": user["username"], "role": user["role"]}
            
    return None

# Run initialization
init_db()

# ==========================================
# 3. AUTHENTICATION & SESSION MANAGEMENT
# ==========================================
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

# ==========================================
# 4. NAVIGATION & SIDEBAR
# ==========================================
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

# ==========================================
# 5. MAIN APPLICATION CONTROLLERS
# ==========================================

# --- MENU 1: DASHBOARD OVERVIEW ---
if selected_menu == "📊 Dashboard Overview":
    st.title("📊 Inventory Overview Dashboard")
    
    with get_db() as conn:
        df_items = pd.read_sql_query("SELECT * FROM master_items ORDER BY category ASC, item_name ASC", conn)
        df_tx = pd.read_sql_query("SELECT * FROM transactions ORDER BY id DESC LIMIT 10", conn)

    # Top High-Level Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Master Items", len(df_items))
    
    low_stock_cnt = len(df_items[df_items['current_stock'] <= df_items['min_threshold']]) if not df_items.empty else 0
    col2.metric("Low Stock Alerts", low_stock_cnt, delta_color="inverse")
    
    total_tx = len(df_tx) if not df_tx.empty else 0
    col3.metric("Recent Transactions Logged", total_tx)

    st.divider()
    st.subheader("📦 Available Inventory & Physical Audit Balance")

    if df_items.empty:
        st.info("No master items configured yet. Go to 'Manage Master Items' to add items.")
    else:
        # Group items by Category
        categories = df_items['category'].unique()

        for cat in categories:
            # Bold Category Header
            st.markdown(f"### **{cat.upper()}**")
            
            cat_df = df_items[df_items['category'] == cat].copy()
            
            display_rows = []
            for _, row in cat_df.iterrows():
                stock = row['current_stock']
                min_t = row['min_threshold']
                
                # Determine stock status & physical inventory variance flag
                if stock <= min_t:
                    status = "⚠️ Lacking / Low Stock"
                else:
                    status = "✅ Normal / Surplus Available"
                
                display_rows.append({
                    "Item Name": row['item_name'],
                    "Unit": row['unit'],
                    "Current Actual Stock": f"{stock:,.2f}".rstrip('0').rstrip('.'),
                    "Min Threshold": f"{min_t:,.2f}".rstrip('0').rstrip('.'),
                    "Physical Audit Variance / Status": status
                })
            
            # Present category items in a clean table
            st.dataframe(
                pd.DataFrame(display_rows), 
                use_container_width=True, 
                hide_index=True
            )
            st.markdown("<br>", unsafe_allow_html=True)

    st.divider()

    # Recent Transactions Activity Stream
    st.subheader("⏱️ Recent Activity (Stock IN / OUT / Adjustments)")
    if not df_tx.empty:
        recent_display = df_tx[['timestamp', 'item_name', 'type', 'quantity', 'user_name', 'project_name', 'remarks', 'edit_status']].copy()
        recent_display.columns = ['Timestamp', 'Item Name', 'Type', 'Qty', 'Logged By', 'Project / Destination', 'Remarks / Details', 'Status']
        
        st.dataframe(recent_display, use_container_width=True, hide_index=True)
    else:
        st.info("No transaction activity recorded yet.")

# --- MENU 2: STOCK RECEIPT (IN) ---
elif selected_menu == "📥 Stock Receipt (IN)":
    st.subheader("📥 Receive Material Deliveries (IN)")
    
    with get_db() as conn:
        df_items = pd.read_sql_query("SELECT item_name FROM master_items ORDER BY item_name ASC", conn)

    if df_items.empty:
        st.warning("No master items found. Please add items in 'Manage Master Items' first.")
    else:
        item_list = df_items['item_name'].tolist()
        
        with st.form("stock_in_form", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            item_selected = col_a.selectbox("Select Item", item_list)
            qty_in = col_b.number_input("Quantity Received", min_value=0.1, step=1.0)
            
            driver_info = st.text_input("Driver & Vehicle Details (e.g., Plate #, Driver Name)")
            project_name = st.text_input("Project / Site Destination")
            remarks = st.text_area("Delivery Remarks / DR Number")
            uploaded_file = st.file_uploader("Upload Delivery Receipt / Proof Photo", type=["png", "jpg", "jpeg"])
            
            submit_in = st.form_submit_button("Log Stock Receipt")
            
            if submit_in:
                photo_path = ""
                if uploaded_file is not None:
                    file_ext = os.path.splitext(uploaded_file.name)[1]
                    filename = f"IN_{datetime.now().strftime('%Y%m%d_%H%M%S')}{file_ext}"
                    photo_path = os.path.join(UPLOAD_DIR, filename)
                    with open(photo_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("BEGIN IMMEDIATE")
                        
                        # Update Stock
                        cursor.execute("UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?", (qty_in, item_selected))
                        
                        # Log Transaction
                        cursor.execute("""
                            INSERT INTO transactions (
                                timestamp, item_name, type, quantity, user_name, user_role, 
                                driver_details, project_name, remarks, photo_path
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            item_selected, "IN", qty_in, user_name, user_role,
                            driver_info, project_name, remarks, photo_path
                        ))
                        
                        conn.commit()
                        st.success(f"Successfully received {qty_in} units of {item_selected}!")
                        st.rerun()
                except sqlite3.OperationalError:
                    st.error("Database is currently busy. Please try submitting again.")

# --- MENU 3: MATERIAL ISSUE (OUT) ---
elif selected_menu == "📤 Material Issue (OUT)":
    st.subheader("📤 Issue Materials to Site (OUT)")
    
    with get_db() as conn:
        df_items = pd.read_sql_query("SELECT item_name, current_stock, unit FROM master_items ORDER BY item_name ASC", conn)

    if df_items.empty:
        st.warning("No master items found.")
    else:
        item_list = df_items['item_name'].tolist()
        
        with st.form("stock_out_form", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            item_selected = col_a.selectbox("Select Item to Issue", item_list)
            qty_out = col_b.number_input("Quantity Issued", min_value=0.1, step=1.0)
            
            issued_to = st.text_input("Issued To (Subcontractor / Personnel)")
            driver_out = st.text_input("Hauler / Transport Details")
            project_name = st.text_input("Project / Site Location")
            purpose = st.text_area("Purpose / Usage Details")
            
            submit_out = st.form_submit_button("Issue Material")
            
            if submit_out:
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("BEGIN IMMEDIATE")
                        
                        cursor.execute("SELECT current_stock FROM master_items WHERE item_name = ?", (item_selected,))
                        row = cursor.fetchone()
                        
                        if not row:
                            st.error("Selected item not found.")
                        elif qty_out > row['current_stock']:
                            st.error(f"Insufficient stock! Available balance: {row['current_stock']}")
                        else:
                            cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", (qty_out, item_selected))
                            
                            cursor.execute("""
                                INSERT INTO transactions (
                                    timestamp, item_name, type, quantity, user_name, user_role, 
                                    driver_details, issued_to, project_name, purpose
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                item_selected, "OUT", qty_out, user_name, user_role,
                                driver_out, issued_to, project_name, purpose
                            ))
                            
                            conn.commit()
                            st.success(f"Successfully issued {qty_out} units of {item_selected}!")
                            st.rerun()
                except sqlite3.OperationalError:
                    st.error("Database is currently busy. Please try submitting again.")

# --- MENU 4: LOW STOCK ALERTS ---
elif selected_menu == "⚠️ Low Stock Alerts":
    st.subheader("⚠️ Low Stock Alert Center")
    with get_db() as conn:
        df_low = pd.read_sql_query("SELECT id, item_name, category, unit, current_stock, min_threshold FROM master_items WHERE current_stock <= min_threshold", conn)
    
    if not df_low.empty:
        st.error(f"Attention: {len(df_low)} item(s) are at or below minimum threshold levels!")
        st.dataframe(df_low, use_container_width=True)
    else:
        st.success("All inventory items are currently above threshold levels.")

# --- MENU 5: EDIT/VOID TRANSACTIONS ---
elif selected_menu == "📝 Edit/Void Transactions":
    st.subheader("📝 Edit or Void Previous Transactions")
    st.info("Reversing or modifying transactions automatically adjusts inventory balances.")

    with get_db() as conn:
        df_tx = pd.read_sql_query("SELECT id, timestamp, item_name, type, quantity, user_name, edit_status FROM transactions WHERE edit_status = 'NORMAL' ORDER BY id DESC LIMIT 50", conn)

    if not df_tx.empty:
        sel_tx_id = st.selectbox("Select Transaction ID to Void/Reverse", df_tx['id'].tolist())
        tx_row = df_tx[df_tx['id'] == sel_tx_id].iloc[0]
        st.write(f"**Transaction Details:** #{tx_row['id']} | {tx_row['timestamp']} | {tx_row['item_name']} | Type: `{tx_row['type']}` | Qty: `{tx_row['quantity']}`")
        
        reason = st.text_input("Reason for Voiding Transaction")
        
        if st.button("Void Transaction"):
            if not reason.strip():
                st.error("A valid reason must be provided to void a transaction.")
            else:
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("BEGIN IMMEDIATE")
                        
                        # Reverse Stock impact
                        if tx_row['type'] == 'IN':
                            cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", (tx_row['quantity'], tx_row['item_name']))
                        elif tx_row['type'] == 'OUT':
                            cursor.execute("UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?", (tx_row['quantity'], tx_row['item_name']))
                        
                        # Mark transaction voided
                        cursor.execute("UPDATE transactions SET edit_status = ? WHERE id = ?", (f"VOIDED: {reason}", sel_tx_id))
                        
                        # Log adjustment audit record
                        cursor.execute("""
                            INSERT INTO transactions (
                                timestamp, item_name, type, quantity, user_name, user_role, remarks
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            tx_row['item_name'], "ADJUSTMENT", 
                            (-tx_row['quantity'] if tx_row['type'] == 'IN' else tx_row['quantity']),
                            user_name, user_role, f"Reversal of TX #{sel_tx_id}: {reason}"
                        ))
                        
                        conn.commit()
                        st.success(f"Transaction #{sel_tx_id} successfully voided.")
                        st.rerun()
                except sqlite3.OperationalError:
                    st.error("Database is busy. Please try again.")
    else:
        st.info("No eligible active transactions found.")

# --- MENU 6: MANAGE MASTER ITEMS ---
elif selected_menu == "➕ Manage Master Items":
    st.subheader("➕ Master Catalog Management")
    
    tab1, tab2 = st.tabs(["Add New Master Item", "Modify Item Details / Adjust Stock"])
    
    with tab1:
        with st.form("add_item_form", clear_on_submit=True):
            i_name = st.text_input("Item Name (e.g. Deformed Bar 12mm)")
            i_cat = st.text_input("Category (e.g. Steel, Cement, Aggregate)")
            i_unit = st.text_input("Unit of Measure (e.g. pcs, bags, cu.m)")
            i_stock = st.number_input("Initial Opening Stock", min_value=0.0, step=1.0)
            i_thresh = st.number_input("Min Alert Threshold", min_value=0.0, step=1.0)
            
            if st.form_submit_button("Create Master Item"):
                if i_name and i_cat and i_unit:
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO master_items (item_name, category, unit, current_stock, min_threshold)
                                VALUES (?, ?, ?, ?, ?)
                            """, (i_name.strip(), i_cat.strip(), i_unit.strip(), i_stock, i_thresh))
                            conn.commit()
                            st.success(f"Item '{i_name}' added to master catalog!")
                            st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("An item with this name already exists in the catalog.")
                else:
                    st.error("Please complete all required fields.")

    with tab2:
        with get_db() as conn:
            df_m = pd.read_sql_query("SELECT id, item_name, category, unit, current_stock, min_threshold FROM master_items", conn)
        
        if not df_m.empty:
            selected_mod_id = st.selectbox(
                "Select Item to Update", 
                df_m['id'].tolist(), 
                format_func=lambda x: df_m[df_m['id']==x]['item_name'].values[0]
            )
            m_row = df_m[df_m['id'] == selected_mod_id].iloc[0]

            st.markdown("##### 📝 Update Item Details (Metadata Only)")
            with st.form("mod_item_form"):
                m_name = st.text_input("Item Name", value=m_row['item_name'])
                m_cat = st.text_input("Category", value=m_row['category'])
                m_unit = st.text_input("Unit", value=m_row['unit'])
                m_thresh = st.number_input("Min Alert Threshold", value=float(m_row['min_threshold']))

                if st.form_submit_button("Update Item Details"):
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE master_items 
                            SET item_name = ?, category = ?, unit = ?, min_threshold = ?
                            WHERE id = ?
                        """, (m_name.strip(), m_cat.strip(), m_unit.strip(), m_thresh, selected_mod_id))
                        conn.commit()
                        st.success(f"Item '{m_name}' metadata updated successfully!")
                        st.rerun()

            st.divider()

            st.markdown("##### ⚖️ Manual Stock Adjustment (Logged Audit Transaction)")
            st.info(f"Current Recorded Stock Balance: **{m_row['current_stock']} {m_row['unit']}**")

            with st.form("adjust_stock_form", clear_on_submit=True):
                new_stock_val = st.number_input("New Actual Stock Quantity", min_value=0.0, value=float(m_row['current_stock']), step=1.0)
                adj_reason = st.text_area("Reason for Stock Adjustment", placeholder="e.g., Damaged inventory, physical count discrepancy")

                if st.form_submit_button("Apply Stock Adjustment"):
                    diff = new_stock_val - m_row['current_stock']

                    if diff == 0:
                        st.warning("No stock change detected.")
                    elif not adj_reason.strip():
                        st.error("You must provide a reason for adjusting stock.")
                    else:
                        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("BEGIN IMMEDIATE")
                            cursor.execute("UPDATE master_items SET current_stock = ? WHERE id = ?", (new_stock_val, selected_mod_id))
                            cursor.execute("""
                                INSERT INTO transactions (
                                    timestamp, item_name, type, quantity, user_name, user_role, remarks
                                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                ts, m_row['item_name'], "ADJUSTMENT", diff, 
                                user_name, user_role, f"Manual Adjustment: {adj_reason.strip()}"
                            ))
                            conn.commit()
                            st.success(f"Stock for '{m_row['item_name']}' adjusted by {diff:+.2f}. Logged to audit trail.")
                            st.rerun()

# --- MENU 7: MASTER AUDIT LOG ---
elif selected_menu == "📜 Master Audit Log":
    st.subheader("📜 Complete Site Transaction Audit Log")

    with get_db() as conn:
        df_master_log = pd.read_sql_query("""
            SELECT id, timestamp, item_name, type, quantity, user_name, user_role, 
                   driver_details, issued_to, project_name, purpose, remarks, edit_status, photo_path
            FROM transactions 
            ORDER BY id DESC
        """, conn)

    if not df_master_log.empty:
        st.dataframe(df_master_log, use_container_width=True)

        st.markdown("#### 📷 View Delivery Proof Photo")
        photo_logs = df_master_log[df_master_log['photo_path'].notnull() & (df_master_log['photo_path'] != '')]
        
        if not photo_logs.empty:
            sel_p_id = st.selectbox("Select Transaction ID with Photo", photo_logs['id'].tolist())
            p_path = photo_logs[photo_logs['id'] == sel_p_id]['photo_path'].values[0]
            
            if os.path.exists(p_path):
                st.image(p_path, caption=f"Delivery Proof for Transaction #{sel_p_id}", use_column_width=True)
            else:
                st.warning("⚠️ Photo record exists in database, but image file was not found on disk.")
        else:
            st.info("No delivery proof photos attached to logs yet.")
    else:
        st.info("No transaction history recorded yet.")

# --- MENU 8: MANAGE USERS (HEAD OFFICE ONLY) ---
elif selected_menu == "👤 Manage Users":
    st.subheader("👤 User Management & Role Access Control")
    
    tab_users, tab_add_user = st.tabs(["User Directory", "Add New User"])
    
    with tab_users:
        with get_db() as conn:
            df_users = pd.read_sql_query("SELECT id, username, role FROM users", conn)
        st.dataframe(df_users, use_container_width=True)
        
    with tab_add_user:
        with st.form("add_user_form", clear_on_submit=True):
            new_username = st.text_input("Username")
            new_password = st.text_input("Password", type="password")
            new_role = st.selectbox("Assign Role", ["Materials Supervisor", "Head Office"])
            
            if st.form_submit_button("Create User Account"):
                if new_username and new_password:
                    try:
                        hashed_pwd = hash_password(new_password.strip())
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                                           (new_username.strip(), hashed_pwd, new_role))
                            conn.commit()
                            st.success(f"User account '{new_username}' created successfully!")
                            st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Username already exists. Please choose a unique username.")
                else:
                    st.error("Please fill in all required fields.")

# --- MENU 9: REMINDERS ---
elif selected_menu == "⏰ Reminders":
    st.subheader("⏰ Site Reminders & Tasks")
    
    with st.form("add_reminder_form", clear_on_submit=True):
        col_t, col_d, col_p = st.columns([2, 1, 1])
        r_title = col_t.text_input("Task / Reminder Title")
        r_due = col_d.date_input("Due Date", datetime.now())
        r_priority = col_p.selectbox("Priority", ["Low", "Medium", "High"])
        
        if st.form_submit_button("Add Reminder"):
            if r_title:
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO reminders (user_name, title, due_date, priority, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                    """, (user_name, r_title, r_due.strftime("%Y-%m-%d"), r_priority, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    st.success("Reminder created!")
                    st.rerun()

    st.markdown("#### Pending Reminders")
    with get_db() as conn:
        df_rem = pd.read_sql_query("SELECT id, title, due_date, priority, status FROM reminders WHERE user_name = ? AND status = 'PENDING' ORDER BY due_date ASC", conn, params=(user_name,))
    
    if not df_rem.empty:
        st.dataframe(df_rem, use_container_width=True)
        rem_to_complete = st.selectbox("Select Task ID to Mark Complete", df_rem['id'].tolist())
        if st.button("Mark Task Completed"):
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE reminders SET status = 'COMPLETED' WHERE id = ?", (rem_to_complete,))
                conn.commit()
                st.success("Task completed!")
                st.rerun()
    else:
        st.info("No pending reminders.")

# --- MENU 10: SCHEDULE ---
elif selected_menu == "📅 Schedule":
    st.subheader("📅 Site Delivery & Event Schedules")
    
    with st.form("add_schedule_form", clear_on_submit=True):
        s_title = st.text_input("Event / Delivery Title")
        c_d, c_s, c_e = st.columns(3)
        s_date = c_d.date_input("Event Date", datetime.now())
        s_start = c_s.time_input("Start Time", time(8, 0))
        s_end = c_e.time_input("End Time", time(17, 0))
        s_loc = st.text_input("Location / Site Area")
        s_notes = st.text_area("Notes / Special Instructions")
        
        if st.form_submit_button("Schedule Event"):
            if s_title:
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO schedules (user_name, title, event_date, start_time, end_time, location_details, notes, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (user_name, s_title, s_date.strftime("%Y-%m-%d"), s_start.strftime("%H:%M"), s_end.strftime("%H:%M"), s_loc, s_notes, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    st.success("Event scheduled successfully!")
                    st.rerun()

    with get_db() as conn:
        df_sched = pd.read_sql_query("SELECT title, event_date, start_time, end_time, location_details, notes FROM schedules ORDER BY event_date ASC, start_time ASC", conn)
    
    if not df_sched.empty:
        st.dataframe(df_sched, use_container_width=True)
    else:
        st.info("No scheduled events found.")
