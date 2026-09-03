# views/stock_in.py
import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime
from database import get_db

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
                cursor.execute(f"ALTER TABLE transactions ADD COLUMN {col_name} {col_type}")
        conn.commit()

def render_stock_in(user_name, user_role):
    # Ensure database schema is migrated before rendering anything
    ensure_transactions_schema()

    st.title("📥 Stock IN - Receive Inventory")
    st.caption("Record incoming materials, stock deliveries, and supplier receipts.")

    # 1. Fetch Master Items for the dropdown
    with get_db() as conn:
        df_items = pd.read_sql_query("SELECT id, item_name, unit, current_stock FROM master_items ORDER BY item_name ASC", conn)

    if df_items.empty:
        st.warning("⚠️ No master items found. Please add items in 'Manage Master Items' first before receiving stock.")
        return

    item_options = df_items["item_name"].tolist()

    # 2. Stock IN Entry Form
    with st.form("stock_in_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            selected_item = st.selectbox("Select Material / Item", item_options)
            
            # Show current stock for the selected item
            item_row = df_items[df_items["item_name"] == selected_item].iloc[0]
            st.info(f"Current Available Stock: **{item_row['current_stock']} {item_row['unit']}**")

            qty_in = st.number_input(f"Quantity Received ({item_row['unit']})", min_value=0.01, step=1.0, format="%.2f")
            driver_details = st.text_input("Transporter / Driver / Truck Details", placeholder="e.g., Plate # ABC-1234, Driver: John")

        with col2:
            project_name = st.text_input("Site / Destination Project", placeholder="e.g., Main Campus Building A")
            purpose = st.text_input("Purpose / Reference PO", placeholder="e.g., PO # 98452 Delivery")
            remarks = st.text_area("Delivery Remarks / Notes", placeholder="e.g., Received in good condition, 50 bags per pallet.")

        submit_btn = st.form_submit_button("📥 Confirm & Save Received Stock")

        if submit_btn:
            if qty_in <= 0:
                st.error("Please enter a valid quantity greater than zero.")
            else:
                try:
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    with get_db() as conn:
                        cursor = conn.cursor()
                        
                        # Update master stock balance
                        cursor.execute(
                            "UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?",
                            (qty_in, selected_item)
                        )

                        # Insert entry into transactions ledger
                        cursor.execute("""
                            INSERT INTO transactions (
                                timestamp, item_name, type, quantity, user_name, user_role,
                                driver_details, project_name, purpose, remarks, edit_status
                            ) VALUES (?, ?, 'IN', ?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
                        """, (
                            now_str, selected_item, qty_in, user_name, user_role,
                            driver_details.strip(), project_name.strip(), purpose.strip(), remarks.strip()
                        ))

                        conn.commit()

                    st.toast(f"✅ Successfully added {qty_in} {item_row['unit']} to {selected_item}!", icon="📥")
                    st.success(f"Stock IN logged for **{selected_item}** (+{qty_in} {item_row['unit']}).")
                    st.rerun()

                except sqlite3.OperationalError:
                    st.error("Database is currently locked or busy. Please try again in a moment.")

    # 3. Recent Delivery Logs Table
    st.divider()
    st.subheader("📑 Recent Incoming Material Deliveries Log")
    
    with get_db() as conn:
        df_recent_in = pd.read_sql_query("""
            SELECT 
                timestamp, 
                item_name, 
                quantity, 
                COALESCE(driver_details, '') AS driver_details, 
                COALESCE(project_name, '') AS project_name, 
                COALESCE(purpose, '') AS purpose, 
                user_name, 
                COALESCE(remarks, '') AS remarks 
            FROM transactions 
            WHERE type = 'IN' 
            ORDER BY id DESC LIMIT 10
        """, conn)

    if not df_recent_in.empty:
        df_recent_in = df_recent_in.rename(columns={
            "timestamp": "Date & Time",
            "item_name": "Item Name",
            "quantity": "Qty Received",
            "driver_details": "Transporter / Driver",
            "project_name": "Destination / Site",
            "purpose": "Purpose / PO",
            "user_name": "Logged By",
            "remarks": "Remarks"
        })
        st.dataframe(df_recent_in, use_container_width=True, hide_index=True)
    else:
        st.info("No incoming deliveries recorded yet.")
