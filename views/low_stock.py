import sqlite3
import pandas as pd
import streamlit as st
from database import get_db, backup_db_to_gdrive


def render_low_stock(user_name: str, user_role: str):
    st.title("⚠️ Low Stock Alerts")
    st.caption(
        "Monitor items below minimum safety thresholds and queue restock orders based on effective stock."
    )

    try:
        with get_db() as conn:
            # Fetch master items and compute effective available stock
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
            st.info("ℹ️ No inventory items found in the master catalog.")
            return

        # Calculate effective stock and shortage deficit
        df["effective_stock"] = df["current_stock"] - df["reserved_stock"]
        df["Shortage Quantity"] = (df["min_threshold"] - df["effective_stock"]).clip(lower=0)

        # Filter items breaching safety thresholds
        low_stock_df = df[df["effective_stock"] <= df["min_threshold"]].copy()

        # Overview KPI Metrics
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Total Catalog Items", len(df))
        col_m2.metric("Low Stock Items", len(low_stock_df), delta=-len(low_stock_df), delta_color="inverse")
        critical_count = len(low_stock_df[low_stock_df["effective_stock"] <= 0])
        col_m3.metric("Critical Out of Stock", critical_count, delta=-critical_count, delta_color="inverse")

        if low_stock_df.empty:
            st.success("✅ Great news! All inventory items are currently above their minimum safety thresholds.")
            return

        # Sort by most severe stock deficit first
        low_stock_df = low_stock_df.sort_values(by="Shortage Quantity", ascending=False)

        st.warning(
            f"⚠️ **Attention Required:** There are **{len(low_stock_df)}** item(s) running low on available stock."
        )

        # Prepare Display DataFrame
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
                "Min Threshold": st.column_config.NumberColumn(format="%.2f"),
            },
        )

        st.divider()

        # Quick Reorder / Schedule Delivery Helper
        st.subheader("📅 Schedule Restock Delivery")

        item_options = low_stock_df["item_name"].tolist()
        selected_item = st.selectbox("Select Low Stock Item", item_options, key="low_stock_selector")

        # Fetch details for the selected item dynamically
        selected_info = low_stock_df[low_stock_df["item_name"] == selected_item].iloc[0]
        suggested_qty = float(max(1.0, selected_info["Shortage Quantity"]))

        with st.form("quick_schedule_form", clear_on_submit=True):
            col1, col2 = st.columns(2)

            with col1:
                expected_qty = st.number_input(
                    f"Expected Restock Quantity ({selected_info['unit']})*",
                    min_value=0.01,
                    value=suggested_qty,
                    step=1.0,
                    format="%.2f",
                )
                supplier = st.text_input("Supplier / Source", placeholder="e.g., Prime Steel Corp")

            with col2:
                expected_date = st.date_input("Expected Delivery Date*")
                schedule_notes = st.text_input("Delivery Notes", placeholder="e.g., Urgent site restock")

            submit_schedule = st.form_submit_button("➕ Schedule Delivery", use_container_width=True)

            if submit_schedule:
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            INSERT INTO deliveries (item_name, expected_quantity, unit, supplier, expected_date, status, notes)
                            VALUES (?, ?, ?, ?, ?, 'PENDING', ?)
                            """,
                            (
                                selected_item,
                                expected_qty,
                                selected_info["unit"],
                                supplier.strip(),
                                str(expected_date),
                                schedule_notes.strip(),
                            ),
                        )
                        conn.commit()

                    # Trigger backup sync to Drive
                    backup_db_to_gdrive()

                    st.toast(f"✅ Delivery scheduled for {selected_item}!", icon="📅")
                    st.success(
                        f"Successfully logged pending delivery for **{selected_item}** ({expected_qty} {selected_info['unit']}) arriving on {expected_date}."
                    )
                except sqlite3.OperationalError as e:
                    st.error(f"Failed to record delivery schedule: {e}")

    except Exception as e:
        st.error(f"Error loading low stock alerts: {e}")


if __name__ == "__main__":
    render_low_stock("Admin", "Admin")
