import streamlit as st
import sqlite3
import pandas as pd
import os
import bcrypt
from datetime import datetime, date, time
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
        
    if stored_password.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            return bcrypt.checkpw(plain_password.encode('utf-8'), stored_password.encode('utf-8'))
        except (ValueError, TypeError):
            return False
            
    return plain_password == stored_password

def init_db():
    """Initialize database tables, pragmas, and default seed data."""
    with get_db() as conn:
        cursor = conn.cursor()
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
        
        # Seed default admin and supervisor accounts if empty
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            hashed_admin = hash_password("admin123")
            hashed_super = hash_password("super123")
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ('admin', hashed_admin, 'Head Office'))
            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ('supervisor', hashed_super, 'Materials Supervisor'))
        
        conn.commit()

def login_user(username, password):
    """Verify user login and auto-upgrade legacy passwords."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, password, role FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        
        if user and verify_password(password, user["password"]):
            if not user["password"].startswith(("$2a$", "$2b$", "$2y$")):
                new_hash = hash_password(password)
                cursor.execute("UPDATE users SET password = ? WHERE username = ?", (new_hash, username))
                conn.commit()
                
            return {"username": user["username"], "role": user["role"]}
            
    return None

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
        categories = df_items['category'].unique()

        for cat in categories:
            st.markdown(f"### **{cat.upper()}**")
            cat_df = df_items[df_items['category'] == cat].copy()
            
            display_rows = []
            for _, row in cat_df.iterrows():
                stock = row['current_stock']
                min_t = row['min_threshold']
                
                status = "⚠️ Lacking / Low Stock" if stock <= min_t else "✅ Normal / Surplus Available"
                
                display_rows.append({
                    "Item Name": row['item_name'],
                    "Unit": row['unit'],
                    "Current Actual Stock": f"{stock:,.2f}".rstrip('0').rstrip('.'),
                    "Min Threshold": f"{min_t:,.2f}".rstrip('0').rstrip('.'),
                    "Physical Audit Variance / Status": status
                })
            
            st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
            st.markdown("<br>", unsafe_allow_html=True)

    st.divider()
    st.subheader("⏱️ Recent Activity (Stock IN / OUT / Adjustments)")
    if not df_tx.empty:
        recent_display = df_tx[['timestamp', 'item_name', 'type', 'quantity', 'user_name', 'project_name', 'remarks', 'edit_status']].copy()
        recent_display.columns = ['Timestamp', 'Item Name', 'Type', 'Qty', 'Logged By', 'Project / Destination', 'Remarks / Details', 'Status']
        st.dataframe(recent_display, use_container_width=True, hide_index=True)
    else:
        st.info("No transaction activity recorded yet.")

# --- MENU 2: STOCK RECEIPT (IN) ---
elif selected_menu == "📥 Stock Receipt (IN)":
    st.title("📥 Receive Material Deliveries (Stock IN)")
    st.caption("Log incoming material deliveries to update stock inventory and record proof of receipt.")
    
    if "is_submitting_in" not in st.session_state:
        st.session_state.is_submitting_in = False

    with get_db() as conn:
        df_items = pd.read_sql_query("SELECT id, item_name, category, unit, current_stock FROM master_items ORDER BY category ASC, item_name ASC", conn)

    if df_items.empty:
        st.warning("⚠️ No master items found in database. Please add items under 'Manage Master Items' first.")
    else:
        item_dict = {row['item_name']: row for _, row in df_items.iterrows()}
        item_list = list(item_dict.keys())
        
        st.subheader("📋 Delivery Log Form")
        
        with st.form("stock_in_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                item_selected = st.selectbox("Select Material / Item", item_list, key="in_item_select")
                selected_item_info = item_dict[item_selected]
                unit_label = selected_item_info['unit']
                current_bal = selected_item_info['current_stock']
                
                qty_in = st.number_input(
                    f"Quantity Received ({unit_label})", 
                    value=None, 
                    min_value=0.01, 
                    step=1.0, 
                    format="%.2f", 
                    placeholder="0.00", 
                    key="in_qty"
                )
                dr_number = st.text_input("Delivery Receipt (DR) / Invoice No.", placeholder="e.g., DR-2026-0891", key="in_dr")
                supplier_name = st.text_input("Supplier / Vendor Name", placeholder="e.g., Holcim Concrete / SteelCorp", key="in_supplier")

            with col2:
                st.info(f"📌 **Current Recorded Balance:** `{current_bal:,.2f} {unit_label}`\n\n**Category:** `{selected_item_info['category']}`")
                driver_info = st.text_input("Driver Name & Vehicle Plate No.", placeholder="e.g., Juan Dela Cruz (ABC-1234)", key="in_driver")
                project_name = st.text_input("Project Site / Unloading Location", placeholder="e.g., Sector 3 - Ground Floor", key="in_project")
                remarks = st.text_area("Delivery Remarks / Quality Notes", placeholder="e.g., Delivered in good condition", key="in_remarks")

            st.divider()
            uploaded_file = st.file_uploader("📷 Upload Delivery Receipt or Photo Proof (PNG, JPG, JPEG)", type=["png", "jpg", "jpeg"], key="in_file")
            
            submit_in = st.form_submit_button("📦 Confirm & Record Material Receipt", disabled=st.session_state.is_submitting_in)
            
            if submit_in and not st.session_state.is_submitting_in:
                if qty_in is None or qty_in <= 0:
                    st.error("Please enter a valid quantity received.")
                elif not dr_number.strip():
                    st.error("Please enter a valid Delivery Receipt (DR) or Invoice number for tracking.")
                else:
                    st.session_state.is_submitting_in = True
                    
                    try:
                        photo_path = ""
                        if uploaded_file is not None:
                            file_ext = os.path.splitext(uploaded_file.name)[1]
                            filename = f"IN_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{dr_number.strip()}{file_ext}"
                            photo_path = os.path.join(UPLOAD_DIR, filename)
                            with open(photo_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())

                        full_remarks = f"DR/Inv: {dr_number.strip()} | Supplier: {supplier_name.strip()}"
                        if remarks.strip():
                            full_remarks += f" | Notes: {remarks.strip()}"

                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("BEGIN IMMEDIATE")
                            cursor.execute("UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?", (qty_in, item_selected))
                            cursor.execute("""
                                INSERT INTO transactions (
                                    timestamp, item_name, type, quantity, user_name, user_role, 
                                    driver_details, project_name, remarks, photo_path
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                item_selected, "IN", qty_in, user_name, user_role,
                                driver_info.strip(), project_name.strip(), full_remarks, photo_path
                            ))
                            conn.commit()
                            
                            st.toast(f"✅ Material Receipt logged: {qty_in:,.2f} {unit_label} of {item_selected}", icon="📦")
                            st.success(f"Successfully recorded **{qty_in:,.2f} {unit_label}** of **{item_selected}**! Form reset for next entry.")
                    except sqlite3.OperationalError:
                        st.error("Database is currently busy. Please try again.")
                    finally:
                        st.session_state.is_submitting_in = False
                        st.rerun()

    st.divider()
    st.subheader("📑 Recent Incoming Material Deliveries Log")
    with get_db() as conn:
        df_recent_in = pd.read_sql_query("""
            SELECT timestamp, 
                   item_name, 
                   quantity, 
                   user_name, 
                   driver_details, 
                   project_name, 
                   remarks 
            FROM transactions 
            WHERE type = 'IN' 
            ORDER BY id DESC LIMIT 10
        """, conn)
    
    if not df_recent_in.empty:
        df_recent_in = df_recent_in.rename(columns={
            "timestamp": "Date & Time",
            "item_name": "Item Name",
            "quantity": "Qty Received",
            "user_name": "Logged By",
            "driver_details": "Driver / Plate #",
            "project_name": "Destination Site",
            "remarks": "DR / Supplier / Remarks"
        })
        st.dataframe(df_recent_in, use_container_width=True, hide_index=True)
    else:
        st.info("No incoming deliveries recorded yet.")

