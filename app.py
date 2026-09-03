import streamlit as st
import sqlite3
import pandas as pd
import json
import os
from datetime import datetime, time
import io

# --- 1. DATABASE CONFIGURATION & INITIALIZATION ---
DB_FILE = "inventory_system.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

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
            current_stock REAL DEFAULT 0.0,
            min_threshold REAL DEFAULT 0.0
        )
    """)

    # Transactions Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            item_name TEXT NOT NULL,
            type TEXT NOT NULL, -- 'IN', 'OUT', or 'ADJUSTMENT'
            quantity REAL NOT NULL,
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

    # Physical Inventory Counts (Audit)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS physical_inventory_counts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            audit_date TEXT NOT NULL,
            item_name TEXT NOT NULL,
            system_stock REAL NOT NULL,
            physical_stock REAL NOT NULL,
            variance REAL NOT NULL,
            unit TEXT NOT NULL,
            counted_by TEXT NOT NULL,
            supervisor_remarks TEXT,
            sync_status TEXT DEFAULT 'PENDING_ADMIN_REVIEW',
            resolved_by TEXT,
            resolved_stock REAL,
            admin_explanation TEXT,
            timestamp TEXT NOT NULL
        )
    """)

    # Edit Requests
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS edit_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            requested_by TEXT NOT NULL,
            reason TEXT NOT NULL,
            original_data TEXT NOT NULL,
            proposed_data TEXT NOT NULL,
            status TEXT DEFAULT 'PENDING',
            review_remarks TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (transaction_id) REFERENCES transactions (id)
        )
    """)

    # Notifications
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            target_role TEXT,
            target_user TEXT,
            is_read INTEGER DEFAULT 0,
            timestamp TEXT NOT NULL
        )
    """)

    # Reminders
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT NOT NULL,
            title TEXT NOT NULL,
            due_date TEXT NOT NULL,
            priority TEXT DEFAULT 'Medium',
            status TEXT DEFAULT 'PENDING',
            timestamp TEXT NOT NULL
        )
    """)

    # Schedules
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
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('admin', 'admin123', 'Head Office')")
        cursor.execute("INSERT INTO users (username, password, role) VALUES ('supervisor', 'super123', 'Materials Supervisor')")

    # Seed sample master items if empty
    cursor.execute("SELECT COUNT(*) FROM master_items")
    if cursor.fetchone()[0] == 0:
        sample_items = [
            ('Portland Cement', '1. Construction Materials', 'Bags', 250.0, 50.0),
            ('Deformed Steel Bar 12mm', '1. Construction Materials', 'Pcs', 120.0, 30.0),
            ('Diesel Fuel', '2. Fuel & Oils', 'Liters', 800.0, 200.0),
            ('Safety Helmets', '3. PPE & Tools', 'Pcs', 45.0, 10.0)
        ]
        cursor.executemany("INSERT INTO master_items (item_name, category, unit, current_stock, min_threshold) VALUES (?, ?, ?, ?, ?)", sample_items)

    conn.commit()
    conn.close()

init_db()

# Ensure uploads folder exists
if not os.path.exists("uploads"):
    os.makedirs("uploads")

# --- 2. HELPER FUNCTIONS ---
def create_notification(message, target_role=None, target_user=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notifications (message, target_role, target_user, timestamp)
        VALUES (?, ?, ?, ?)
    """, (message, target_role, target_user, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def generate_excel_report(user_name, report_date, df_tx, df_stock):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_stock.to_excel(writer, sheet_name='Current Stock Balance', index=False)
        df_tx.to_excel(writer, sheet_name='Daily Transactions', index=False)
    processed_data = output.getvalue()
    return processed_data

# --- 3. SESSION STATE & LOGIN PAGE ---
st.set_page_config(page_title="Site Inventory Management System", layout="wide", page_icon="📦")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_name = ""
    st.session_state.user_role = ""

def login_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username, role FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    conn.close()
    return user

if not st.session_state.logged_in:
    st.title("📦 Inventory Management System")
    st.subheader("Login to Access System")

    col1, col2, _ = st.columns([1, 1, 1])
    with col1:
        u_input = st.text_input("Username")
        p_input = st.text_input("Password", type="password")
        if st.button("Log In", use_container_width=True):
            user = login_user(u_input, p_input)
            if user:
                st.session_state.logged_in = True
                st.session_state.user_name = user["username"]
                st.session_state.user_role = user["role"]
                st.success(f"Welcome, {user['username']}!")
                st.rerun()
            else:
                st.error("Invalid Username or Password")
    st.stop()

# --- 4. MAIN SYSTEM INTERFACE ---
conn = get_db_connection()
cursor = conn.cursor()

user_name = st.session_state.user_name
user_role = st.session_state.user_role

# Sidebar Navigation & User Info
st.sidebar.title("📌 Navigation")
st.sidebar.write(f"Logged in as: **{user_name}** (`{user_role}`)")

# Read Unread Notifications
df_notifs = pd.read_sql_query("""
    SELECT id, message, timestamp FROM notifications 
    WHERE (target_role = ? OR target_user = ? OR (target_role IS NULL AND target_user IS NULL))
      AND is_read = 0 
    ORDER BY id DESC
""", conn, params=(user_role, user_name))

if not df_notifs.empty:
    st.sidebar.warning(f"🔔 You have {len(df_notifs)} unread notification(s)!")
    with st.sidebar.expander("View Notifications"):
        for _, n_row in df_notifs.iterrows():
            st.caption(f"[{n_row['timestamp']}] {n_row['message']}")
        if st.button("Mark All as Read"):
            cursor.execute("UPDATE notifications SET is_read = 1 WHERE target_role = ? OR target_user = ?", (user_role, user_name))
            conn.commit()
            st.rerun()

if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.rerun()

# Dynamic Menu Based on Role
if user_role == "Materials Supervisor":
    menu_options = [
        "📊 Dashboard Overview",
        "📥 Stock Receipt (IN)",
        "📤 Issue Material (OUT)",
        "📦 Physical Inventory Audit",
        "📜 My Log & Request Edits",
        "📅 Daily Report (Excel)",
        "⏰ Reminders",
        "📅 Schedule"
    ]
else:  # Head Office / Admin
    menu_options = [
        "📊 Dashboard Overview",
        "📥 Stock Receipt (IN)",
        "📤 Issue Material (OUT)",
        "📦 Physical Inventory Audit",
        "✏️ Edit Requests Review",
        "📅 Daily Report (Excel)",
        "➕ Manage Master Items",
        "📜 Master Audit Log",
        "👤 Manage Users",
        "⏰ Reminders",
        "📅 Schedule"
    ]

selected_menu = st.sidebar.radio("Select Action:", menu_options)

# --- MENU 1: DASHBOARD OVERVIEW ---
if selected_menu == "📊 Dashboard Overview":
    st.subheader("📊 Inventory Dashboard Overview")

    df_items = pd.read_sql_query("SELECT category, item_name, current_stock, min_threshold, unit FROM master_items ORDER BY category ASC, item_name ASC", conn)

    # Search & Filter Controls
    c_search, c_filter = st.columns([2, 1])
    search_query = c_search.text_input("🔍 Search Items", placeholder="Enter item name or category...")
    
    categories = ["All"] + list(df_items['category'].unique()) if not df_items.empty else ["All"]
    selected_cat = c_filter.selectbox("Filter Category", categories)

    filtered_items = df_items.copy()
    if search_query:
        filtered_items = filtered_items[filtered_items['item_name'].str.contains(search_query, case=False, na=False) | 
                                        filtered_items['category'].str.contains(search_query, case=False, na=False)]
    if selected_cat != "All":
        filtered_items = filtered_items[filtered_items['category'] == selected_cat]

    # Quick Metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Item Types", len(df_items))
    low_stock_count = len(df_items[df_items['current_stock'] <= df_items['min_threshold']])
    m2.metric("Low Stock Alerts", low_stock_count, delta_color="inverse")
    
    today_tx_count = cursor.execute("SELECT COUNT(*) FROM transactions WHERE DATE(timestamp) = ?", (datetime.now().strftime("%Y-%m-%d"),)).fetchone()[0]
    m3.metric("Today's Transactions", today_tx_count)

    st.markdown("#### Item Stock Balance Table")
    
    def highlight_low_stock(val):
        color = 'background-color: #ffcccc' if val <= 0 else ''
        return color

    st.dataframe(filtered_items, use_container_width=True)

# --- MENU 2: STOCK RECEIPT (IN) ---
elif selected_menu == "📥 Stock Receipt (IN)":
    st.subheader("📥 Receive Stock / Deliveries (IN)")

    items_list = pd.read_sql_query("SELECT item_name, unit FROM master_items", conn)
    
    if not items_list.empty:
        with st.form("receive_stock_form", clear_on_submit=True):
            item_selected = st.selectbox("Select Master Item", items_list['item_name'].tolist())
            qty_in = st.number_input("Quantity Received", min_value=0.1, step=1.0)
            driver_info = st.text_input("Driver / Delivery Details", placeholder="e.g. Plate # ABC-123, Driver: John Doe")
            project_name = st.text_input("Project / Site Name", placeholder="e.g. Building A Expansion")
            remarks = st.text_area("Delivery Remarks / Notes")
            uploaded_file = st.file_uploader("Upload Delivery Receipt Photo Proof (Optional)", type=['png', 'jpg', 'jpeg'])

            submit_in = st.form_submit_button("Submit Stock Receipt")

        if submit_in:
            photo_path = ""
            if uploaded_file is not None:
                photo_path = os.path.join("uploads", f"IN_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name}")
                with open(photo_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

            # Update master items stock
            cursor.execute("UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?", (qty_in, item_selected))
            
            # Record Transaction
            cursor.execute("""
                INSERT INTO transactions (timestamp, item_name, type, quantity, user_role, driver_details, project_name, remarks, photo_path) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item_selected, "IN", qty_in, user_name, driver_info, project_name, remarks, photo_path))
            
            conn.commit()
            st.success(f"Successfully added {qty_in} to {item_selected}!")
            st.rerun()
    else:
        st.warning("Please add items to Master Inventory first.")

# --- MENU 3: ISSUE MATERIAL (OUT) ---
elif selected_menu == "📤 Issue Material (OUT)":
    st.subheader("📤 Issue Materials / Stock Out")

    df_stock = pd.read_sql_query("SELECT item_name, current_stock, min_threshold, unit FROM master_items", conn)
    
    if not df_stock.empty:
        with st.form("issue_stock_form", clear_on_submit=True):
            item_selected = st.selectbox("Select Item to Issue", df_stock['item_name'].tolist())
            
            current_stk = df_stock[df_stock['item_name'] == item_selected]['current_stock'].values[0]
            min_thresh = df_stock[df_stock['item_name'] == item_selected]['min_threshold'].values[0]
            unit = df_stock[df_stock['item_name'] == item_selected]['unit'].values[0]

            st.info(f"Available Stock: **{current_stk} {unit}**")

            qty_out = st.number_input("Quantity to Issue", min_value=0.1, step=1.0)
            issued_to = st.text_input("Issued To (Person / Subcontractor)", placeholder="e.g. Juan Cruz (Foreman)")
            driver_out = st.text_input("Driver / Hauler Details (If applicable)")
            project_name = st.text_input("Project / Cost Center")
            purpose = st.text_area("Purpose / Area of Work")

            submit_out = st.form_submit_button("Confirm Material Release")

        if submit_out:
            if qty_out > current_stk:
                st.error(f"Cannot issue {qty_out}. Only {current_stk} {unit} available!")
            else:
                new_stock = current_stk - qty_out
                cursor.execute("UPDATE master_items SET current_stock = ? WHERE item_name = ?", (new_stock, item_selected))
                
                cursor.execute("""
                    INSERT INTO transactions (timestamp, item_name, type, quantity, user_role, driver_details, issued_to, project_name, purpose) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item_selected, "OUT", qty_out, user_name, driver_out, issued_to, project_name, purpose))
                
                conn.commit()

                # Low Stock Alert Check
                if new_stock <= min_thresh:
                    create_notification(f"⚠️ LOW STOCK ALERT: {item_selected} is now down to {new_stock} (Min Threshold: {min_thresh})", target_role="Head Office")

                st.success(f"Successfully issued {qty_out} {unit} of {item_selected}!")
                st.rerun()
    else:
        st.warning("Please add items to Master Inventory first.")

# --- MENU 4: PHYSICAL INVENTORY AUDIT ---
elif selected_menu == "📦 Physical Inventory Audit":
    st.subheader("📦 Physical Inventory Audit & Variance Reconciliation")

    if user_role == "Materials Supervisor":
        st.markdown("#### Submit Physical Count")
        df_curr = pd.read_sql_query("SELECT item_name, current_stock, unit FROM master_items ORDER BY item_name ASC", conn)
        
        if not df_curr.empty:
            audit_date = st.date_input("Audit Date", datetime.now())
            
            with st.form("audit_form"):
                st.markdown("Enter actual physical count for each item:")
                count_data = []
                
                for idx, row in df_curr.iterrows():
                    c1, c2, c3 = st.columns([0.4, 0.3, 0.3])
                    with c1:
                        st.write(f"**{row['item_name']}** (Sys: {row['current_stock']} {row['unit']})")
                    with c2:
                        phys_qty = st.number_input(f"Physical Qty", min_value=0.0, value=float(row['current_stock']), key=f"audit_qty_{idx}", label_visibility="collapsed")
                    with c3:
                        variance = phys_qty - row['current_stock']
                        var_color = "green" if variance == 0 else ("red" if variance < 0 else "blue")
                        st.markdown(f":{var_color}[Variance: {variance:+.2f}]")
                        count_data.append((row['item_name'], row['current_stock'], phys_qty, variance, row['unit']))

                sup_remarks = st.text_area("Supervisor Audit Notes / Remarks")
                submit_audit = st.form_submit_button("Submit Audit Findings")

            if submit_audit:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                has_variance = False
                for item, sys_s, phys_s, var, unit in count_data:
                    status = "PENDING_ADMIN_REVIEW" if var != 0 else "AUTO_SYNCED"
                    if var != 0:
                        has_variance = True
                    cursor.execute("""
                        INSERT INTO physical_inventory_counts 
                        (audit_date, item_name, system_stock, physical_stock, variance, unit, counted_by, supervisor_remarks, sync_status, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (audit_date.strftime("%Y-%m-%d"), item, sys_s, phys_s, var, unit, user_name, sup_remarks, status, ts))
                
                conn.commit()

                if has_variance:
                    create_notification(f"🚨 Audit submitted by {user_name} with stock variances requiring review.", target_role="Head Office")
                    st.warning("Audit submitted! Variance detected; sent to Head Office for review.")
                else:
                    st.success("Audit submitted! All physical counts match system stock perfectly.")
                st.rerun()

    else:  # Head Office View
        st.markdown("#### Pending Variance Reviews")
        df_pending = pd.read_sql_query("""
            SELECT id, audit_date, item_name, system_stock, physical_stock, variance, unit, counted_by, supervisor_remarks, timestamp 
            FROM physical_inventory_counts 
            WHERE sync_status = 'PENDING_ADMIN_REVIEW'
            ORDER BY timestamp DESC
        """, conn)

        if not df_pending.empty:
            st.dataframe(df_pending, use_container_width=True)
            
            selected_audit_id = st.selectbox("Select Audit Entry to Reconcile", df_pending['id'].tolist())
            audit_row = df_pending[df_pending['id'] == selected_audit_id].iloc[0]

            st.info(f"Reconciling **{audit_row['item_name']}**: System Stock = {audit_row['system_stock']} | Physical Count = {audit_row['physical_stock']} (Variance: {audit_row['variance']:+.2f})")

            rec_action = st.radio("Resolution Action:", ["Update System Stock to Physical Count", "Keep Current System Stock (Reject Audit Variance)"])
            admin_explanation = st.text_area("Admin Resolution Notes / Reason")

            if st.button("Resolve Variance"):
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if rec_action == "Update System Stock to Physical Count":
                    final_stock = audit_row['physical_stock']
                    cursor.execute("UPDATE master_items SET current_stock = ? WHERE item_name = ?", (final_stock, audit_row['item_name']))
                    
                    cursor.execute("""
                        INSERT INTO transactions (timestamp, item_name, type, quantity, user_role, remarks) 
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (ts, audit_row['item_name'], "ADJUSTMENT", audit_row['variance'], user_name, f"Audit Adjustment: {admin_explanation}"))
                    
                    status = "RESOLVED_UPDATED"
                else:
                    final_stock = audit_row['system_stock']
                    status = "RESOLVED_REJECTED"

                cursor.execute("""
                    UPDATE physical_inventory_counts 
                    SET sync_status = ?, resolved_by = ?, resolved_stock = ?, admin_explanation = ?
                    WHERE id = ?
                """, (status, user_name, final_stock, admin_explanation, selected_audit_id))

                conn.commit()
                create_notification(f"Audit variance for {audit_row['item_name']} resolved: {status}", target_user=audit_row['counted_by'])
                st.success("Variance resolved successfully.")
                st.rerun()
        else:
            st.info("No pending audit variances to review.")

# --- MENU 5: MY LOG & REQUEST EDITS / EDIT REQUESTS ---
elif selected_menu == "📜 My Log & Request Edits" or selected_menu == "✏️ Edit Requests Review":
    if user_role == "Materials Supervisor":
        st.subheader("📜 My Activity Log & Request Correction")
        
        df_my_tx = pd.read_sql_query("""
            SELECT id, timestamp, item_name, type, quantity, driver_details, issued_to, project_name, purpose, remarks, edit_status
            FROM transactions 
            WHERE user_role = ? 
            ORDER BY id DESC LIMIT 50
        """, conn, params=(user_name,))

        if not df_my_tx.empty:
            st.dataframe(df_my_tx, use_container_width=True)

            st.markdown("#### ✏️ Request Transaction Correction")
            tx_id_to_edit = st.selectbox("Select Transaction ID to Request Edit", df_my_tx['id'].tolist())
            tx_data = df_my_tx[df_my_tx['id'] == tx_id_to_edit].iloc[0]

            with st.form("request_edit_form"):
                st.write(f"Requesting Edit for TX #{tx_id_to_edit} ({tx_data['item_name']} - {tx_data['type']})")
                new_qty = st.number_input("Corrected Quantity", value=float(tx_data['quantity']))
                new_remarks = st.text_input("Corrected Remarks / Details", value=str(tx_data['remarks'] if tx_data['remarks'] else ''))
                reason = st.text_area("Reason for Edit Request", placeholder="e.g. Typo in quantity")
                
                submit_req = st.form_submit_button("Submit Edit Request")

            if submit_req:
                orig_dict = json.dumps({"quantity": tx_data['quantity'], "remarks": tx_data['remarks']})
                prop_dict = json.dumps({"quantity": new_qty, "remarks": new_remarks})
                
                cursor.execute("""
                    INSERT INTO edit_requests (transaction_id, requested_by, reason, original_data, proposed_data, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (tx_id_to_edit, user_name, reason, orig_dict, prop_dict, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                
                cursor.execute("UPDATE transactions SET edit_status = 'PENDING_EDIT' WHERE id = ?", (tx_id_to_edit,))
                conn.commit()

                create_notification(f"✏️ New Edit Request submitted by {user_name} for TX #{tx_id_to_edit}.", target_role="Head Office")
                st.success("Edit request submitted to Head Office for approval!")
                st.rerun()
        else:
            st.info("No recent activity logs found.")

    else:  # Head Office View
        st.subheader("✏️ Edit Requests Review")
        
        df_reqs = pd.read_sql_query("""
            SELECT e.id, e.transaction_id, e.requested_by, e.reason, e.original_data, e.proposed_data, e.status, e.timestamp,
                   t.item_name, t.type
            FROM edit_requests e
            JOIN transactions t ON e.transaction_id = t.id
            WHERE e.status = 'PENDING'
            ORDER BY e.id DESC
        """, conn)

        if not df_reqs.empty:
            st.dataframe(df_reqs, use_container_width=True)

            selected_req_id = st.selectbox("Select Request ID to Review", df_reqs['id'].tolist())
            req_row = df_reqs[df_reqs['id'] == selected_req_id].iloc[0]

            orig = json.loads(req_row['original_data'])
            prop = json.loads(req_row['proposed_data'])

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Original Data:**")
                st.json(orig)
            with c2:
                st.markdown("**Proposed Data:**")
                st.json(prop)

            review_notes = st.text_area("Review Remarks / Decision Notes")
            action_col1, action_col2 = st.columns(2)

            if action_col1.button("✅ Approve Request", use_container_width=True):
                tx_id = req_row['transaction_id']
                tx = cursor.execute("SELECT item_name, type, quantity FROM transactions WHERE id = ?", (tx_id,)).fetchone()
                
                item, t_type, old_qty = tx[0], tx[1], tx[2]
                new_qty = prop['quantity']
                qty_diff = new_qty - old_qty

                if t_type == 'IN':
                    cursor.execute("UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?", (qty_diff, item))
                elif t_type == 'OUT':
                    cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", (qty_diff, item))

                cursor.execute("UPDATE transactions SET quantity = ?, remarks = ?, edit_status = 'EDITED' WHERE id = ?", (new_qty, prop['remarks'], tx_id))
                cursor.execute("UPDATE edit_requests SET status = 'APPROVED', review_remarks = ? WHERE id = ?", (review_notes, selected_req_id))
                conn.commit()

                create_notification(f"✅ Your edit request for TX #{tx_id} was APPROVED.", target_user=req_row['requested_by'])
                st.success("Edit request approved and stock adjusted.")
                st.rerun()

            if action_col2.button("❌ Reject Request", use_container_width=True):
                cursor.execute("UPDATE edit_requests SET status = 'REJECTED', review_remarks = ? WHERE id = ?", (review_notes, selected_req_id))
                cursor.execute("UPDATE transactions SET edit_status = 'NORMAL' WHERE id = ?", (req_row['transaction_id'],))
                conn.commit()

                create_notification(f"❌ Your edit request for TX #{req_row['transaction_id']} was REJECTED.", target_user=req_row['requested_by'])
                st.warning("Edit request rejected.")
                st.rerun()
        else:
            st.info("No pending edit requests.")

# --- MENU 6: DAILY REPORT (EXCEL) ---
elif selected_menu == "📅 Daily Report (Excel)":
    st.subheader("📅 Export Daily Inventory Activity & Balance Report")

    report_date = st.date_input("Select Report Date", datetime.now())
    str_date = report_date.strftime("%Y-%m-%d")

    df_daily_tx = pd.read_sql_query("""
        SELECT timestamp, item_name, type, quantity, user_role, driver_details, issued_to, project_name, purpose, remarks 
        FROM transactions 
        WHERE DATE(timestamp) = ?
        ORDER BY timestamp ASC
    """, conn, params=(str_date,))

    df_curr_stock = pd.read_sql_query("SELECT category, item_name, current_stock, min_threshold, unit FROM master_items ORDER BY category ASC, item_name ASC", conn)

    st.info(f"Found **{len(df_daily_tx)}** transaction records for {str_date}.")

    excel_file = generate_excel_report(user_name, str_date, df_daily_tx, df_curr_stock)

    st.download_button(
        label="📥 Download Daily Excel Report",
        data=excel_file,
        file_name=f"Inventory_Report_{str_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

# --- MENU 7: MANAGE MASTER ITEMS ---
elif selected_menu == "➕ Manage Master Items":
    st.subheader("➕ Master Inventory Item Management")

    tab1, tab2 = st.tabs(["Add New Item", "Modify Existing Item"])

    with tab1:
        with st.form("add_item_form", clear_on_submit=True):
            new_item = st.text_input("Item Name")
            new_cat = st.text_input("Category", placeholder="e.g. 1. Fuel & Oils")
            new_unit = st.text_input("Unit of Measure", placeholder="e.g. Bags, Liters, Pcs")
            init_stock = st.number_input("Initial Stock Quantity", min_value=0.0, step=1.0)
            min_thresh = st.number_input("Minimum Alert Threshold", min_value=0.0, step=1.0)

            if st.form_submit_button("Add Item"):
                try:
                    cursor.execute("""
                        INSERT INTO master_items (item_name, category, unit, current_stock, min_threshold)
                        VALUES (?, ?, ?, ?, ?)
                    """, (new_item.strip(), new_cat.strip(), new_unit.strip(), init_stock, min_thresh))
                    conn.commit()
                    st.success(f"Item '{new_item}' added successfully!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Item with this name already exists.")

    with tab2:
        df_m = pd.read_sql_query("SELECT id, item_name, category, unit, current_stock, min_threshold FROM master_items", conn)
        if not df_m.empty:
            selected_mod_id = st.selectbox("Select Item to Update", df_m['id'].tolist(), format_func=lambda x: df_m[df_m['id']==x]['item_name'].values[0])
            m_row = df_m[df_m['id'] == selected_mod_id].iloc[0]

            with st.form("mod_item_form"):
                m_name = st.text_input("Item Name", value=m_row['item_name'])
                m_cat = st.text_input("Category", value=m_row['category'])
                m_unit = st.text_input("Unit", value=m_row['unit'])
                m_stock = st.number_input("Current Stock", value=float(m_row['current_stock']))
                m_thresh = st.number_input("Min Threshold", value=float(m_row['min_threshold']))

                if st.form_submit_button("Update Item Details"):
                    cursor.execute("""
                        UPDATE master_items 
                        SET item_name = ?, category = ?, unit = ?, current_stock = ?, min_threshold = ?
                        WHERE id = ?
                    """, (m_name.strip(), m_cat.strip(), m_unit.strip(), m_stock, m_thresh, selected_mod_id))
                    conn.commit()
                    st.success("Item updated successfully!")
                    st.rerun()

# --- MENU 8: MASTER AUDIT LOG ---
elif selected_menu == "📜 Master Audit Log":
    st.subheader("📜 Complete Site Transaction Log")

    df_master_log = pd.read_sql_query("""
        SELECT id, timestamp, item_name, type, quantity, user_role, driver_details, issued_to, project_name, purpose, remarks, edit_status, photo_path
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
                st.image(p_path, caption=f"Proof for TX #{sel_p_id}")
            else:
                st.warning("Photo file not found on disk.")
        else:
            st.info("No transaction photos uploaded yet.")
    else:
        st.info("No transaction activity recorded.")

# --- MENU 9: MANAGE USERS ---
elif selected_menu == "👤 Manage Users":
    st.subheader("👤 User Account Management")

    with st.form("create_user_form", clear_on_submit=True):
        st.markdown("#### Create New User")
        new_u = st.text_input("Username")
        new_p = st.text_input("Password", type="password")
        new_r = st.selectbox("Role", ["Materials Supervisor", "Head Office"])

        if st.form_submit_button("Create Account"):
            try:
                cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (new_u.strip(), new_p.strip(), new_r))
                conn.commit()
                st.success(f"User '{new_u}' created successfully!")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Username already exists.")

    st.markdown("---")
    st.markdown("#### Existing Accounts")
    df_users = pd.read_sql_query("SELECT id, username, role FROM users", conn)
    st.dataframe(df_users, use_container_width=True)

# --- MENU 10: REMINDERS ---
elif selected_menu == "⏰ Reminders":
    st.subheader("⏰ Reminders & Task Tracker")

    with st.form("add_reminder", clear_on_submit=True):
        r_title = st.text_input("Reminder Title / Task")
        r_date = st.date_input("Due Date", datetime.now())
        r_priority = st.selectbox("Priority", ["High", "Medium", "Low"])

        if st.form_submit_button("Set Reminder"):
            cursor.execute("""
                INSERT INTO reminders (user_name, title, due_date, priority, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (user_name, r_title, r_date.strftime("%Y-%m-%d"), r_priority, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            st.success("Reminder set successfully!")
            st.rerun()

    st.markdown("---")
    df_rems = pd.read_sql_query("SELECT id, title, due_date, priority, status FROM reminders WHERE user_name = ? ORDER BY due_date ASC", conn, params=(user_name,))
    if not df_rems.empty:
        st.dataframe(df_rems, use_container_width=True)
        done_id = st.selectbox("Select Completed Reminder", df_rems['id'].tolist())
        if st.button("Mark as Completed"):
            cursor.execute("UPDATE reminders SET status = 'COMPLETED' WHERE id = ?", (done_id,))
            conn.commit()
            st.rerun()
    else:
        st.info("No reminders found.")

# --- MENU 11: SCHEDULE ---
elif selected_menu == "📅 Schedule":
    st.subheader("📅 Site Events & Delivery Schedule")

    with st.form("add_schedule", clear_on_submit=True):
        s_title = st.text_input("Event / Delivery Title")
        s_date = st.date_input("Event Date", datetime.now())
        s_col1, s_col2 = st.columns(2)
        with s_col1:
            s_start = st.time_input("Start Time", time(9, 0))
        with s_col2:
            s_end = st.time_input("End Time", time(10, 0))
        s_loc = st.text_input("Location / Gate Details")
        s_notes = st.text_area("Notes / Instructions")

        if st.form_submit_button("Add Event to Schedule"):
            cursor.execute("""
                INSERT INTO schedules (user_name, title, event_date, start_time, end_time, location_details, notes, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_name, s_title, s_date.strftime("%Y-%m-%d"), str(s_start), str(s_end), s_loc, s_notes, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            st.success("Event scheduled successfully!")
            st.rerun()

    st.markdown("---")
    df_sched = pd.read_sql_query("SELECT id, event_date, start_time, end_time, title, location_details, notes FROM schedules ORDER BY event_date ASC, start_time ASC", conn)
    if not df_sched.empty:
        st.dataframe(df_sched, use_container_width=True)
    else:
        st.info("No scheduled events found.")

conn.close()
