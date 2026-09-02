import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# ---------------------------------------------------------
# DATABASE SETUP
# ---------------------------------------------------------
conn = sqlite3.connect("site_inventory.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT UNIQUE,
    category TEXT,
    unit TEXT,
    current_stock REAL,
    min_alert REAL
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    trans_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    item_name TEXT,
    trans_type TEXT,
    quantity REAL,
    issued_to_location TEXT,
    user_role TEXT,
    remarks TEXT,
    status TEXT DEFAULT 'ACTIVE'
)
""")
conn.commit()

# Seed database with standard categories/items if empty
c.execute("SELECT COUNT(*) FROM items")
if c.fetchone()[0] == 0:
    sample_items = [
        ("Diesel", "1. Fuel & Oils", "Liters", 1200, 500),
        ("Oil #10", "1. Fuel & Oils", "Liters", 40, 20),
        ("Tonner Cement", "2. Construction Materials", "Bags (1-Ton)", 15, 5),
        ("Small Bag Cement", "2. Construction Materials", "Bags (40kg)", 250, 100),
        ("Rebar 10mm", "3. Steel / Rebar", "Pcs", 350, 100),
        ("CWN #2 (2' Common Nails)", "4A. Nails & Fasteners", "Kilos", 45, 20),
        ("Cutting Disc 4'", "4B. Cutting & Grinding Consumables", "Pcs", 120, 50),
        ("Concrete Cutter Blade", "4B. Cutting & Grinding Consumables", "Pcs", 4, 2),
        ("Welding Rod 6011", "4C. Welding Supplies & PPE", "Kilos", 30, 15),
        ("Chalk Stone", "4D. General Site Supplies", "Boxes", 12, 5)
    ]
    c.executemany("INSERT INTO items (item_name, category, unit, current_stock, min_alert) VALUES (?, ?, ?, ?, ?)", sample_items)
    conn.commit()

# ---------------------------------------------------------
# STREAMLIT UI
# ---------------------------------------------------------
st.set_page_config(page_title="Construction Site Inventory", layout="wide")

st.sidebar.title("Construction Inventory App")
role = st.sidebar.selectbox("Select User Role", ["Materials Supervisor", "Head Office", "Admin"])

if role == "Materials Supervisor":
    st.title("📦 Materials Supervisor Interface")
    tab1, tab2 = st.tabs(["+ Stock In (Receiving)", "- Stock Out (Issuance)"])
    
    with tab1:
        st.subheader("Log Incoming Delivery")
        item_list = [r[0] for r in c.execute("SELECT item_name FROM items").fetchall()]
        selected_item = st.selectbox("Select Item", item_list)
        qty = st.number_input("Quantity Received", min_value=0.1, step=1.0)
        remarks = st.text_input("Delivery Receipt # / Remarks")
        if st.button("Submit Stock In"):
            c.execute("UPDATE items SET current_stock = current_stock + ? WHERE item_name = ?", (qty, selected_item))
            c.execute("INSERT INTO transactions (timestamp, item_name, trans_type, quantity, user_role, remarks) VALUES (?, ?, 'STOCK IN', ?, ?, ?)",
                      (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), selected_item, qty, role, remarks))
            conn.commit()
            st.success(f"Successfully added {qty} to {selected_item}!")

    with tab2:
        st.subheader("Log Material Issuance")
        selected_item_out = st.selectbox("Select Item to Issue", item_list, key="out_item")
        current_stk = c.execute("SELECT current_stock FROM items WHERE item_name = ?", (selected_item_out,)).fetchone()[0]
        st.info(f"Available Stock: {current_stk}")
        qty_out = st.number_input("Quantity Issued", min_value=0.1, max_value=float(current_stk), step=1.0)
        location = st.text_input("Issued To / Equipment ID / Location")
        if st.button("Submit Stock Out"):
            c.execute("UPDATE items SET current_stock = current_stock - ? WHERE item_name = ?", (qty_out, selected_item_out))
            c.execute("INSERT INTO transactions (timestamp, item_name, trans_type, quantity, issued_to_location, user_role) VALUES (?, ?, 'STOCK OUT', ?, ?, ?)",
                      (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), selected_item_out, qty_out, location, role))
            conn.commit()
            st.success(f"Successfully issued {qty_out} of {selected_item_out}!")

elif role in ["Head Office", "Admin"]:
    st.title("📊 Head Office Oversight & Management")
    tab1, tab2, tab3 = st.tabs(["Stock Overview & Low Stock Alerts", "Transaction History & Audit", "+ Add Master Item"])
    
    with tab1:
        st.subheader("Current Inventory Status")
        df_items = pd.read_sql_query("SELECT item_name AS Item, category AS Category, unit AS Unit, current_stock AS Stock, min_alert AS Min_Threshold FROM items", conn)
        df_items["Status"] = df_items.apply(lambda r: "⚠️ REORDER ALERT" if r["Stock"] <= r["Min_Threshold"] else "OK", axis=1)
        st.dataframe(df_items, use_container_width=True)
        
    with tab2:
        st.subheader("Master Transaction Audit Log")
        df_trans = pd.read_sql_query("SELECT * FROM transactions ORDER BY trans_id DESC", conn)
        st.dataframe(df_trans, use_container_width=True)
        
    with tab3:
        st.subheader("Add New Item to Master List")
        new_name = st.text_input("Item Name")
        new_cat = st.selectbox("Category", ["1. Fuel & Oils", "2. Construction Materials", "3. Steel / Rebar", "4A. Nails & Fasteners", "4B. Cutting & Grinding Consumables", "4C. Welding Supplies & PPE", "4D. General Site Supplies"])
        new_unit = st.text_input("Unit of Measure (e.g., Liters, Kilos, Pcs)")
        new_min = st.number_input("Minimum Alert Threshold", min_value=0.0, step=1.0)
        if st.button("Add Item"):
            try:
                c.execute("INSERT INTO items (item_name, category, unit, current_stock, min_alert) VALUES (?, ?, ?, 0, ?)", (new_name, new_cat, new_unit, new_min))
                conn.commit()
                st.success(f"Successfully added {new_name} to Master Inventory!")
            except sqlite3.IntegrityError:
                st.error("Item already exists!")
