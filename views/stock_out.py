# views/stock_out.py
import os
import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime
from database import get_db, UPLOAD_DIR

def render_stock_out(user_name, user_role):
    st.title("📤 Issue Materials (Stock OUT)")
    st.caption("Record material issuances for site projects, sub-contractors, or maintenance needs.")

    if "is_submitting_out" not in st.session_state:
        st.session_state.is_submitting_out = False

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
                issued_to = st.text_input("Issued To (Person / Contractor / Sub-con)", placeholder="e.g., Engr. Santos / ABC Masonry", key="out_issued_to")
                project_name = st.text_input("Project Site / Work Area", placeholder="e.g., Tower 1 - Level 5 Floor Slab", key="out_project")

            with col2:
                st.info(f"📌 **Current Recorded Balance:** `{current_bal:,.2f} {unit_label}`\n\n**Category:** `{selected_item_info['category']}`")
                purpose = st.text_input("Purpose / Activity Details", placeholder="e.g., Slab Concreting Phase 2", key="out_purpose")
                driver_info = st.text_input("Transporter / Hauler Details (Optional)", placeholder="e.g., Site Buggy #2 / Driver Mike", key="out_driver")
                remarks = st.text_area("Additional Notes / Gate Pass No.", placeholder="e.g., Requisition Form #1042 attached", key="out_remarks")

            st.divider()
            uploaded_file = st.file_uploader("📷 Upload Requisition Form or Photo Proof (PNG, JPG, JPEG)", type=["png", "jpg", "jpeg"], key="out_file")

            submit_out = st.form_submit_button("📤 Confirm & Issue Material", disabled=st.session_state.is_submitting_out)

            if submit_out and not st.session_state.is_submitting_out:
                if qty_out is None or qty_out <= 0:
                    st.error("Please enter a valid quantity to issue.")
                elif qty_out > current_bal:
                    st.error(f"❌ Insufficient Stock! Requested: {qty_out:,.2f} {unit_label} | Available: {current_bal:,.2f} {unit_label}")
                elif not issued_to.strip():
                    st.error("Please specify who or which contractor the material is being issued to.")
                else:
                    st.session_state.is_submitting_out = True

                    try:
                        photo_path = ""
                        if uploaded_file is not None:
                            file_ext = os.path.splitext(uploaded_file.name)[1]
                            filename = f"OUT_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{issued_to.strip().replace(' ', '_')}{file_ext}"
                            photo_path = os.path.join(UPLOAD_DIR, filename)
                            with open(photo_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())

                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("BEGIN IMMEDIATE")
                            cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", (qty_out, item_selected))
                            cursor.execute("""
                                INSERT INTO transactions (
                                    timestamp, item_name, type, quantity, user_name, user_role, 
                                    driver_details, issued_to, project_name, purpose, remarks, photo_path
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                item_selected, "OUT", qty_out, user_name, user_role,
                                driver_info.strip(), issued_to.strip(), project_name.strip(), purpose.strip(), remarks.strip(), photo_path
                            ))
                            conn.commit()

                            st.toast(f"✅ Material Issued: {qty_out:,.2f} {unit_label} of {item_selected}", icon="📤")
                            st.success(f"Successfully issued **{qty_out:,.2f} {unit_label}** of **{item_selected}** to **{issued_to}**!")
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
                   user_name,
                   remarks 
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
            "project_name": "Project Site",
            "purpose": "Purpose / Activity",
            "user_name": "Issued By",
            "remarks": "Remarks"
        })
        st.dataframe(df_recent_out, use_container_width=True, hide_index=True)
    else:
        st.info("No material issuances recorded yet.")