# --- MENU 3: MATERIAL ISSUE (OUT) ---
elif selected_menu == "📤 Material Issue (OUT)":
    st.title("📤 Issue Materials to Site (Stock OUT)")
    st.caption("Log material issuances to contractors, site locations, or tasks to deduct stock from inventory.")
    
    if "is_submitting_out" not in st.session_state:
        st.session_state.is_submitting_out = False

    with get_db() as conn:
        df_items = pd.read_sql_query("SELECT id, item_name, category, unit, current_stock FROM master_items ORDER BY category ASC, item_name ASC", conn)

    if df_items.empty:
        st.warning("⚠️ No master items found in database. Please add items under 'Manage Master Items' first.")
    else:
        item_dict = {row['item_name']: row for _, row in df_items.iterrows()}
        item_list = list(item_dict.keys())
        
        st.subheader("📋 Material Issuance Form")
        
        with st.form("stock_out_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                item_selected = st.selectbox("Select Material / Item", item_list, key="out_item_select")
                selected_item_info = item_dict[item_selected]
                unit_label = selected_item_info['unit']
                current_bal = selected_item_info['current_stock']
                
                qty_out = st.number_input(
                    f"Quantity to Issue ({unit_label})", 
                    value=None, 
                    min_value=0.01, 
                    step=1.0, 
                    format="%.2f", 
                    placeholder="0.00", 
                    key="out_qty"
                )
                issued_to = st.text_input("Issued To (Subcontractor / Foreperson / Person)", placeholder="e.g., Foreman Juan / ABC Construction", key="out_issued_to")
                driver_out = st.text_input("Hauler / Driver Name & Vehicle Details", placeholder="e.g., Driver Pedro / Site Buggy #2", key="out_driver")

            with col2:
                st.info(f"📌 **Current Available Stock:** `{current_bal:,.2f} {unit_label}`\n\n**Category:** `{selected_item_info['category']}`")
                project_name = st.text_input("Destination Site / Specific Location", placeholder="e.g., Sector 2 - Pier Column 4", key="out_project")
                purpose = st.text_area("Purpose / Construction Activity Notes", placeholder="e.g., Concrete pouring for foundation slab", key="out_purpose")

            st.divider()
            uploaded_file = st.file_uploader("📷 Upload Gate Pass or Signed Requisition Photo Proof (PNG, JPG, JPEG)", type=["png", "jpg", "jpeg"], key="out_file")
            
            submit_out = st.form_submit_button("📦 Confirm & Issue Material", disabled=st.session_state.is_submitting_out)
            
            if submit_out and not st.session_state.is_submitting_out:
                if qty_out is None or qty_out <= 0:
                    st.error("Please enter a valid quantity to issue.")
                elif not issued_to.strip():
                    st.error("Please enter who or which contractor the material is being issued to.")
                elif qty_out > current_bal:
                    st.error(f"❌ Cannot issue **{qty_out:,.2f} {unit_label}**. Only **{current_bal:,.2f} {unit_label}** available in stock.")
                else:
                    st.session_state.is_submitting_out = True
                    
                    try:
                        photo_path = ""
                        if uploaded_file is not None:
                            file_ext = os.path.splitext(uploaded_file.name)[1]
                            filename = f"OUT_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{item_selected.replace(' ', '_')}{file_ext}"
                            photo_path = os.path.join(UPLOAD_DIR, filename)
                            with open(photo_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())

                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("BEGIN IMMEDIATE")
                            
                            cursor.execute("SELECT current_stock FROM master_items WHERE item_name = ?", (item_selected,))
                            latest_stock = cursor.fetchone()['current_stock']
                            
                            if qty_out > latest_stock:
                                st.error(f"Stock changed during entry! Current balance is now {latest_stock:,.2f} {unit_label}.")
                            else:
                                cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", (qty_out, item_selected))
                                cursor.execute("""
                                    INSERT INTO transactions (
                                        timestamp, item_name, type, quantity, user_name, user_role, 
                                        driver_details, issued_to, project_name, purpose, photo_path
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    item_selected, "OUT", qty_out, user_name, user_role,
                                    driver_out.strip(), issued_to.strip(), project_name.strip(), purpose.strip(), photo_path
                                ))
                                conn.commit()
                                
                                st.toast(f"✅ Material Issued: {qty_out:,.2f} {unit_label} of {item_selected}", icon="📤")
                                st.success(f"Successfully issued **{qty_out:,.2f} {unit_label}** of **{item_selected}** to **{issued_to.strip()}**! Form reset for next entry.")
                    except sqlite3.OperationalError:
                        st.error("Database is currently busy. Please try again.")
                    finally:
                        st.session_state.is_submitting_out = False
                        st.rerun()

    st.divider()
    st.subheader("📑 Recent Material Issuances Log")
    with get_db() as conn:
        df_recent_out = pd.read_sql_query("""
            SELECT timestamp, 
                   item_name, 
                   quantity, 
                   issued_to, 
                   project_name, 
                   purpose,
                   user_name 
            FROM transactions 
            WHERE type = 'OUT' 
            ORDER BY id DESC LIMIT 10
        """, conn)
    
    if not df_recent_out.empty:
        df_recent_out = df_recent_out.rename(columns={
            "timestamp": "Date & Time",
            "item_name": "Item Name",
            "quantity": "Qty Issued",
            "issued_to": "Issued To",
            "project_name": "Destination Site",
            "purpose": "Purpose / Activity",
            "user_name": "Logged By"
        })
        st.dataframe(df_recent_out, use_container_width=True, hide_index=True)
    else:
        st.info("No material issuances recorded yet.")

# --- MENU 4: LOW STOCK ALERTS ---
elif selected_menu == "⚠️ Low Stock Alerts":
    st.subheader("⚠️ Low Stock Alert Center")
    with get_db() as conn:
        df_low = pd.read_sql_query("SELECT id, item_name, category, unit, current_stock, min_threshold FROM master_items WHERE current_stock <= min_threshold", conn)
    
    if not df_low.empty:
        st.error(f"Attention: {len(df_low)} item(s) are at or below minimum threshold levels!")
        st.dataframe(df_low, use_container_width=True, hide_index=True)
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
                        
                        if tx_row['type'] == 'IN':
                            cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", (tx_row['quantity'], tx_row['item_name']))
                        elif tx_row['type'] == 'OUT':
                            cursor.execute("UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?", (tx_row['quantity'], tx_row['item_name']))
                        
                        cursor.execute("UPDATE transactions SET edit_status = ? WHERE id = ?", (f"VOIDED: {reason}", sel_tx_id))
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
            selected_mod_id = st.selectbox("Select Item to Update", df_m['id'].tolist(), format_func=lambda x: df_m[df_m['id']==x]['item_name'].values[0])
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
                        cursor.execute("UPDATE master_items SET item_name = ?, category = ?, unit = ?, min_threshold = ? WHERE id = ?", 
                                       (m_name.strip(), m_cat.strip(), m_unit.strip(), m_thresh, selected_mod_id))
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
                            """, (ts, m_row['item_name'], "ADJUSTMENT", diff, user_name, user_role, f"Manual Adj: {adj_reason.strip()}"))
                            conn.commit()
                            st.success("Stock adjustment successfully applied and logged.")
                            st.rerun()
        else:
            st.info("No master items found to update.")

# --- MENU 7: MANAGE USERS (HEAD OFFICE EXCLUSIVE) ---
elif selected_menu == "👤 Manage Users" and user_role == "Head Office":
    st.subheader("👤 User Account Management")
    
    tab_user1, tab_user2 = st.tabs(["Create New User", "Existing Users List"])
    
    with tab_user1:
        with st.form("create_user_form", clear_on_submit=True):
            new_user = st.text_input("Username")
            new_pass = st.text_input("Password", type="password")
            new_role = st.selectbox("Role", ["Materials Supervisor", "Head Office"])
            
            if st.form_submit_button("Register User"):
                if new_user and new_pass:
                    try:
                        hashed = hash_password(new_pass.strip())
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                                           (new_user.strip(), hashed, new_role))
                            conn.commit()
                            st.success(f"User account '{new_user.strip()}' created successfully!")
                    except sqlite3.IntegrityError:
                        st.error("Username already exists.")
                else:
                    st.error("Please supply both username and password.")

    with tab_user2:
        with get_db() as conn:
            df_users = pd.read_sql_query("SELECT id, username, role FROM users", conn)
        st.dataframe(df_users, use_container_width=True, hide_index=True)

