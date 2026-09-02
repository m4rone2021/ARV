import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
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

    # SHEET 1: MASTER LOG
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

    # SHEET 2: STOCK IN RECORD
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

    # SHEET 3: STOCK OUT RECORD
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

    # SHEET 4: CATEGORIZED STOCK BALANCE
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
        st.space()
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

    # Define Navigation Options based on Role
    if user_role == "Materials Supervisor":
        nav_options = [
            "📋 Current Inventory", 
            "📊 Analytics",
            "+ Stock In", 
            "- Stock Out",
            "📜 My Log & Request Edits",
            "📅 Daily Report (Excel)"
        ]
    else:  # Head Office Admin
        pending_requests_count = cursor.execute("SELECT COUNT(*) FROM edit_requests WHERE status = 'PENDING'").fetchone()[0]
        edit_option_title = f"✏️ Edit Requests ({pending_requests_count})" if pending_requests_count > 0 else "✏️ Edit Requests"

        nav_options = [
            "📋 Current Inventory", 
            "📊 Analytics",
            "+ Stock In", 
            "- Stock Out", 
            edit_option_title,
            "➕ Manage Master Items", 
            "📜 Master Audit Log",
            "👤 Manage Users"
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
                        "item_name": st.column_config.Column(
                            "Item Name",
                            pinned=True,
                            width="medium"
                        ),
                        "current_stock": st.column_config.NumberColumn(
                            "Current Stock",
                            format="%.2f"
                        ),
                        "min_threshold": st.column_config.NumberColumn(
                            "Min. Threshold",
                            format="%.2f"
                        ),
                        "unit": st.column_config.Column(
                            "Unit"
                        )
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

            st.markdown("---")

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"##### 🔥 Top Issued Items ({time_view.split()[0]})")
                if not df_filtered_tx.empty and not df_filtered_tx[df_filtered_tx['type'] == 'OUT'].empty:
                    df_out_top = df_filtered_tx[df_filtered_tx['type'] == 'OUT'].groupby('item_name')['quantity'].sum().reset_index()
                    df_out_top = df_out_top.sort_values(by='quantity', ascending=False).head(10)
                    st.dataframe(df_out_top, use_container_width=True)
                else:
                    st.caption("No Stock OUT transactions logged in this period.")

            with col_b:
                st.markdown(f"##### 🚚 Active Drivers & Transport Logins ({time_view.split()[0]})")
                if not df_filtered_tx.empty and df_filtered_tx['driver_details'].notnull().any():
                    df_drivers = df_filtered_tx[df_filtered_tx['driver_details'] != ''].groupby('driver_details')['timestamp'].count().reset_index()
                    df_drivers.columns = ['Driver / Vehicle Details', 'Trips Logged']
                    df_drivers = df_drivers.sort_values(by='Trips Logged', ascending=False).head(10)
                    st.dataframe(df_drivers, use_container_width=True)
                else:
                    st.caption("No driver entries logged in this period.")

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
                driver_out = st.text_input("Driver / Transport Vehicle", placeholder="e.g. Driver Bob (Dump Truck #02)", key="out_driver")
                proj_name = st.text_input("Project / Site Name", placeholder="e.g. Tower B - 12th Floor", key="out_proj")
                purpose = st.text_input("Purpose / Equipment ID", placeholder="e.g. Excavator #04 Refueling / Slab Pouring", key="out_purpose")

            if st.button("Submit Stock Out", use_container_width=True):
                curr_stock = cursor.execute("SELECT current_stock FROM master_items WHERE item_name = ?", (item_selected,)).fetchone()[0]
                if qty_out > curr_stock:
                    st.error(f"Insufficient stock! Current stock: {curr_stock}")
                else:
                    cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", (qty_out, item_selected))
                    cursor.execute("""
                        INSERT INTO transactions (timestamp, item_name, type, quantity, user_role, issued_to, driver_details, project_name, purpose) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item_selected, "OUT", qty_out, user_name, issued_to, driver_out, proj_name, purpose))
                    conn.commit()
                    st.success(f"Successfully issued {qty_out} of {item_selected}")
                    st.rerun()

    # --- SUPERVISOR SPECIFIC MENU: MY LOG & REQUEST EDITS ---
    elif selected_menu == "📜 My Log & Request Edits":
        st.subheader("My Recent Activity & Edit Requests")
        st.caption("If you made a typing error in a log, click 'Request Edit' to submit a correction request to Head Office.")

        df_my_tx = pd.read_sql_query(
            """SELECT id, timestamp, item_name, type, quantity, issued_to, driver_details, project_name, purpose, remarks, edit_status 
               FROM transactions WHERE user_role = ? ORDER BY id DESC""", 
            conn, params=(user_name,)
        )

        if not df_my_tx.empty:
            for _, row in df_my_tx.iterrows():
                tx_id = row['id']
                status_badge = ""
                if row['edit_status'] == 'PENDING_EDIT':
                    status_badge = "⏳ **[PENDING EDIT APPROVAL]** "

                with st.expander(f"{status_badge}#{tx_id} | {row['timestamp']} | {row['type']} - {row['item_name']} ({row['quantity']})"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write(f"**Item:** {row['item_name']}")
                        st.write(f"**Quantity:** {row['quantity']}")
                        st.write(f"**Type:** {row['type']}")
                        st.write(f"**Issued To:** {row['issued_to'] or '-'}")
                    with c2:
                        st.write(f"**Driver:** {row['driver_details'] or '-'}")
                        st.write(f"**Project:** {row['project_name'] or '-'}")
                        st.write(f"**Purpose / Remarks:** {row['purpose'] or row['remarks'] or '-'}")

                    if row['edit_status'] == 'PENDING_EDIT':
                        st.warning("An edit request is currently pending Head Office approval for this log.")
                    else:
                        with st.popover("✏️ Request Correction / Edit"):
                            st.markdown("#### Submit Correction Request")
                            edit_qty = st.number_input("Corrected Quantity", value=float(row['quantity']), key=f"eqty_{tx_id}")
                            edit_issued_to = st.text_input("Corrected Issued To", value=str(row['issued_to'] or ''), key=f"eiss_{tx_id}")
                            edit_driver = st.text_input("Corrected Driver / Delivery", value=str(row['driver_details'] or ''), key=f"edrv_{tx_id}")
                            edit_proj = st.text_input("Corrected Project Name", value=str(row['project_name'] or ''), key=f"eprj_{tx_id}")
                            edit_purpose = st.text_input("Corrected Purpose / Remarks", value=str(row['purpose'] or row['remarks'] or ''), key=f"eprp_{tx_id}")
                            edit_reason = st.text_area("Reason for Correction Error (Mandatory)", placeholder="e.g. Typo in quantity, entered 100 instead of 10", key=f"ersn_{tx_id}")

                            if st.button("Submit Request to Head Office", key=f"btn_sub_{tx_id}"):
                                if not edit_reason.strip():
                                    st.error("You must provide a reason for the error.")
                                else:
                                    orig_data = json.dumps({
                                        "quantity": row['quantity'],
                                        "issued_to": row['issued_to'],
                                        "driver_details": row['driver_details'],
                                        "project_name": row['project_name'],
                                        "purpose": row['purpose'] or row['remarks']
                                    })
                                    prop_data = json.dumps({
                                        "quantity": edit_qty,
                                        "issued_to": edit_issued_to,
                                        "driver_details": edit_driver,
                                        "project_name": edit_proj,
                                        "purpose": edit_purpose
                                    })

                                    cursor.execute("""
                                        INSERT INTO edit_requests (transaction_id, requested_by, reason, original_data, proposed_data, status, timestamp)
                                        VALUES (?, ?, ?, ?, ?, 'PENDING', ?)
                                    """, (tx_id, user_name, edit_reason.strip(), orig_data, prop_data, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                                    
                                    cursor.execute("UPDATE transactions SET edit_status = 'PENDING_EDIT' WHERE id = ?", (tx_id,))
                                    conn.commit()

                                    create_notification(
                                        f"⚠️ New Edit Request from `{user_name}` for Log #{tx_id} ({row['item_name']}).",
                                        target_role="Head Office"
                                    )

                                    st.success("Edit request submitted to Head Office!")
                                    st.rerun()
        else:
            st.info("You have not submitted any stock entries yet.")

    # --- SUPERVISOR SPECIFIC MENU: EXCEL REPORTS ---
    elif selected_menu == "📅 Daily Report (Excel)":
        st.subheader("📅 Multi-Sheet Excel Report Generator")

        selected_date = st.date_input("Select Report Date", datetime.now().date())
        date_str = selected_date.strftime("%Y-%m-%d")

        query_daily = """
            SELECT timestamp, item_name, type, quantity, issued_to, driver_details, project_name, purpose, user_role, remarks 
            FROM transactions 
            WHERE timestamp LIKE ? 
            ORDER BY id ASC
        """
        df_daily_tx = pd.read_sql_query(query_daily, conn, params=(f"{date_str}%",))
        df_current_stock = pd.read_sql_query("SELECT item_name, category, unit, current_stock, min_threshold FROM master_items ORDER BY category, item_name", conn)

        excel_data = generate_excel_report(
            user_name=user_name,
            selected_date=date_str,
            df_daily_tx=df_daily_tx,
            df_current_stock=df_current_stock
        )

        st.download_button(
            label="📥 Download Structured Excel Report (.xlsx)",
            data=excel_data,
            file_name=f"Site_Inventory_Report_{date_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    # --- HEAD OFFICE SPECIFIC MENU: EDIT REQUESTS ---
    elif "✏️ Edit Requests" in selected_menu:
        st.subheader("✏️ Supervisor Log Edit Requests")
        st.caption("Review correction requests submitted by supervisors due to typing mistakes.")

        pending_reqs = pd.read_sql_query("""
            SELECT e.id as req_id, e.transaction_id, e.requested_by, e.reason, e.original_data, e.proposed_data, e.timestamp as req_time,
                   t.item_name, t.type as tx_type
            FROM edit_requests e
            JOIN transactions t ON e.transaction_id = t.id
            WHERE e.status = 'PENDING'
            ORDER BY e.id DESC
        """, conn)

        if not pending_reqs.empty:
            for _, req in pending_reqs.iterrows():
                r_id = req['req_id']
                tx_id = req['transaction_id']
                orig = json.loads(req['original_data'])
                prop = json.loads(req['proposed_data'])

                st.markdown(f"### Request #{r_id} — Log #{tx_id} (`{req['item_name']}`)")
                st.caption(f"Requested by **{req['requested_by']}** on {req['req_time']}")
                st.info(f"**Reason for Error:** {req['reason']}")

                diff_data = {
                    "Field": ["Quantity", "Issued To", "Driver / Vehicle", "Project Name", "Purpose / Remarks"],
                    "Original Value": [orig.get('quantity'), orig.get('issued_to'), orig.get('driver_details'), orig.get('project_name'), orig.get('purpose')],
                    "Proposed Correction": [prop.get('quantity'), prop.get('issued_to'), prop.get('driver_details'), prop.get('project_name'), prop.get('purpose')]
                }
                st.table(pd.DataFrame(diff_data))

                col_acc, col_rej = st.columns(2)
                with col_acc:
                    if st.button(f"✅ Accept & Update Log #{tx_id}", key=f"acc_{r_id}", use_container_width=True):
                        qty_diff = float(prop['quantity']) - float(orig['quantity'])
                        if req['tx_type'] == 'IN':
                            cursor.execute("UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?", (qty_diff, req['item_name']))
                        else:
                            cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", (qty_diff, req['item_name']))

                        cursor.execute("""
                            UPDATE transactions 
                            SET quantity = ?, issued_to = ?, driver_details = ?, project_name = ?, purpose = ?, edit_status = 'EDITED'
                            WHERE id = ?
                        """, (prop['quantity'], prop['issued_to'], prop['driver_details'], prop['project_name'], prop['purpose'], tx_id))

                        cursor.execute("UPDATE edit_requests SET status = 'APPROVED' WHERE id = ?", (r_id,))
                        conn.commit()

                        create_notification(
                            f"✅ Your edit request for Log #{tx_id} ({req['item_name']}) was APPROVED by Head Office.",
                            target_user=req['requested_by']
                        )

                        st.success("Log updated and inventory stock recalculated!")
                        st.rerun()

                with col_rej:
                    with st.popover("❌ Reject Request", use_container_width=True):
                        rej_remarks = st.text_input("Rejection Reason (Optional)", key=f"rej_rem_{r_id}")
                        if st.button("Confirm Reject", key=f"cnf_rej_{r_id}"):
                            cursor.execute("UPDATE edit_requests SET status = 'REJECTED', review_remarks = ? WHERE id = ?", (rej_remarks, r_id))
                            cursor.execute("UPDATE transactions SET edit_status = 'NORMAL' WHERE id = ?", (tx_id,))
                            conn.commit()

                            create_notification(
                                f"❌ Your edit request for Log #{tx_id} was REJECTED. Remarks: {rej_remarks or 'None'}",
                                target_user=req['requested_by']
                            )

                            st.warning("Request rejected.")
                            st.rerun()
                st.divider()
        else:
            st.info("No pending edit requests from supervisors.")

    # --- HEAD OFFICE SPECIFIC MENU: MANAGE MASTER ITEMS ---
    elif selected_menu == "➕ Manage Master Items":
        categories_list = [
            "1. Fuel & Oils", 
            "2. Construction Materials", 
            "3. Steel / Rebar", 
            "4A. Nails & Fasteners", 
            "4B. Cutting & Grinding Consumables", 
            "4C. Welding Supplies & PPE", 
            "4D. General Site Supplies"
        ]

        # Section A: Edit Existing Inventory Item Name & Category
        st.subheader("✏️ Edit Item Name or Category")
        existing_items_df = pd.read_sql_query("SELECT id, item_name, category, unit, min_threshold FROM master_items ORDER BY item_name ASC", conn)

        if not existing_items_df.empty:
            selected_item_name = st.selectbox("Select Master Item to Modify", existing_items_df['item_name'].tolist(), key="select_edit_item")
            item_details = existing_items_df[existing_items_df['item_name'] == selected_item_name].iloc[0]

            with st.form("edit_master_item_form"):
                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    updated_item_name = st.text_input("Item Name", value=item_details['item_name'])
                    cat_index = categories_list.index(item_details['category']) if item_details['category'] in categories_list else 0
                    updated_category = st.selectbox("Category", categories_list, index=cat_index)

                with col_e2:
                    updated_unit = st.text_input("Unit of Measure", value=item_details['unit'])
                    updated_min_thresh = st.number_input("Minimum Alert Threshold", min_value=0.0, value=float(item_details['min_threshold']), step=1.0)

                btn_update_item = st.form_submit_button("Update Item Details", use_container_width=True)

            if btn_update_item:
                if updated_item_name.strip():
                    try:
                        old_item_name = item_details['item_name']
                        
                        cursor.execute("""
                            UPDATE master_items 
                            SET item_name = ?, category = ?, unit = ?, min_threshold = ?
                            WHERE id = ?
                        """, (updated_item_name.strip(), updated_category, updated_unit.strip(), updated_min_thresh, int(item_details['id'])))
                        
                        if old_item_name != updated_item_name.strip():
                            cursor.execute("UPDATE transactions SET item_name = ? WHERE item_name = ?", (updated_item_name.strip(), old_item_name))

                        conn.commit()
                        st.success(f"Successfully updated '{old_item_name}' details!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("An item with that name already exists.")
                else:
                    st.error("Item name cannot be empty.")
        else:
            st.info("No items in inventory to edit.")

        st.markdown("---")

        # Section B: Add New Item
        st.subheader("➕ Add New Master Item")
        with st.form("add_new_master_item_form"):
            col_n1, col_n2 = st.columns(2)
            with col_n1:
                new_name = st.text_input("New Item Name")
                new_cat = st.selectbox("Category", categories_list, key="add_cat_select")
            with col_n2:
                new_unit = st.text_input("Unit of Measure (e.g., Liters, Bags, Pcs)")
                init_stock = st.number_input("Initial Stock Quantity", min_value=0.0, step=1.0)
                min_thresh = st.number_input("Minimum Alert Threshold", min_value=0.0, step=1.0)

            btn_save_new = st.form_submit_button("Save New Item", use_container_width=True)

        if btn_save_new:
            if new_name.strip():
                try:
                    cursor.execute("INSERT INTO master_items (item_name, category, unit, current_stock, min_threshold) VALUES (?, ?, ?, ?, ?)",
                                   (new_name.strip(), new_cat, new_unit.strip(), init_stock, min_thresh))
                    conn.commit()
                    st.success(f"Added '{new_name}' to inventory master!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("An item with that name already exists.")
            else:
                st.error("Item name cannot be empty.")

    # --- HEAD OFFICE SPECIFIC MENU: MASTER AUDIT LOG ---
    elif selected_menu == "📜 Master Audit Log":
        st.subheader("Master Transaction Audit Log")
        df_tx = pd.read_sql_query("SELECT * FROM transactions ORDER BY id DESC", conn)
        st.dataframe(df_tx, use_container_width=True)
        
        photos = df_tx[df_tx['photo_path'].notnull()]
        if not photos.empty:
            st.markdown("---")
            st.markdown("### 📷 Delivery Receipt & Photo Audit Trail")
            cols = st.columns(3)
            for idx, (_, row) in enumerate(photos.iterrows()):
                if os.path.exists(row['photo_path']):
                    with cols[idx % 3]:
                        st.image(row['photo_path'], caption=f"{row['item_name']} | {row['driver_details']} ({row['timestamp']})", use_container_width=True)

    # --- HEAD OFFICE SPECIFIC MENU: MANAGE USERS ---
    elif selected_menu == "👤 Manage Users":
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
