# views/low_stock.py
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db, init_db

def render_low_stock(user_name, user_role):
    st.title("⚠️ Low Stock Alerts")
    st.caption("Monitor items below minimum safety thresholds and queue restock orders.")

    init_db()

    try:
        with get_db() as conn:
            # Query items where current_stock is at or below min_threshold
            df = pd.read_sql_query("""
                SELECT id, item_name, category, unit, current_stock, min_threshold, remarks 
                FROM master_items 
                WHERE current_stock <= min_threshold
                ORDER BY (current_stock - min_threshold) ASC, category ASC, item_name ASC
            """, conn)

        if df.empty:
            st.success("✅ Great news! All inventory items are currently above their minimum safety thresholds.")
            return

        # Top Warning Banner
        st.warning(f"⚠️ **Attention Required:** There are **{len(df)}** item(s) running low on stock.")

        # Data Display
        df_display = df.rename(columns={
            "id": "ID",
            "item_name": "Item Description",
            "category": "Category",
            "unit": "Unit",
            "current_stock": "Current Stock",
            "min_threshold": "Min Threshold",
            "remarks": "Storage / Remarks"
        })

        # Calculate Stock Deficit
        df_display["Shortage Quantity"] = df_display["Min Threshold"] - df_display["Current Stock"]

        st.dataframe(
            df_display[[
                "ID", "Item Description", "Category", "Unit", 
                "Current Stock", "Min Threshold", "Shortage Quantity", "Storage / Remarks"
            ]],
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        # Quick Reorder / Schedule Delivery Helper
        st.subheader("📅 Schedule Quick Restock Shipment")
        
        with st.form("quick_schedule_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                selected_item = st.selectbox("Select Low Stock Item", df["item_name"].tolist())
                
                # Fetch unit and default shortage quantity for selected item
                item_info = df[df["item_name"] == selected_item].iloc[0]
                suggested_qty = max(1.0, float(item_info["min_threshold"] - item_info["current_stock"]))
                
                expected_qty = st.number_input("Expected Restock Quantity*", min_value=0.1, value=suggested_qty, step=1.0)
                unit_label = st.text_input("Unit of Measure", value=str(item_info["unit"]), disabled=True)

            with col2:
                scheduled_date = st.date_input("Expected Delivery Date*")
                supplier = st.text_input("Supplier / Source", placeholder="e.g., Prime Steel Corp")
                schedule_remarks = st.text_input("Delivery Remarks", placeholder="e.g., Urgent site delivery")

            submit_schedule = st.form_submit_button("➕ Add to Delivery Schedules", use_container_width=True)

            if submit_schedule:
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO schedules (scheduled_date, item_name, expected_quantity, unit, supplier, status, remarks)
                            VALUES (?, ?, ?, ?, ?, 'PENDING', ?)
                        """, (str(scheduled_date), selected_item, expected_qty, item_info["unit"], supplier.strip(), schedule_remarks.strip()))
                        conn.commit()
                        st.success(f"✅ Created pending delivery schedule for **{selected_item}** on {scheduled_date}.")
                except Exception as e:
                    st.error(f"Failed to schedule delivery: {e}")

    except Exception as e:
        st.error(f"Error loading low stock alerts: {e}")
