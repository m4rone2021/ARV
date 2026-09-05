import sqlite3
import pandas as pd
import streamlit as st
from database import get_db


def render_low_stock(user_name, user_role):
    st.title("⚠️ Low Stock Alerts")
    st.caption(
        "Monitor items below minimum safety thresholds and queue restock orders based on effective stock."
    )

    try:
        with get_db() as conn:
            # Fetch master items and compute effective stock
            df = pd.read_sql_query(
                """
                SELECT id, item_name, category, unit, 
                       COALESCE(current_stock, 0.0) AS current_stock, 
                       COALESCE(reserved_stock, 0.0) AS reserved_stock, 
                       min_threshold, remarks 
                FROM master_items
            """,
                conn,
            )

        if df.empty:
            st.info("ℹ️ No inventory items found in database.")
            return

        # Compute effective available stock and shortage
        df["effective_stock"] = df["current_stock"] - df["reserved_stock"]
        low_stock_df = df[df["effective_stock"] <= df["min_threshold"]].copy()

        if low_stock_df.empty:
            st.success(
                "✅ Great news! All inventory items are currently above their minimum safety thresholds."
            )
            return

        # Sort by most severe stock deficit first
        low_stock_df["Shortage Quantity"] = (
            low_stock_df["min_threshold"] - low_stock_df["effective_stock"]
        )
        low_stock_df = low_stock_df.sort_values(
            by="Shortage Quantity", ascending=False
        )

        # Top Warning Banner
        st.warning(
            f"⚠️ **Attention Required:** There are **{len(low_stock_df)}** item(s) running low on available stock."
        )

        # Data Display
        df_display = low_stock_df.rename(
            columns={
                "id": "ID",
                "item_name": "Item Description",
                "category": "Category",
                "unit": "Unit",
                "current_stock": "Physical Stock",
                "reserved_stock": "Reserved",
                "effective_stock": "Available Stock",
                "min_threshold": "Min Threshold",
                "remarks": "Storage / Remarks",
            }
        )

        st.dataframe(
            df_display[
                [
                    "ID",
                    "Item Description",
                    "Category",
                    "Unit",
                    "Physical Stock",
                    "Reserved",
                    "Available Stock",
                    "Min Threshold",
                    "Shortage Quantity",
                    "Storage / Remarks",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Physical Stock": st.column_config.NumberColumn(format="%.2f"),
                "Reserved": st.column_config.NumberColumn(format="%.2f"),
                "Available Stock": st.column_config.NumberColumn(format="%.2f"),
                "Shortage Quantity": st.column_config.NumberColumn(format="%.2f"),
            },
        )

        st.divider()

        # Quick Reorder / Schedule Delivery Helper
        st.subheader("📅 Schedule Quick Restock Shipment")

        with st.form("quick_schedule_form", clear_on_submit=True):
            col1, col2 = st.columns(2)

            with col1:
                selected_item = st.selectbox(
                    "Select Low Stock Item", low_stock_df["item_name"].tolist()
                )

                # Fetch unit and default shortage quantity for selected item
                item_info = low_stock_df[
                    low_stock_df["item_name"] == selected_item
                ].iloc[0]
                suggested_qty = max(1.0, float(item_info["Shortage Quantity"]))

                expected_qty = st.number_input(
                    "Expected Restock Quantity*",
                    min_value=0.1,
                    value=suggested_qty,
                    step=1.0,
                    format="%.2f",
                )
                st.text_input(
                    "Unit of Measure",
                    value=str(item_info["unit"]),
                    disabled=True,
                )

            with col2:
                scheduled_date = st.date_input("Expected Delivery Date*")
                supplier = st.text_input(
                    "Supplier / Source", placeholder="e.g., Prime Steel Corp"
                )
                schedule_remarks = st.text_input(
                    "Delivery Remarks", placeholder="e.g., Urgent site delivery"
                )

            submit_schedule = st.form_submit_button(
                "➕ Add to Delivery Schedules", use_container_width=True
            )

            if submit_schedule:
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            INSERT INTO schedules (scheduled_date, item_name, expected_quantity, unit, supplier, status, remarks)
                            VALUES (?, ?, ?, ?, ?, 'PENDING', ?)
                        """,
                            (
                                str(scheduled_date),
                                selected_item,
                                expected_qty,
                                item_info["unit"],
                                supplier.strip(),
                                schedule_remarks.strip(),
                            ),
                        )
                        conn.commit()
                        st.toast(
                            f"✅ Restock scheduled for {selected_item}!", icon="📅"
                        )
                        st.success(
                            f"Created pending delivery schedule for **{selected_item}** on {scheduled_date}."
                        )
                except sqlite3.OperationalError as e:
                    st.error(f"Failed to schedule delivery: {e}")

    except Exception as e:
        st.error(f"Error loading low stock alerts: {e}")
