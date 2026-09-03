# views/stock_in.py
import os
import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime
from database import get_db, UPLOAD_DIR

def render_stock_in(user_name, user_role):
    st.title("📥 Receive Material Deliveries (Stock IN)")
    st.caption("Log incoming material deliveries to update inventory balances and save proof of receipt.")
    
    if "is_submitting_in" not in st.session_state:
        st.session_state.is_submitting_in = False

    with get_db() as conn:
        df_items = pd.read_sql_query(
            "SELECT id, item_name, category, unit, current_stock FROM master_items ORDER BY category ASC, item_name ASC", 
            conn
        )

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
                            st.success(f"Successfully recorded **{qty_in:,.2f} {unit_label}** of **{item_selected}**!")
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
