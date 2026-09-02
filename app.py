import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

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


# --- HELPER FUNCTION: EXCEL REPORT GENERATOR ---
def generate_excel_report(user_name, selected_date, df_daily_tx, df_current_stock):
    wb = openpyxl.Workbook()
    
    # Sheet 1: Daily Transactions Log
    ws_tx = wb.active
    ws_tx.title = "Daily Activity Log"
    ws_tx.views.sheetView[0].showGridLines = True

    # Title Block
    ws_tx.merge_cells("A1:F1")
    title_cell = ws_tx["A1"]
    title_cell.value = "CONSTRUCTION SITE INVENTORY - DAILY ACTIVITY REPORT"
    title_cell.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    title_cell.fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws_tx.row_dimensions[1].height = 30

    # Meta Info
    ws_tx["A3"] = f"Report Date: {selected_date}"
    ws_tx["A3"].font = Font(bold=True)
    ws_tx["A4"] = f"Supervisor: {user_name}"
    ws_tx["A4"].font = Font(bold=True)
    ws_tx["A5"] = f"Generated On: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    ws_tx["A5"].font = Font(italic=True, color="595959")

    # Table Headers
    headers = ["Time", "Item Name", "Transaction Type", "Quantity", "Logged By", "Remarks / DR / Issued To"]
    start_row = 7
    for col_num, header_title in enumerate(headers, 1):
        cell = ws_tx.cell(row=start_row, column=col_num, value=header_title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )

    # Data Rows
    current_row = start_row + 1
    if not df_daily_tx.empty:
        for _, row in df_daily_tx.iterrows():
            ws_tx.cell(row=current_row, column=1, value=str(row['timestamp']))
            ws_tx.cell(row=current_row, column=2, value=str(row['item_name']))
            
            type_cell = ws_tx.cell(row=current_row, column=3, value=str(row['type']))
            type_cell.alignment = Alignment(horizontal="center")
            if row['type'] == 'IN':
                type_cell.font = Font(bold=True, color="006100")
            else:
                type_cell.font = Font(bold=True, color="9C0006")

            qty_cell = ws_tx.cell(row=current_row, column=4, value=float(row['quantity']))
            qty_cell.number_format = "#,##0.00"
            
            ws_tx.cell(row=current_row, column=5, value=str(row['user_role']))
            ws_tx.cell(row=current_row, column=6, value=str(row['remarks']))

            for col_num in range(1, 7):
                ws_tx.cell(row=current_row, column=col_num).border = thin_border

            current_row += 1
    else:
        ws_tx.cell(row=current_row, column=1, value="No transactions recorded for this date.")
        current_row += 1

    # Sheet 2: Stock Snapshot
    ws_stock = wb.create_sheet(title="Current Stock Snapshot")
    ws_stock.views.sheetView[0].showGridLines = True

    ws_stock.merge_cells("A1:E1")
    s_title = ws_stock["A1"]
    s_title.value = "SITE INVENTORY BALANCE SNAPSHOT"
    s_title.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    s_title.fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    s_title.alignment = Alignment(horizontal="center", vertical="center")
    ws_stock.row_dimensions[1].height = 30

    stock_headers = ["Item Name", "Category", "Unit", "Current Stock", "Min Threshold"]
    for col_num, header_title in enumerate(stock_headers, 1):
        cell = ws_stock.cell(row=3, column=col_num, value=header_title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    s_row = 4
    if not df_current_stock.empty:
        for _, row in df_current_stock.iterrows():
            ws_stock.cell(row=s_row, column=1, value=str(row['item_name']))
            ws_stock.cell(row=s_row, column=2, value=str(row['category']))
            ws_stock.cell(row=s_row, column=3, value=str(row['unit']))
            
            stk_cell = ws_stock.cell(row=s_row, column=4, value=float(row['current_stock']))
            stk_cell.number_format = "#,##0.00"

            thresh_cell = ws_stock.cell(row=s_row, column=5, value=float(row['min_threshold']))
            thresh_cell.number_format = "#,##0.00"

            # Low stock highlight
            if float(row['current_stock']) <= float(row['min_threshold']):
                stk_cell.fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
                stk_cell.font = Font(color="9C0006", bold=True)

            for col_num in range(1, 6):
                ws_stock.cell(row=s_row, column=col_num).border = thin_border

            s_row += 1

    # Auto-fit Column Widths for both sheets
    for sheet in [ws_tx, ws_stock]:
        for col in sheet.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.row in [1]:  # Skip title row length calculation
                    continue
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            sheet.column_dimensions[col_letter].width = max(max_len + 4, 12)

    # Save to memory buffer
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

    # Tab 1: Current Inventory (Accessible to ALL)
    with tab1:
        st.subheader("Current Available Stocks")
        df_items = pd.read_sql_query("SELECT item_name, category, unit, current_stock, min_threshold FROM master_items", conn)
        
        if not df_items.empty:
            def highlight_low_stock(row):
                return ['background-color: #ffcccc' if row['current_stock'] <= row['min_threshold'] else '' for _ in row]

            st.dataframe(df_items.style.apply(highlight_low_stock, axis=1), use_container_width=True)
        else:
            st.info("No items found in Master Inventory.")

    # Tab 2: Stock In (Receiving)
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

    # Tab 3: Stock Out (Issuance)
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

    # Supervisor Tab 4: Personal Activity Verification Log
    if st.session_state["user_role"] == "Materials Supervisor":
        with tab4:
            st.subheader("My Recent Activity & Submitted Logs")
            st.caption("Review your recently submitted transactions below to verify if your entries are correct.")
            
            df_my_tx = pd.read_sql_query(
                "SELECT timestamp, item_name, type, quantity, remarks FROM transactions WHERE user_role = ? ORDER BY id DESC", 
                conn, params=(st.session_state["username"],)
            )
            
            if not df_my_tx.empty:
                st.dataframe(df_my_tx, use_container_width=True)
            else:
                st.info("You have not submitted any stock entries yet.")

        # Supervisor Tab 5: Daily Activity & Excel Report Generator
        with tab5:
            st.subheader("📅 Daily Activity Report Generator")
            st.caption("Select a date to preview transactions and download an official Excel (.xlsx) summary report.")

            selected_date = st.date_input("Select Report Date", datetime.now().date())
            date_str = selected_date.strftime("%Y-%m-%d")

            # Fetch transactions for selected date
            query_daily = """
                SELECT timestamp, item_name, type, quantity, user_role, remarks 
                FROM transactions 
                WHERE timestamp LIKE ? 
                ORDER BY id ASC
            """
            df_daily_tx = pd.read_sql_query(query_daily, conn, params=(f"{date_str}%",))
            df_current_stock = pd.read_sql_query("SELECT item_name, category, unit, current_stock, min_threshold FROM master_items", conn)

            # Metrics
            col1, col2, col3 = st.columns(3)
            in_count = len(df_daily_tx[df_daily_tx['type'] == 'IN']) if not df_daily_tx.empty else 0
            out_count = len(df_daily_tx[df_daily_tx['type'] == 'OUT']) if not df_daily_tx.empty else 0
            
            col1.metric("Stock In Logs", f"{in_count} Entries")
            col2.metric("Stock Out Logs", f"{out_count} Entries")
            col3.metric("Total Activity", f"{len(df_daily_tx)} Records")

            st.markdown("---")
            st.write(f"### Activity Preview for `{date_str}`")

            if not df_daily_tx.empty:
                st.dataframe(df_daily_tx, use_container_width=True)
            else:
                st.info(f"No transactions logged on {date_str}.")

            # Generate Excel Buffer
            excel_data = generate_excel_report(
                user_name=st.session_state["username"],
                selected_date=date_str,
                df_daily_tx=df_daily_tx,
                df_current_stock=df_current_stock
            )

            # Excel Download Button
            st.download_button(
                label="📥 Download Daily Excel Report (.xlsx)",
                data=excel_data,
                file_name=f"Site_Inventory_Daily_Report_{date_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

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

        # Tab 5: Complete Master Audit Log across all users
        with tab5:
            st.subheader("Master Transaction Audit Log")
            df_tx = pd.read_sql_query("SELECT * FROM transactions ORDER BY id DESC", conn)
            st.dataframe(df_tx, use_container_width=True)

        # Tab 6: User Management
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
