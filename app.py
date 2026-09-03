import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta, time
import io
import os
import json
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Ensure photo directory exists
os.makedirs("uploads", exist_ok=True)

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
    driver_details TEXT,
    issued_to TEXT,
    project_name TEXT,
    purpose TEXT,
    remarks TEXT,
    photo_path TEXT,
    edit_status TEXT DEFAULT 'NORMAL'
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS edit_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id INTEGER,
    requested_by TEXT,
    reason TEXT,
    original_data TEXT,
    proposed_data TEXT,
    status TEXT DEFAULT 'PENDING',
    review_remarks TEXT,
    timestamp TEXT,
    FOREIGN KEY(transaction_id) REFERENCES transactions(id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_user TEXT,
    target_role TEXT,
    message TEXT,
    is_read INTEGER DEFAULT 0,
    timestamp TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name TEXT,
    title TEXT,
    due_date TEXT,
    priority TEXT,
    status TEXT DEFAULT 'PENDING',
    timestamp TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name TEXT,
    title TEXT,
    event_date TEXT,
    start_time TEXT,
    end_time TEXT,
    location_details TEXT,
    notes TEXT,
    timestamp TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS physical_inventory_counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_date TEXT,
    item_name TEXT,
    system_stock REAL,
    physical_stock REAL,
    variance REAL,
    unit TEXT,
    counted_by TEXT,
    supervisor_remarks TEXT,
    sync_status TEXT DEFAULT 'UNSYNCED',
    resolved_by TEXT,
    resolved_stock REAL,
    admin_explanation TEXT,
    timestamp TEXT
)
""")

# Schema Safe Migrations
for col, col_type in [
    ("driver_details", "TEXT"),
    ("issued_to", "TEXT"),
    ("project_name", "TEXT"),
    ("purpose", "TEXT"),
    ("photo_path", "TEXT"),
    ("edit_status", "TEXT DEFAULT 'NORMAL'")
]:
    try:
        cursor.execute(f"ALTER TABLE transactions ADD COLUMN {col} {col_type}")
    except sqlite3.OperationalError:
        pass

for col, col_type in [
    ("supervisor_remarks", "TEXT"),
    ("resolved_by", "TEXT"),
    ("resolved_stock", "REAL"),
    ("admin_explanation", "TEXT")
]:
    try:
        cursor.execute(f"ALTER TABLE physical_inventory_counts ADD COLUMN {col} {col_type}")
    except sqlite3.OperationalError:
        pass

# Seed Default Accounts
cursor.execute("SELECT COUNT(*) FROM users")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                   ("admin", "admin123", "Head Office"))
    cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                   ("supervisor", "super123", "Materials Supervisor"))

# Seed Expanded Inventory List
cursor.execute("SELECT COUNT(*) FROM master_items")
if cursor.fetchone()[0] == 0:
    sample_items = [
        ("Diesel Fuel", "1. Fuel & Oils", "Liters", 1200, 500),
        ("Gasoline", "1. Fuel & Oils", "Liters", 200, 50),
        ("Engine Oil #10", "1. Fuel & Oils", "Liters", 40, 20),
        ("Engine Oil #40", "1. Fuel & Oils", "Liters", 40, 20),
        ("Hydraulic Oil #68", "1. Fuel & Oils", "Pails (20L)", 8, 3),
        ("Chassis Grease", "1. Fuel & Oils", "Cans (1kg)", 15, 5),
        ("Tonner Cement", "2. Construction Materials", "Bags (1-Ton)", 15, 5),
        ("Portland Cement", "2. Construction Materials", "Bags (40kg)", 250, 100),
        ("Plywood 1/2 (4x8)", "2. Construction Materials", "Sheets", 80, 25),
        ("Plywood 3/4 (4x8)", "2. Construction Materials", "Sheets", 50, 15),
        ("Coco Lumber 2x2x12", "2. Construction Materials", "Board Feet", 300, 100),
        ("Rebar 10mm x 6m", "3. Steel / Rebar", "Pcs", 350, 100),
        ("Rebar 12mm x 6m", "3. Steel / Rebar", "Pcs", 250, 80),
        ("Rebar 16mm x 6m", "3. Steel / Rebar", "Pcs", 150, 50),
        ("G.I. Tie Wire #16", "3. Steel / Rebar", "Kilos", 50, 15),
        ("CWN #1-1/2 (Common Nails)", "4A. Nails & Fasteners", "Kilos", 30, 10),
        ("CWN #2 (2 Common Nails)", "4A. Nails & Fasteners", "Kilos", 45, 20),
        ("CWN #3 (3 Common Nails)", "4A. Nails & Fasteners", "Kilos", 40, 15),
        ("CWN #4 (4 Common Nails)", "4A. Nails & Fasteners", "Kilos", 35, 10),
        ("Concrete Nails 3", "4A. Nails & Fasteners", "Kilos", 20, 5),
        ("Cutting Disc 4", "4B. Cutting & Grinding Consumables", "Pcs", 120, 50),
        ("Grinding Disc 4", "4B. Cutting & Grinding Consumables", "Pcs", 60, 20),
        ("Diamond Cutter Blade 14", "4B. Cutting & Grinding Consumables", "Pcs", 4, 2),
        ("Welding Rod 6011", "4C. Welding Supplies & PPE", "Kilos", 30, 15),
        ("Welding Rod 6013", "4C. Welding Supplies & PPE", "Kilos", 50, 20),
        ("Safety Helmets (Hard Hats)", "4C. Welding Supplies & PPE", "Pcs", 25, 10),
        ("Cotton Gloves (Pair)", "4C. Welding Supplies & PPE", "Pairs", 100, 30),
        ("Chalk Stone (Marking)", "4D. General Site Supplies", "Boxes", 12, 5),
        ("Nylon Rope 1/2", "4D. General Site Supplies", "Meters", 100, 30)
    ]
    cursor.executemany("""
    INSERT INTO master_items (item_name, category, unit, current_stock, min_threshold)
    VALUES (?, ?, ?, ?, ?)
    """, sample_items)

conn.commit()


# --- HELPER: NOTIFICATION CREATOR ---
def create_notification(message, target_user=None, target_role=None):
    cursor.execute("""
        INSERT INTO notifications (target_user, target_role, message, is_read, timestamp)
        VALUES (?, ?, ?, 0, ?)
    """, (target_user, target_role, message, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()


# --- MULTI-SHEET EXCEL GENERATOR ---
def generate_excel_report(user_name, selected_date, df_daily_tx, df_current_stock):
    wb = openpyxl.Workbook()
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'), right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'), bottom=Side(style='thin', color='D9D9D9')
    )

    ws_master = wb.active
    ws_master.title = "Master Activity Log"
    ws_master.views.sheetView[0].showGridLines = True

    ws_master.merge_cells("A1:I1")
    title1 = ws_master["A1"]
    title1.value = "MASTER SITE INVENTORY ACTIVITY LOG"
    title1.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    title1.fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    title1.alignment = Alignment(horizontal="center", vertical="center")
    ws_master.row_dimensions[1].height = 30

    ws_master["A3"] = f"Report Date: {selected_date}"
    ws_master["A3"].font = Font(bold=True)
    ws_master["A4"] = f"Supervisor: {user_name}"
    ws_master["A4"].font = Font(bold=True)

    headers_master = [
        "Time", "Item Name", "Type", "Quantity", "Issued To / Recipient", 
        "Driver / Delivery", "Project Name", "Purpose / Equipment", "Logged By"
    ]
    for col_num, h_title in enumerate(headers_master, 1):
        cell = ws_master.cell(row=6, column=col_num, value=h_title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    row_idx = 7
    if not df_daily_tx.empty:
        for _, r in df_daily_tx.iterrows():
            ws_master.cell(row=row_idx, column=1, value=str(r.get('timestamp', '')))
            ws_master.cell(row=row_idx, column=2, value=str(r.get('item_name', '')))
            
            t_cell = ws_master.cell(row=row_idx, column=3, value=str(r.get('type', '')))
            t_cell.alignment = Alignment(horizontal="center")
            t_cell.font = Font(bold=True, color="006100" if r.get('type') == 'IN' else "9C0006")

            q_cell = ws_master.cell(row=row_idx, column=4, value=float(r.get('quantity', 0)))
            q_cell.number_format = "#,##0.00"
            
            ws_master.cell(row=row_idx, column=5, value=str(r.get('issued_to', '-')))
            ws_master.cell(row=row_idx, column=6, value=str(r.get('driver_details', '-')))
            ws_master.cell(row=row_idx, column=7, value=str(r.get('project_name', '-')))
            ws_master.cell(row=row_idx, column=8, value=str(r.get('purpose', r.get('remarks', '-'))))
            ws_master.cell(row=row_idx, column=9, value=str(r.get('user_role', '')))

            for c in range(1, 10):
                ws_master.cell(row=row_idx, column=c).border = thin_border
            row_idx += 1
    else:
        ws_master.cell(row=7, column=1, value="No activity recorded for this date.")

    ws_in = wb.create_sheet(title="Stock IN Entries")
    ws_in.views.sheetView[0].showGridLines = True
    ws_in.merge_cells("A1:F1")
    title2 = ws_in["A1"]
    title2.value = "DAILY STOCK IN / RECEIVING REPORT"
    title2.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    title2.fill = PatternFill(start_color="2E75B6", end_color="2E75B6", fill_type="solid")
    title2.alignment = Alignment(horizontal="center", vertical="center")
    ws_in.row_dimensions[1].height = 30

    headers_in = ["Time", "Item Name", "Qty Received", "Driver / Delivery Details", "Logged By", "General Remarks"]
    for col_num, h_title in enumerate(headers_in, 1):
        cell = ws_in.cell(row=4, column=col_num, value=h_title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    df_in = df_daily_tx[df_daily_tx['type'] == 'IN'] if not df_daily_tx.empty else pd.DataFrame()
    row_idx = 5
    if not df_in.empty:
        for _, r in df_in.iterrows():
            ws_in.cell(row=row_idx, column=1, value=str(r.get('timestamp', '')))
            ws_in.cell(row=row_idx, column=2, value=str(r.get('item_name', '')))
            q_cell = ws_in.cell(row=row_idx, column=3, value=float(r.get('quantity', 0)))
            q_cell.number_format = "#,##0.00"
            q_cell.font = Font(bold=True, color="006100")
            
            ws_in.cell(row=row_idx, column=4, value=str(r.get('driver_details', '-')))
            ws_in.cell(row=row_idx, column=5, value=str(r.get('user_role', '')))
            ws_in.cell(row=row_idx, column=6, value=str(r.get('remarks', '-')))

            for c in range(1, 7):
                ws_in.cell(row=row_idx, column=c).border = thin_border
            row_idx += 1
    else:
        ws_in.cell(row=5, column=1, value="No Stock IN entries for this date.")

    ws_out = wb.create_sheet(title="Stock OUT Entries")
    ws_out.views.sheetView[0].showGridLines = True
    ws_out.merge_cells("A1:H1")
    title3 = ws_out["A1"]
    title3.value = "DAILY STOCK OUT / ISSUANCE REPORT"
    title3.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    title3.fill = PatternFill(start_color="C65911", end_color="C65911", fill_type="solid")
    title3.alignment = Alignment(horizontal="center", vertical="center")
    ws_out.row_dimensions[1].height = 30

    headers_out = ["Time", "Item Name", "Qty Issued", "Issued To", "Driver / Transport", "Project Name", "Purpose / Usage", "Logged By"]
    for col_num, h_title in enumerate(headers_out, 1):
        cell = ws_out.cell(row=4, column=col_num, value=h_title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="833C0C", end_color="833C0C", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    df_out = df_daily_tx[df_daily_tx['type'] == 'OUT'] if not df_daily_tx.empty else pd.DataFrame()
    row_idx = 5
    if not df_out.empty:
        for _, r in df_out.iterrows():
            ws_out.cell(row=row_idx, column=1, value=str(r.get('timestamp', '')))
            ws_out.cell(row=row_idx, column=2, value=str(r.get('item_name', '')))
            q_cell = ws_out.cell(row=row_idx, column=3, value=float(r.get('quantity', 0)))
            q_cell.number_format = "#,##0.00"
            q_cell.font = Font(bold=True, color="9C0006")
            
            ws_out.cell(row=row_idx, column=4, value=str(r.get('issued_to', '-')))
            ws_out.cell(row=row_idx, column=5, value=str(r.get('driver_details', '-')))
            ws_out.cell(row=row_idx, column=6, value=str(r.get('project_name', '-')))
            ws_out.cell(row=row_idx, column=7, value=str(r.get('purpose', r.get('remarks', '-'))))
            ws_out.cell(row=row_idx, column=8, value=str(r.get('user_role', '')))

            for c in range(1, 9):
                ws_out.cell(row=row_idx, column=c).border = thin_border
            row_idx += 1
    else:
        ws_out.cell(row=5, column=1, value="No Stock OUT entries for this date.")

    ws_cat = wb.create_sheet(title="Categorized Stock Balance")
    ws_cat.views.sheetView[0].showGridLines = True
    ws_cat.merge_cells("A1:D1")
    title4 = ws_cat["A1"]
    title4.value = "SITE INVENTORY BALANCE (BY CATEGORY)"
    title4.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    title4.fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    title4.alignment = Alignment(horizontal="center", vertical="center")
    ws_cat.row_dimensions[1].height = 30

    c_row = 3
    if not df_current_stock.empty:
        for cat in sorted(df_current_stock['category'].unique()):
            ws_cat.merge_cells(start_row=c_row, start_column=1, end_row=c_row, end_column=4)
            cat_cell = ws_cat.cell(row=c_row, column=1, value=str(cat).upper())
            cat_cell.font = Font(bold=True, color="FFFFFF")
            cat_cell.fill = PatternFill(start_color="595959", end_color="595959", fill_type="solid")
            cat_cell.alignment = Alignment(horizontal="left", vertical="center")
            c_row += 1

            sub_headers = ["Item Name", "Current Stock", "Min Alert Threshold", "Unit"]
            for col_num, h_title in enumerate(sub_headers, 1):
                cell = ws_cat.cell(row=c_row, column=col_num, value=h_title)
                cell.font = Font(bold=True, color="333333")
                cell.fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")

            c_row += 1
            for _, r in df_current_stock[df_current_stock['category'] == cat].iterrows():
                ws_cat.cell(row=c_row, column=1, value=str(r['item_name']))
                
                stk_cell = ws_cat.cell(row=c_row, column=2, value=float(r['current_stock']))
                stk_cell.number_format = "#,##0.00"

                thresh_cell = ws_cat.cell(row=c_row, column=3, value=float(r['min_threshold']))
                thresh_cell.number_format = "#,##0.00"

                ws_cat.cell(row=c_row, column=4, value=str(r['unit']))

                if float(r['current_stock']) <= float(r['min_threshold']):
                    stk_cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                    stk_cell.font = Font(color="9C0006", bold=True)

                for col_num in range(1, 5):
                    ws_cat.cell(row=c_row, column=col_num).border = thin_border
                c_row += 1
            c_row += 1

    for sheet in [ws_master, ws_in, ws_out, ws_cat]:
        for col in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.row != 1 and cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            sheet.column_dimensions[col_letter].width = max(max_len + 4, 12)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


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
    user_name = st.session_state["username"]
    user_role = st.session_state["user_role"]

    unread_query = """
        SELECT COUNT(*) FROM notifications 
        WHERE is_read = 0 AND (target_user = ? OR target_role = ?)
    """
    unread_count = cursor.execute(unread_query, (user_name, user_role)).fetchone()[0]

    bell_label = f"🔔 ({unread_count})" if unread_count > 0 else "🔔"

    header_col1, header_col2 = st.columns([0.8, 0.2])
    with header_col1:
        st.title("🏗️ Construction Site Inventory System")
    with header_col2:
        with st.popover(bell_label, use_container_width=True):
            st.markdown(f"### Notifications for `{user_name}`")
            
            notifs = cursor.execute("""
                SELECT id, message, timestamp, is_read FROM notifications 
                WHERE target_user = ? OR target_role = ?
                ORDER BY id DESC LIMIT 15
            """, (user_name, user_role)).fetchall()

            if notifs:
                if st.button("Mark All as Read", key="read_all_notifs"):
                    cursor.execute("""
                        UPDATE notifications SET is_read = 1 
                        WHERE target_user = ? OR target_role = ?
                    """, (user_name, user_role))
                    conn.commit()
                    st.rerun()

                st.markdown("---")
                for n_id, msg, ts, is_r in notifs:
                    badge = "🟢 **NEW** " if is_r == 0 else ""
                    st.markdown(f"{badge}*{ts}*\n\n{msg}")
                    st.divider()
            else:
                st.info("No notifications yet.")

    # --- SIDEBAR NAVIGATION & USER INFO ---
    st.sidebar.markdown(f"**Logged in as:** `{user_name}`")
    st.sidebar.markdown(f"**Role:** `{user_role}`")
    st.sidebar.markdown("---")

    if user_role == "Materials Supervisor":
        nav_options = [
            "📋 Current Inventory", 
            "📊 Analytics",
            "+ Stock In", 
            "- Stock Out",
            "📦 Physical Inventory Audit",
            "📜 My Log & Request Edits",
            "📅 Daily Report (Excel)",
            "⏰ Reminders",
            "📅 Schedule"
        ]
    else:  # Head Office Admin
        pending_requests_count = cursor.execute("SELECT COUNT(*) FROM edit_requests WHERE status = 'PENDING'").fetchone()[0]
        pending_variances_count = cursor.execute("SELECT COUNT(*) FROM physical_inventory_counts WHERE sync_status = 'PENDING_ADMIN_REVIEW'").fetchone()[0]
        
        edit_option_title = f"✏️ Edit Requests ({pending_requests_count})" if pending_requests_count > 0 else "✏️ Edit Requests"
        audit_option_title = f"📦 Physical Inventory Audit ({pending_variances_count})" if pending_variances_count > 0 else "📦 Physical Inventory Audit"

        nav_options = [
            "📋 Current Inventory", 
            "📊 Analytics",
            "+ Stock In", 
            "- Stock Out", 
            audit_option_title,
            edit_option_title,
            "➕ Manage Master Items", 
            "📜 Master Audit Log",
            "👤 Manage Users",
            "⏰ Reminders",
            "📅 Schedule"
        ]

    st.sidebar.markdown("### 📌 Navigation")
    selected_menu = st.sidebar.radio("Go to:", nav_options)

    st.sidebar.markdown("---")
    if st.sidebar.button("Log Out", use_container_width=True):
        st.session_state["logged_in"] = False
        st.session_state["username"] = None
        st.session_state["user_role"] = None
        st.rerun()

    # --- ROUTING BASED ON SIDEBAR SELECTION ---

    # --- MENU 1: CURRENT INVENTORY ---
    if selected_menu == "📋 Current Inventory":
        st.subheader("📋 Current Available Stocks")

        df_items = pd.read_sql_query(
            "SELECT category, item_name, current_stock, min_threshold, unit FROM master_items ORDER BY category ASC, item_name ASC", 
            conn
        )
        
        if not df_items.empty:
            def highlight_low_stock(row):
                return ['background-color: #ffcccc' if row['current_stock'] <= row['min_threshold'] else '' for _ in row]

            categories = df_items['category'].unique()
            for cat in categories:
                st.markdown(f"### 📂 **{cat.upper()}**")
                
                df_cat = df_items[df_items['category'] == cat][['item_name', 'current_stock', 'min_threshold', 'unit']]

                st.dataframe(
                    df_cat.style.apply(highlight_low_stock, axis=1),
                    column_config={
                        "item_name": st.column_config.Column("Item Name", pinned=True, width="medium"),
                        "current_stock": st.column_config.NumberColumn("Current Stock", format="%.2f"),
                        "min_threshold": st.column_config.NumberColumn("Min. Threshold", format="%.2f"),
                        "unit": st.column_config.Column("Unit")
                    },
                    hide_index=True,
                    use_container_width=True
                )
        else:
            st.info("No items found in Master Inventory.")

    # --- MENU 2: ANALYTICS DASHBOARD ---
    elif selected_menu == "📊 Analytics":
        st.subheader("📊 Inventory Analytics & Operational Insights")

        filter_col1, filter_col2 = st.columns([0.4, 0.6])
        with filter_col1:
            time_view = st.selectbox(
                "🗓️ Select Time View:", 
                ["Daily (Last 14 Days)", "Weekly (Last 8 Weeks)", "Monthly (Last 12 Months)", "All Time / Year-To-Date"]
            )
        
        today = datetime.now()
        
        if time_view == "Daily (Last 14 Days)":
            start_date = today - timedelta(days=14)
            freq_rule = "D"
            date_format = "%Y-%m-%d"
        elif time_view == "Weekly (Last 8 Weeks)":
            start_date = today - timedelta(weeks=8)
            freq_rule = "W-MON"
            date_format = "Week %U, %Y"
        elif time_view == "Monthly (Last 12 Months)":
            start_date = today - timedelta(days=365)
            freq_rule = "ME"
            date_format = "%b %Y"
        else:
            start_date = datetime(today.year, 1, 1)
            freq_rule = "ME"
            date_format = "%b %Y"

        df_inv = pd.read_sql_query("SELECT item_name, category, unit, current_stock, min_threshold FROM master_items", conn)
        df_tx_all = pd.read_sql_query("SELECT timestamp, item_name, type, quantity, user_role, driver_details, project_name FROM transactions", conn)

        if df_inv.empty:
            st.warning("No inventory data available for analytics.")
        else:
            if not df_tx_all.empty:
                df_tx_all['dt_timestamp'] = pd.to_datetime(df_tx_all['timestamp'])
                df_filtered_tx = df_tx_all[df_tx_all['dt_timestamp'] >= start_date].copy()
            else:
                df_filtered_tx = pd.DataFrame()

            total_skus = len(df_inv)
            low_stock_items = df_inv[df_inv['current_stock'] <= df_inv['min_threshold']]
            low_stock_count = len(low_stock_items)

            total_received_qty = df_filtered_tx[df_filtered_tx['type'] == 'IN']['quantity'].sum() if not df_filtered_tx.empty else 0
            total_issued_qty = df_filtered_tx[df_filtered_tx['type'] == 'OUT']['quantity'].sum() if not df_filtered_tx.empty else 0

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Active SKUs", total_skus)
            m2.metric("Low Stock Alerts", low_stock_count, delta=f"{low_stock_count} Critical", delta_color="inverse" if low_stock_count > 0 else "off")
            m3.metric(f"Received (IN) [{time_view.split()[0]}]", f"{total_received_qty:,.1f}")
            m4.metric(f"Issued (OUT) [{time_view.split()[0]}]", f"{total_issued_qty:,.1f}")

            st.markdown("---")

            if low_stock_count > 0:
                st.error(f"⚠️ **Attention Required:** {low_stock_count} item(s) are at or below safety threshold!")
                st.dataframe(low_stock_items[['item_name', 'category', 'current_stock', 'min_threshold', 'unit']], use_container_width=True)
            else:
                st.success("✅ Stock levels across all items are healthy.")

            st.markdown("---")

            st.markdown(f"##### 📈 Stock Movement Trends ({time_view})")
            if not df_filtered_tx.empty:
                df_filtered_tx_grouped = df_filtered_tx.set_index('dt_timestamp')
                trend_in = df_filtered_tx_grouped[df_filtered_tx_grouped['type'] == 'IN'].resample(freq_rule)['quantity'].sum()
                trend_out = df_filtered_tx_grouped[df_filtered_tx_grouped['type'] == 'OUT'].resample(freq_rule)['quantity'].sum()

                df_trend = pd.DataFrame({'Stock IN': trend_in, 'Stock OUT': trend_out}).fillna(0)
                df_trend.index = df_trend.index.strftime(date_format)

                st.line_chart(df_trend, use_container_width=True)
            else:
                st.info(f"No transactions recorded for the selected time window ({time_view}).")

            st.markdown("---")

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("##### 📦 Current Stock vs. Threshold (Top 15)")
                df_chart_inv = df_inv.sort_values(by='current_stock', ascending=False).head(15)
                st.bar_chart(df_chart_inv, x="item_name", y=["current_stock", "min_threshold"], use_container_width=True)

            with c2:
                st.markdown("##### 🏷️ Category-wise SKU Count")
                cat_summary = df_inv.groupby("category")["item_name"].count().reset_index()
                cat_summary.columns = ["Category", "Total Items"]
                st.bar_chart(cat_summary, x="Category", y="Total Items", use_container_width=True)

    # --- MENU 3: STOCK IN ---
    elif selected_menu == "+ Stock In":
        st.subheader("Log Stock Delivery (Receiving)")
        items = [row[0] for row in cursor.execute("SELECT item_name FROM master_items").fetchall()]
        if items:
            col_a, col_b = st.columns(2)
            with col_a:
                item_selected = st.selectbox("Select Item to Receive", items, key="in_item")
                qty_in = st.number_input("Quantity Received", min_value=0.1, step=1.0, key="in_qty")
            with col_b:
                driver_info = st.text_input("Driver / Delivery Details / DR #", placeholder="e.g. John Doe (Plate: ABC-123, DR #9876)", key="in_driver")
                remarks_in = st.text_input("General Remarks", placeholder="e.g. Verified good condition, unloaded at Bay 2", key="in_rem")

            st.markdown("### 📷 Delivery Photo / Receipt Proof")
            photo_mode = st.radio("Choose Photo Upload Method:", ["Camera Capture", "Upload File"], horizontal=True, key="in_photo_mode")
            
            image_bytes = None
            if photo_mode == "Camera Capture":
                camera_photo = st.camera_input("Take a picture of the delivery / receipt", key="in_camera")
                if camera_photo:
                    image_bytes = camera_photo.getvalue()
            else:
                uploaded_file = st.file_uploader("Upload Delivery Receipt / Photo", type=["jpg", "jpeg", "png"], key="in_upload")
                if uploaded_file:
                    image_bytes = uploaded_file.getvalue()

            if st.button("Submit Stock In", use_container_width=True):
                saved_photo_path = None
                if image_bytes:
                    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                    file_filename = f"uploads/delivery_{timestamp_str}.jpg"
                    with open(file_filename, "wb") as f:
                        f.write(image_bytes)
                    saved_photo_path = file_filename

                cursor.execute("UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?", (qty_in, item_selected))
                cursor.execute("""
                    INSERT INTO transactions (timestamp, item_name, type, quantity, user_role, driver_details, remarks, photo_path) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item_selected, "IN", qty_in, user_name, driver_info, remarks_in, saved_photo_path))
                conn.commit()
                st.success(f"Successfully recorded receiving {qty_in} of {item_selected}!")
                st.rerun()
        else:
            st.warning("Please add items to Master Inventory first.")

    # --- MENU 4: STOCK OUT ---
    elif selected_menu == "- Stock Out":
        st.subheader("Log Stock Issuance (Stock OUT)")
        items = [row[0] for row in cursor.execute("SELECT item_name FROM master_items").fetchall()]
        if items:
            col_x, col_y = st.columns(2)
            with col_x:
                item_selected = st.selectbox("Select Item to Issue", items, key="out_item")
                qty_out = st.number_input("Quantity Issued", min_value=0.1, step=1.0, key="out_qty")
                issued_to = st.text_input("Issued To (Person / Subcontractor)", placeholder="e.g. Foreman Mike / Subcon ABC", key="out_issued_to")
            
            with col_y:
                driver_out = st.text_input("Driver / Transport Vehicle", placeholder="e.g. Driver Bob (Dump Truck #2)", key="out_driver")
                project_name = st.text_input("Project Name / Site Location", placeholder="e.g. Tower B - 5th Floor", key="out_project")
                purpose = st.text_input("Purpose / Equipment Usage", placeholder="e.g. Concrete Pouring Foundation", key="out_purpose")

            current_stk, min_thresh = cursor.execute("SELECT current_stock, min_threshold FROM master_items WHERE item_name = ?", (item_selected,)).fetchone()
            st.caption(f"Current Stock Available: **{current_stk}** | Min Alert Threshold: **{min_thresh}**")

            if st.button("Submit Stock Out", use_container_width=True):
                if qty_out > current_stk:
                    st.error(f"Cannot issue {qty_out}. Current stock is only {current_stk}.")
                else:
                    cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", (qty_out, item_selected))
                    cursor.execute("""
                        INSERT INTO transactions (timestamp, item_name, type, quantity, user_role, driver_details, issued_to, project_name, purpose) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item_selected, "OUT", qty_out, user_name, driver_out, issued_to, project_name, purpose))
                    conn.commit()
                    
                    new_stk = current_stk - qty_out
                    if new_stk <= min_thresh:
                        create_notification(f"⚠️ LOW STOCK ALERT: {item_selected} stock dropped to {new_stk}.", target_role="Head Office")
                    
                    st.success(f"Successfully issued {qty_out} of {item_selected}!")
                    st.rerun()
        else:
            st.warning("Please add items to Master Inventory first.")

    # --- MENU 5: PHYSICAL INVENTORY AUDIT ---
    elif "Physical Inventory Audit" in selected_menu:
        st.subheader("📦 Physical Inventory Audit & Variance Resolution")

        if user_role == "Materials Supervisor":
            st.markdown("##### 📝 Perform Physical Stock Count")
            audit_date = st.date_input("Audit Date", datetime.now()).strftime("%Y-%m-%d")
            
            df_curr = pd.read_sql_query("SELECT item_name, category, current_stock, unit FROM master_items ORDER BY category, item_name", conn)
            
            with st.form("audit_form"):
                counts = {}
                st.markdown("Enter actual physical counts for items below:")
                for idx, row in df_curr.iterrows():
                    c1, c2, c3 = st.columns([0.4, 0.3, 0.3])
                    c1.write(f"**{row['item_name']}** ({row['category']})")
                    c2.caption(f"System: {row['current_stock']} {row['unit']}")
                    counts[row['item_name']] = c3.number_input(f"Actual Count ({row['unit']})", min_value=0.0, value=float(row['current_stock']), key=f"audit_{idx}")
                
                sup_remarks = st.text_area("Supervisor Audit Notes / Remarks")
                submit_audit = st.form_submit_button("Submit Audit Counts")

            if submit_audit:
                variances_found = 0
                for item_name, phys_qty in counts.items():
                    sys_qty = float(df_curr[df_curr['item_name'] == item_name]['current_stock'].values[0])
                    unit = str(df_curr[df_curr['item_name'] == item_name]['unit'].values[0])
                    var = phys_qty - sys_qty

                    sync_status = "SYNCED" if var == 0 else "PENDING_ADMIN_REVIEW"
                    if var != 0:
                        variances_found += 1

                    cursor.execute("""
                        INSERT INTO physical_inventory_counts 
                        (audit_date, item_name, system_stock, physical_stock, variance, unit, counted_by, supervisor_remarks, sync_status, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (audit_date, item_name, sys_qty, phys_qty, var, unit, user_name, sup_remarks, sync_status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

                conn.commit()
                if variances_found > 0:
                    create_notification(f"⚠️ Audit submitted by {user_name} with {variances_found} stock variance(s) needing review.", target_role="Head Office")
                    st.warning(f"Audit submitted! {variances_found} variances flagged for Head Office review.")
                else:
                    st.success("Audit submitted successfully with zero stock variances!")
                st.rerun()

        else: # Head Office Admin Review
            st.markdown("##### 🔍 Pending Audit Variances Review")
            df_pending_audits = pd.read_sql_query("""
                SELECT id, audit_date, item_name, system_stock, physical_stock, variance, unit, counted_by, supervisor_remarks, timestamp 
                FROM physical_inventory_counts 
                WHERE sync_status = 'PENDING_ADMIN_REVIEW'
            """, conn)

            if df_pending_audits.empty:
                st.info("No pending audit variances require review.")
            else:
                for _, r in df_pending_audits.iterrows():
                    with st.expander(f"⚠️ Variance: {r['item_name']} | Diff: {r['variance']:+} {r['unit']} (Audited: {r['audit_date']})"):
                        st.write(f"**Counted By:** {r['counted_by']} | **Date:** {r['timestamp']}")
                        st.write(f"**System Stock:** {r['system_stock']} | **Physical Count:** {r['physical_stock']}")
                        st.write(f"**Supervisor Remarks:** {r['supervisor_remarks']}")

                        adj_stock = st.number_input(f"Final Resolved Stock Level ({r['unit']})", value=float(r['physical_stock']), key=f"res_{r['id']}")
                        admin_expl = st.text_input("Resolution Explanation", placeholder="e.g. Approved adjustment due to physical damage", key="expl_{r['id']}")

                        c_a, c_b = st.columns(2)
                        if c_a.button("Approve & Adjust Stock", key=f"app_aud_{r['id']}"):
                            cursor.execute("UPDATE master_items SET current_stock = ? WHERE item_name = ?", (adj_stock, r['item_name']))
                            cursor.execute("""
                                UPDATE physical_inventory_counts 
                                SET sync_status = 'RESOLVED', resolved_by = ?, resolved_stock = ?, admin_explanation = ?
                                WHERE id = ?
                            """, (user_name, adj_stock, admin_expl, r['id']))
                            conn.commit()
                            create_notification(f"✅ Stock variance for {r['item_name']} resolved by Head Office.", target_user=r['counted_by'])
                            st.success(f"Stock adjusted for {r['item_name']}.")
                            st.rerun()

                        if c_b.button("Reject Variance Entry", key=f"rej_aud_{r['id']}"):
                            cursor.execute("UPDATE physical_inventory_counts SET sync_status = 'REJECTED', resolved_by = ?, admin_explanation = ? WHERE id = ?", (user_name, admin_expl, r['id']))
                            conn.commit()
                            st.info("Variance report rejected.")
                            st.rerun()

    # --- MENU 6: MY LOG & REQUEST EDITS (SUPERVISOR) / EDIT REQUESTS (ADMIN) ---
    elif "Edit Requests" in selected_menu or selected_menu == "📜 My Log & Request Edits":
        if user_role == "Materials Supervisor":
            st.subheader("📜 My Submitted Transactions & Edit Requests")
            df_my_tx = pd.read_sql_query("""
                SELECT id, timestamp, item_name, type, quantity, issued_to, driver_details, project_name, purpose, remarks, edit_status 
                FROM transactions WHERE user_role = ? ORDER BY id DESC
            """, conn, params=(user_name,))

            if not df_my_tx.empty:
                st.dataframe(df_my_tx, use_container_width=True)
                st.markdown("---")
                st.markdown("##### ✏️ Request Transaction Correction")
                
                tx_ids = df_my_tx['id'].tolist()
                selected_tx_id = st.selectbox("Select Transaction ID to Edit", tx_ids)
                
                tx_detail = df_my_tx[df_my_tx['id'] == selected_tx_id].iloc[0]
                st.json(tx_detail.to_dict())

                req_reason = st.text_area("Reason for Edit Request")
                new_qty = st.number_input("Proposed Correct Quantity", value=float(tx_detail['quantity']))
                new_remarks = st.text_input("Proposed Remarks / Explanation", value=str(tx_detail['remarks'] or ''))

                if st.button("Submit Edit Request to Admin"):
                    orig_data = json.dumps(tx_detail.to_dict())
                    prop_data = json.dumps({"quantity": new_qty, "remarks": new_remarks})

                    cursor.execute("""
                        INSERT INTO edit_requests (transaction_id, requested_by, reason, original_data, proposed_data, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (selected_tx_id, user_name, req_reason, orig_data, prop_data, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    cursor.execute("UPDATE transactions SET edit_status = 'PENDING_EDIT' WHERE id = ?", (selected_tx_id,))
                    conn.commit()

                    create_notification(f"✏️ New edit request for Tx #{selected_tx_id} submitted by {user_name}.", target_role="Head Office")
                    st.success("Edit request submitted successfully!")
                    st.rerun()
            else:
                st.info("No transaction logs recorded yet.")

        else: # Head Office Admin Review
            st.subheader("✏️ Review Pending Transaction Edit Requests")
            df_edits = pd.read_sql_query("""
                SELECT id, transaction_id, requested_by, reason, original_data, proposed_data, timestamp 
                FROM edit_requests WHERE status = 'PENDING'
            """, conn)

            if df_edits.empty:
                st.info("No pending transaction edit requests.")
            else:
                for _, r in df_edits.iterrows():
                    with st.expander(f"Edit Request #{r['id']} for Tx #{r['transaction_id']} by {r['requested_by']}"):
                        st.write(f"**Reason:** {r['reason']}")
                        col_o, col_p = st.columns(2)
                        orig = json.loads(r['original_data'])
                        prop = json.loads(r['proposed_data'])
                        
                        col_o.markdown("**Original Data:**")
                        col_o.json(orig)
                        col_p.markdown("**Proposed Changes:**")
                        col_p.json(prop)

                        rev_remarks = st.text_input("Admin Remarks", key=f"rev_rem_{r['id']}")
                        
                        btn_col1, btn_col2 = st.columns(2)
                        if btn_col1.button("Approve Request", key=f"app_req_{r['id']}"):
                            # Revert old qty effect on current stock
                            item_name = orig['item_name']
                            tx_type = orig['type']
                            old_qty = float(orig['quantity'])
                            new_qty = float(prop['quantity'])
                            diff_qty = new_qty - old_qty

                            if tx_type == 'IN':
                                cursor.execute("UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?", (diff_qty, item_name))
                            else:
                                cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", (diff_qty, item_name))

                            cursor.execute("UPDATE transactions SET quantity = ?, remarks = ?, edit_status = 'EDITED' WHERE id = ?", (new_qty, prop['remarks'], r['transaction_id']))
                            cursor.execute("UPDATE edit_requests SET status = 'APPROVED', review_remarks = ? WHERE id = ?", (rev_remarks, r['id']))
                            conn.commit()

                            create_notification(f"✅ Your edit request for Tx #{r['transaction_id']} was APPROVED.", target_user=r['requested_by'])
                            st.success("Edit request approved and stock adjusted!")
                            st.rerun()

                        if btn_col2.button("Reject Request", key=f"rej_req_{r['id']}"):
                            cursor.execute("UPDATE transactions SET edit_status = 'NORMAL' WHERE id = ?", (r['transaction_id'],))
                            cursor.execute("UPDATE edit_requests SET status = 'REJECTED', review_remarks = ? WHERE id = ?", (rev_remarks, r['id']))
                            conn.commit()

                            create_notification(f"❌ Your edit request for Tx #{r['transaction_id']} was REJECTED.", target_user=r['requested_by'])
                            st.info("Edit request rejected.")
                            st.rerun()

    # --- MENU 7: MANAGE MASTER ITEMS (ADMIN) ---
    elif selected_menu == "➕ Manage Master Items":
        st.subheader("➕ Master Item Inventory Management")

        tab_add, tab_edit = st.tabs(["Add New Item", "Update Existing Item"])
        
        with tab_add:
            with st.form("add_item_form"):
                new_name = st.text_input("Item Name")
                new_cat = st.selectbox("Category", ["1. Fuel & Oils", "2. Construction Materials", "3. Steel / Rebar", "4A. Nails & Fasteners", "4B. Cutting & Grinding Consumables", "4C. Welding Supplies & PPE", "4D. General Site Supplies"])
                new_unit = st.text_input("Unit of Measure (e.g., Pcs, Liters, Kilos, Bags)")
                new_stock = st.number_input("Initial Stock Quantity", min_value=0.0)
                new_thresh = st.number_input("Minimum Alert Threshold", min_value=0.0)
                
                if st.form_submit_button("Add Master Item"):
                    try:
                        cursor.execute("INSERT INTO master_items (item_name, category, unit, current_stock, min_threshold) VALUES (?, ?, ?, ?, ?)",
                                       (new_name.strip(), new_cat, new_unit.strip(), new_stock, new_thresh))
                        conn.commit()
                        st.success(f"Successfully added '{new_name}' to master inventory!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("An item with this name already exists!")

        with tab_edit:
            df_m = pd.read_sql_query("SELECT * FROM master_items", conn)
            if not df_m.empty:
                item_to_mod = st.selectbox("Select Item to Update", df_m['item_name'].tolist())
                row_mod = df_m[df_m['item_name'] == item_to_mod].iloc[0]

                mod_cat = st.text_input("Category", value=row_mod['category'])
                mod_unit = st.text_input("Unit", value=row_mod['unit'])
                mod_thresh = st.number_input("Min Alert Threshold", value=float(row_mod['min_threshold']))

                if st.button("Save Item Changes"):
                    cursor.execute("UPDATE master_items SET category = ?, unit = ?, min_threshold = ? WHERE id = ?", (mod_cat, mod_unit, mod_thresh, int(row_mod['id'])))
                    conn.commit()
                    st.success(f"Updated {item_to_mod}!")
                    st.rerun()

    # --- MENU 8: MASTER AUDIT LOG (ADMIN) ---
    elif selected_menu == "📜 Master Audit Log":
        st.subheader("📜 Master Activity & Audit Log")
        df_master_log = pd.read_sql_query("SELECT * FROM transactions ORDER BY id DESC", conn)
        st.dataframe(df_master_log, use_container_width=True)

    # --- MENU 9: DAILY REPORT EXCEL EXPORT ---
    elif selected_menu == "📅 Daily Report (Excel)":
        st.subheader("📅 Export Daily Inventory Report (Excel)")
        
        rep_date = st.date_input("Select Report Date", datetime.now()).strftime("%Y-%m-%d")
        
        df_daily_tx = pd.read_sql_query("""
            SELECT timestamp, item_name, type, quantity, issued_to, driver_details, project_name, purpose, remarks, user_role 
            FROM transactions WHERE DATE(timestamp) = ? ORDER BY id ASC
        """, conn, params=(rep_date,))

        df_curr_stock = pd.read_sql_query("SELECT category, item_name, current_stock, min_threshold, unit FROM master_items ORDER BY category, item_name", conn)

        st.info(f"Transactions found for {rep_date}: **{len(df_daily_tx)}**")

        excel_data = generate_excel_report(user_name, rep_date, df_daily_tx, df_curr_stock)
        
        st.download_button(
            label="📥 Download Structured Excel Report",
            data=excel_data,
            file_name=f"Inventory_Report_{rep_date}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    # --- MENU 10: MANAGE USERS (ADMIN) ---
    elif selected_menu == "👤 Manage Users":
        st.subheader("👤 User Account Management")
        
        with st.form("create_user_form"):
            st.markdown("##### Create New User Account")
            u_name = st.text_input("Username")
            u_pass = st.text_input("Password", type="password")
            u_role = st.selectbox("Role", ["Materials Supervisor", "Head Office"])
            
            if st.form_submit_button("Register User"):
                try:
                    cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (u_name.strip(), u_pass.strip(), u_role))
                    conn.commit()
                    st.success(f"User account '{u_name}' created successfully!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Username already exists!")

        st.markdown("---")
        st.markdown("##### Existing User Accounts")
        df_users = pd.read_sql_query("SELECT id, username, role FROM users", conn)
        st.dataframe(df_users, use_container_width=True)

    # --- MENU 11: REMINDERS ---
    elif selected_menu == "⏰ Reminders":
        st.subheader("⏰ Reminders & Task Tracker")
        
        c_r1, c_r2 = st.columns([0.4, 0.6])
        with c_r1:
            st.markdown("##### ➕ Add New Reminder")
            rem_title = st.text_input("Task Title")
            rem_due = st.date_input("Due Date", datetime.now()).strftime("%Y-%m-%d")
            rem_prio = st.selectbox("Priority Level", ["Low", "Medium", "High", "Urgent"])

            if st.button("Save Reminder"):
                cursor.execute("""
                    INSERT INTO reminders (user_name, title, due_date, priority, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_name, rem_title, rem_due, rem_prio, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
                st.success("Reminder added!")
                st.rerun()

        with c_r2:
            st.markdown("##### 📌 Active Tasks")
            df_rems = pd.read_sql_query("SELECT id, title, due_date, priority, status FROM reminders WHERE user_name = ? AND status = 'PENDING' ORDER BY due_date ASC", conn, params=(user_name,))
            if not df_rems.empty:
                for _, r in df_rems.iterrows():
                    rc1, rc2 = st.columns([0.8, 0.2])
                    rc1.write(f"**[{r['priority']}]** {r['title']} *(Due: {r['due_date']})*")
                    if rc2.button("Done", key=f"rem_{r['id']}"):
                        cursor.execute("UPDATE reminders SET status = 'COMPLETED' WHERE id = ?", (r['id'],))
                        conn.commit()
                        st.rerun()
            else:
                st.info("No active pending reminders.")

    # --- MENU 12: SCHEDULE ---
    elif selected_menu == "📅 Schedule":
        st.subheader("📅 Site Events & Delivery Schedule")
        
        with st.form("sch_form"):
            st.markdown("##### ➕ Schedule Event / Delivery")
            s_title = st.text_input("Event / Delivery Title")
            s_date = st.date_input("Event Date", datetime.now()).strftime("%Y-%m-%d")
            col_t1, col_t2 = st.columns(2)
            s_start = col_t1.time_input("Start Time", time(8, 0)).strftime("%H:%M")
            s_end = col_t2.time_input("End Time", time(17, 0)).strftime("%H:%M")
            s_loc = st.text_input("Location / Gate Details")
            s_notes = st.text_area("Notes / Specifications")

            if st.form_submit_button("Add to Schedule"):
                cursor.execute("""
                    INSERT INTO schedules (user_name, title, event_date, start_time, end_time, location_details, notes, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (user_name, s_title, s_date, s_start, s_end, s_loc, s_notes, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
                st.success("Event scheduled!")
                st.rerun()

        st.markdown("---")
        st.markdown("##### 📅 Upcoming Scheduled Events")
        df_sch = pd.read_sql_query("SELECT title, event_date, start_time, end_time, location_details, notes FROM schedules WHERE event_date >= DATE('now') ORDER BY event_date ASC, start_time ASC", conn)
        
        if not df_sch.empty:
            st.dataframe(df_sch, use_container_width=True)
        else:
            st.info("No upcoming events scheduled.")