# --- MENU 8: MASTER AUDIT LOG ---
elif selected_menu == "📜 Master Audit Log":
    st.subheader("📜 Master Audit & Transaction Ledger")

    with get_db() as conn:
        df_all_tx = pd.read_sql_query("SELECT * FROM transactions ORDER BY id DESC", conn)

    if not df_all_tx.empty:
        # Search and Filters
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            search_query = st.text_input("🔍 Search Keyword (Item, User, Destination, DR)", "")
        with col_f2:
            type_filter = st.multiselect("Filter Transaction Type", options=["IN", "OUT", "ADJUSTMENT"], default=["IN", "OUT", "ADJUSTMENT"])

        filtered_df = df_all_tx[df_all_tx['type'].isin(type_filter)]
        
        if search_query:
            query = search_query.lower()
            filtered_df = filtered_df[
                filtered_df['item_name'].str.lower().str.contains(query, na=False) |
                filtered_df['user_name'].str.lower().str.contains(query, na=False) |
                filtered_df['project_name'].str.lower().str.contains(query, na=False) |
                filtered_df['remarks'].str.lower().str.contains(query, na=False)
            ]

        st.dataframe(filtered_df, use_container_width=True, hide_index=True)

        # CSV Download button
        csv_data = filtered_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Export Filtered Ledger as CSV", data=csv_data, file_name=f"audit_log_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")

        st.divider()
        st.markdown("##### 🖼️ Attached Proof Photos Search")
        has_photo = filtered_df[filtered_df['photo_path'].str.strip() != ""]
        if not has_photo.empty:
            sel_photo_id = st.selectbox("Select Transaction to View Attached Photo", has_photo['id'].tolist())
            img_path = has_photo[has_photo['id'] == sel_photo_id]['photo_path'].values[0]
            if os.path.exists(img_path):
                st.image(img_path, caption=f"Proof Photo for Transaction #{sel_photo_id}", width=400)
            else:
                st.warning("Photo file no longer exists on disk.")
        else:
            st.info("No proof attachments found in the selected transaction set.")
    else:
        st.info("Audit log is currently empty.")

