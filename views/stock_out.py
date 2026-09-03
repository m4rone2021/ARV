# views/stock_out.py
import os
import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime
from database import get_db, UPLOAD_DIR

def ensure_transactions_schema():
    """Checks and automatically adds any missing columns to the transactions table."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(transactions)")
        existing_cols = [row[1] for row in cursor.fetchall()]

        required_cols = {
            "driver_details": "TEXT",
            "issued_to": "TEXT",
            "project_name": "TEXT",
            "purpose": "TEXT",
            "remarks": "TEXT",
            "photo_path": "TEXT",
            "edit_status": "TEXT DEFAULT 'ACTIVE'"
        }

        for col_name, col_type in required_cols.items():
            if col_name not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE transactions ADD COLUMN {col_name} {col_type}")
                except sqlite3.OperationalError:
                    pass  # Column already added by concurrent request
        conn.commit()

def render_stock_out(user_name, user_role):
    # Guarantee table and columns exist on startup
    ensure_transactions_schema()

    st.title("📤 Stock OUT - Issue Inventory")
    st.caption("Record material dispatches, site issuances, and inventory stock-outs.")

    # 1. Fetch Master Items for the dropdown
    with get_db() as conn:
        df_items = pd.read_sql_query("SELECT id, item_name, unit, current_stock FROM master_items ORDER BY item_name ASC", conn)

    if df_items.empty:
        st.warning("⚠️ No master items found. Please add items in 'Manage Master Items' first.")
        return

    item_options = df_items["item_name"].tolist()

    # 2. Stock OUT Entry Form
    with st.form("stock_out_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            selected_item = st.selectbox("Select Material / Item", item_options)
            
            # Display current available balance
            item_row = df_items[df_items["item_name"] == selected_item].iloc[0]
            current_bal = float(item_row['current_stock'])
            st.info(f"Available Stock Balance: **{current_bal} {item_row['unit']}**")

            qty_out = st.number_input(f"Quantity to Issue ({item_row['unit']})", min_value=0.01, step=1.0, format="%.2f")
            issued_to = st.text_input("Issued To / Recipient Name", placeholder="e.g., Engineer / Foreman Name")

        with col2:
            project_name = st.text_input("Destination Project / Site Location", placeholder="e.g., Bridge Expansion Site B")
            purpose = st.text_input("Purpose / Work Order", placeholder="e.g., Concrete Foundation Pouring")
            remarks = st.text_area("Dispatched Remarks / Notes", placeholder="e.g., Dispatched via Site Pickup Truck.")
            
            uploaded_photo = st.file_uploader("Attach Photo / Delivery Receipt (Optional)", type=["jpg", "png", "jpeg"])

        submit_btn = st.form_submit_button("📤 Confirm & Issue Stock")

        if submit_btn:
            if qty_out <= 0:
                st.error("Please enter a valid quantity greater than zero.")
            elif qty_out > current_bal:
                st.error(f"❌ Insufficient Stock! You are trying to issue **{qty_out} {item_row['unit']}**, but only **{current_bal} {item_row['unit']}** is available.")
            else:
                try:
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    photo_path = None

                    # Handle optional receipt/photo file save
                    if uploaded_photo is not None:
                        file_ext = os.path.splitext(uploaded_photo.name)[1]
                        filename = f"OUT_{datetime.now().strftime('%Y%m%d_%H%M%S')}{file_ext}"
                        photo_path = os.path.join(UPLOAD_DIR, filename)
                        with open(photo_path, "wb") as f:
                            f.write(uploaded_photo.getbuffer())

                    with get_db() as conn:
                        cursor = conn.cursor()
                        
                        # Deduct stock balance
                        cursor.execute(
                            "UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?",
                            (qty_out, selected_item)
                        )

                        # Record transaction in ledger
                        cursor.execute("""
                            INSERT INTO transactions (
                                timestamp, item_name, type, quantity, user_name, user_role,
                                issued_to, project_name, purpose, remarks, photo_path, edit_status
                            ) VALUES (?, ?, 'OUT', ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
                        """, (
                            now_str, selected_item, qty_out, user_name, user_role,
                            issued_to.strip(), project_name.strip(), purpose.strip(), remarks.strip(), photo_path
                        ))

                        conn.commit()

                    st.toast(f"✅ Dispatched {qty_out} {item_row['unit']} of {selected_item}!", icon="📤")
                    st.success(f"Stock OUT successfully logged for **{selected_item}** (-{qty_out} {item_row['unit']}).")
                    st.rerun()

                except sqlite3.OperationalError:
                    st.error("Database is currently busy or locked. Please try again in a moment.")

    # 3. Recent Stock Out Log Table (Fail-safe Query)
    st.divider()
    st.subheader("📑 Recent Outgoing Material Dispatches Log")
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    timestamp, 
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
            """)
            rows = cursor.fetchall()

        if rows:
            df_recent_out = pd.DataFrame(rows, columns=[
                "Date & Time", "Item Name", "Qty Issued", "Issued To",
                "Destination / Site", "Purpose", "Dispatched By", "Remarks"
            ])
            st.dataframe(df_recent_out, use_container_width=True, hide_index=True)
        else:
            st.info("No outgoing dispatches recorded yet.")
            
    except sqlite3.OperationalError:
        st.warning("Notice: Initializing transaction log table...")
        ensure_transactions_schema()
        st.rerun()
