import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import io
import os
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
    photo_path TEXT
)
""")

# Safe Schema Update Migrations
for col, col_type in [
    ("driver_details", "TEXT"),
    ("issued_to", "TEXT"),
    ("project_name", "TEXT"),
    ("purpose", "TEXT"),
    ("photo_path", "TEXT")
]:
    try:
        cursor.execute(f"ALTER TABLE transactions ADD COLUMN {col} {col_type}")
    except sqlite3.OperationalError:
        pass

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

# --- SEED EXPANDED INVENTORY LIST ---
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


# --- ENHANCED MULTI-SHEET EXCEL REPORT GENERATOR ---
def generate_excel_report(user_name, selected_date, df_daily_tx, df_current_stock):
    wb = openpyxl.Workbook()
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )

    # ----------------------------------------------------
    # SHEET 1: MASTER LOG (ALL TRANSACTIONS)
    # ----------------------------------------------------
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
            if r.get('type') == 'IN':
                t_cell.font = Font(bold=True, color="006100")
            else:
                t_cell.font = Font(bold=True, color="9C0006")

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

    # ----------------------------------------------------
    # SHEET 2: STOCK IN RECORD
    # ----------------------------------------------------
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

    # ----------------------------------------------------
    # SHEET 3: STOCK OUT RECORD (SEPARATED FIELDS)
    # ----------------------------------------------------
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

    # ----------------------------------------------------
    # SHEET 4: CATEGORIZED STOCK BALANCE
    # ----------------------------------------------------
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
        categories = df_current_stock['category'].unique()
        for cat in sorted(categories):
            ws_cat.merge_cells(start_row=c_row, start_column=1, end_row=c_row, end_column=4)
            cat_cell = ws_cat.cell(row=c_row, column=1, value=str(cat).upper())
            cat_cell.font = Font(bold=True, color="FFFFFF")
            cat_cell.fill = PatternFill(start_color="595959", end_color="595959", fill_type="solid")
            cat_cell.alignment = Alignment(horizontal="left", vertical="center")
            c_row += 1

            sub_headers = ["Item Name", "Unit", "Current Stock", "Min Alert Threshold"]
            for col_num, h_title in enumerate(sub_headers, 1):
                cell = ws_cat.cell(row=c_row, column=col_num, value=h_title)
                cell.font = Font(bold=True, color="333333")
                cell.fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")

            c_row += 1
            cat_items = df_current_stock[df_current_stock['category'] == cat]
            for _, r in cat_items.iterrows():
                ws_cat.cell(row=c_row, column=1, value=str(r['item_name']))
                ws_cat.cell(row=c_row, column=2, value=str(r['unit']))
                
                stk_cell = ws_cat.cell(row=c_row, column=3, value=float(r['current_stock']))
                stk_cell.number_format = "#,##0.00"

                thresh_cell = ws_cat.cell(row=c_row, column=4, value=float(r['min_threshold']))
                thresh_cell.number_format = "#,##0.00"

                if float(r['current_stock']) <= float(r['min_threshold']):
                    stk_cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                    stk_cell.font = Font(color="9C0006", bold=True)

                for col_num in range(1, 5):
                    ws_cat.cell(row=c_row, column=col_num).border = thin_border
                c_row += 1
            
            c_row += 1

    # Auto-Fit Columns
    for sheet in [ws_master, ws_in, ws_out, ws_cat]:
        for col in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.row in [1]:
                    continue
                if cell.value:
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
    st.sidebar.markdown(f"**Logged in as:** `{st.session_state['username']}`")
    st.sidebar.markdown(f"**Role:** `{st.session_state['user_role']}`")
    
    if st.sidebar.button("Log Out"):
        st.session_state["logged_in"] = False
        st.session_state["username"] = None
        st.session_state["user_role"] = None
        st.rerun()

    st.title("🏗️ Construction Site Inventory System")

    if st.session_state["user_role"] == "Materials Supervisor":
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📋 Current Inventory", 
            "+ Stock In", 
            "- Stock Out",
            "📜 My Log & History",
            "📅 Daily Report (Excel)"
        ])
    else:  # Head Office Admin
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📋 Current Inventory", 
            "+ Stock In", 
            "- Stock Out", 
            "➕ Add Master Item", 
            "📜 Master Audit Log",
            "👤 Manage Users"
        ])

    # Tab 1: Current Inventory
    with tab1:
        st.subheader("Current Available Stocks")
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
                """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item_selected, "IN", qty_in, st.session_state["username"], driver_info, remarks_in, saved_photo_path))
                conn.commit()
                st.success(f"Successfully recorded receiving {qty_in} of {item_selected}!")
                st.rerun()
        else:
            st.warning("Please add items to Master Inventory first.")

    # Tab 3: Stock Out (SEPARATED FIELDS)
    with tab3:
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
                    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item_selected, "OUT", qty_out, st.session_state["username"], issued_to, driver_out, proj_name, purpose))
                    conn.commit()
                    st.success(f"Successfully issued {qty_out} of {item_selected}")
                    st.rerun()

    # Supervisor Tab 4: Activity Log
    if st.session_state["user_role"] == "Materials Supervisor":
        with tab4:
            st.subheader("My Recent Activity & Submitted Logs")
            
            df_my_tx = pd.read_sql_query(
                """SELECT timestamp, item_name, type, quantity, issued_to, driver_details, project_name, purpose, remarks, photo_path 
                   FROM transactions WHERE user_role = ? ORDER BY id DESC""", 
                conn, params=(st.session_state["username"],)
            )
            
            if not df_my_tx.empty:
                st.dataframe(df_my_tx.drop(columns=["photo_path"]), use_container_width=True)
                
                photos = df_my_tx[df_my_tx['photo_path'].notnull()]
                if not photos.empty:
                    st.markdown("#### 📸 Attached Delivery Photos")
                    cols = st.columns(3)
                    for idx, (_, row) in enumerate(photos.iterrows()):
                        if os.path.exists(row['photo_path']):
                            with cols[idx % 3]:
                                st.image(row['photo_path'], caption=f"{row['item_name']} - {row['timestamp']}", use_container_width=True)
            else:
                st.info("You have not submitted any stock entries yet.")

        # Supervisor Tab 5: Multi-Sheet Daily Report Generator
        with tab5:
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

            col1, col2, col3 = st.columns(3)
            in_count = len(df_daily_tx[df_daily_tx['type'] == 'IN']) if not df_daily_tx.empty else 0
            out_count = len(df_daily_tx[df_daily_tx['type'] == 'OUT']) if not df_daily_tx.empty else 0
            
            col1.metric("Stock IN Logs", f"{in_count} Entries")
            col2.metric("Stock OUT Logs", f"{out_count} Entries")
            col3.metric("Total Master Activity", f"{len(df_daily_tx)} Records")

            st.markdown("---")
            st.write(f"### Activity Preview for `{date_str}`")

            if not df_daily_tx.empty:
                st.dataframe(df_daily_tx, use_container_width=True)
            else:
                st.info(f"No transactions logged on {date_str}.")

            excel_data = generate_excel_report(
                user_name=st.session_state["username"],
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

    # Head Office Tabs
    if st.session_state["user_role"] == "Head Office":
        with tab4:
            st.subheader("Add New Master Item")
            new_name = st.text_input("Item Name")
            new_cat = st.selectbox("Category", ["1. Fuel & Oils", "2. Construction Materials", "3. Steel / Rebar", "4A. Nails & Fasteners", "4B. Cutting & Grinding Consumables", "4C. Welding Supplies & PPE", "4D. General Site Supplies"])
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

        with tab5:
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