# --- MENU 9: REMINDERS ---
elif selected_menu == "⏰ Reminders":
    st.subheader("⏰ Reminders & Task Tracker")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("##### Add New Reminder")
        with st.form("add_reminder_form", clear_on_submit=True):
            r_title = st.text_input("Task / Reminder Title")
            r_date = st.date_input("Due Date", value=date.today())
            r_priority = st.selectbox("Priority", ["LOW", "MEDIUM", "HIGH", "CRITICAL"])
            
            if st.form_submit_button("Save Reminder"):
                if r_title.strip():
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO reminders (user_name, title, due_date, priority, timestamp)
                            VALUES (?, ?, ?, ?, ?)
                        """, (user_name, r_title.strip(), str(r_date), r_priority, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        conn.commit()
                        st.success("Reminder logged!")
                        st.rerun()

    with col2:
        st.markdown("##### Active Reminders List")
        with get_db() as conn:
            df_reminders = pd.read_sql_query("SELECT id, title, due_date, priority, status FROM reminders WHERE status = 'PENDING' ORDER BY due_date ASC", conn)
        
        if not df_reminders.empty:
            for _, r_row in df_reminders.iterrows():
                col_r1, col_r2 = st.columns([3, 1])
                col_r1.write(f"📌 **{r_row['title']}** | Due: `{r_row['due_date']}` | Priority: `{r_row['priority']}`")
                if col_r2.button("Mark Done", key=f"rem_{r_row['id']}"):
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("UPDATE reminders SET status = 'COMPLETED' WHERE id = ?", (r_row['id'],))
                        conn.commit()
                        st.rerun()
        else:
            st.info("No pending reminders.")

# --- MENU 10: SCHEDULE ---
elif selected_menu == "📅 Schedule":
    st.subheader("📅 Site Events & Delivery Schedules")

    tab_s1, tab_s2 = st.tabs(["Schedule New Event", "Calendar View / Events List"])

    with tab_s1:
        with st.form("add_schedule_form", clear_on_submit=True):
            s_title = st.text_input("Event / Delivery Title")
            s_date = st.date_input("Event Date", value=date.today())
            s_start = st.time_input("Start Time", value=time(8, 0))
            s_end = st.time_input("End Time", value=time(17, 0))
            s_loc = st.text_input("Location / Gate Details")
            s_notes = st.text_area("Notes / Requirements")

            if st.form_submit_button("Save Schedule"):
                if s_title.strip():
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO schedules (user_name, title, event_date, start_time, end_time, location_details, notes, timestamp)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (user_name, s_title.strip(), str(s_date), str(s_start), str(s_end), s_loc.strip(), s_notes.strip(), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                        conn.commit()
                        st.success("Event scheduled successfully!")
                        st.rerun()

    with tab_s2:
        with get_db() as conn:
            df_sched = pd.read_sql_query("SELECT id, event_date, start_time, end_time, title, location_details, notes, user_name FROM schedules ORDER BY event_date ASC, start_time ASC", conn)
        
        if not df_sched.empty:
            df_sched = df_sched.rename(columns={
                "event_date": "Date",
                "start_time": "Start",
                "end_time": "End",
                "title": "Title",
                "location_details": "Location",
                "notes": "Notes",
                "user_name": "Created By"
            })
            st.dataframe(df_sched, use_container_width=True, hide_index=True)
        else:
            st.info("No upcoming site events scheduled.")
