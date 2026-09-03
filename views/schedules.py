# views/schedules.py
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db, init_db

def render_schedules(user_name, user_role):
    st.title("📅 Schedules & Deliveries")
    st.caption("Manage upcoming site deliveries, expected material shipments, and supplier schedules.")

    init_db()

    # Action Tabs
    tab_list, tab_add = st.tabs(["📋 Delivery Schedule List", "➕ Schedule New Delivery"])

    # -------------------------------------------------------------
    # TAB 1: SCHEDULE LIST & STATUS MANAGEMENT
    # -------------------------------------------------------------
    with tab_list:
        st.subheader("Upcoming & Historic Deliveries")
        
        filter_status = st.selectbox("Filter Status", ["All", "PENDING", "DELIVERED", "CANCELLED"], key="sched_filter_status")

        query = "SELECT id, scheduled_date, item_name, expected_quantity, unit, supplier, status, remarks FROM schedules WHERE 1=1"
        params = []

        if filter_status != "All":
            query += " AND status = ?"
            params.append(filter_status)

        query += " ORDER BY scheduled_date ASC, id DESC"

        try:
            with get_db() as conn:
                df = pd.read_sql_query(query, conn, params=params)

            if not df.empty:
                df_display = df.rename(columns={
                    "id": "ID",
                    "scheduled_date": "Scheduled Date",
                    "item_name": "Item Description",
                    "expected_quantity": "Expected Qty",
                    "unit": "Unit",
                    "supplier": "Supplier",
                    "status": "Status",
                    "remarks": "Remarks"
                })
                st.dataframe(df_display, use_container_width=True, hide_index=True)

                st.divider()
                st.subheader("🔄 Update Delivery Status")
                
                # Status Update Form
                with st.form("update_schedule_status_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        pending_df = df[df["status"] == "PENDING"]
                        if not pending_df.empty:
                            sched_options = [f"#{row['id']} - {row['item_name']} ({row['scheduled_date']})" for _, row in pending_df.iterrows()]
                            selected_sched = st.selectbox("Select Pending Delivery", sched_options)
                        else:
                            st.info("No pending deliveries available to update.")
                            selected_sched = None

                    with col2:
                        new_status = st.selectbox("New Status", ["DELIVERED", "CANCELLED"])

                    submit_update = st.form_submit_button("Update Status", use_container_width=True)

                    if submit_update and selected_sched:
                        sched_id = int(selected_sched.split("#")[1].split(" ")[0])
                        try:
                            with get_db() as conn:
                                cursor = conn.cursor()
                                cursor.execute("UPDATE schedules SET status = ? WHERE id = ?", (new_status, sched_id))
                                conn.commit()
                                st.success(f"✅ Schedule #{sched_id} status updated to '{new_status}'.")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Failed to update schedule status: {e}")
            else:
                st.info("No delivery schedules found matching the criteria.")

        except Exception as e:
            st.error(f"Error loading delivery schedules: {e}")

    # -------------------------------------------------------------
    # TAB 2: SCHEDULE NEW DELIVERY
    # -------------------------------------------------------------
    with tab_add:
        st.subheader("Log Expected Supplier Shipment")

        # Fetch master item list for dropdown
        try:
            with get_db() as conn:
                df_master = pd.read_sql_query("SELECT item_name, unit FROM master_items ORDER BY item_name ASC", conn)
            master_items = df_master["item_name"].tolist() if not df_master.empty else []
        except Exception:
            master_items = []

        with st.form("add_schedule_form", clear_on_submit=True):
            col1, col2 = st.columns(2)

            with col1:
                if master_items:
                    selected_item = st.selectbox("Item Description*", master_items, key="sched_item_select")
                    item_unit = df_master[df_master["item_name"] == selected_item]["unit"].values[0]
                else:
                    selected_item = st.text_input("Item Description*", placeholder="e.g., Cement Bags")
                    item_unit = "Pcs"

                expected_qty = st.number_input("Expected Quantity*", min_value=0.1, value=100.0, step=1.0)
                unit_display = st.text_input("Unit of Measure", value=item_unit, disabled=True)

            with col2:
                scheduled_date = st.date_input("Scheduled Arrival Date*")
                supplier = st.text_input("Supplier Name / Contractor", placeholder="e.g., Northern Concrete Corp")
                remarks = st.text_input("Remarks", placeholder="e.g., Batch 1 delivery")

            submit_add = st.form_submit_button("💾 Save Delivery Schedule", use_container_width=True)

            if submit_add:
                if not selected_item:
                    st.error("⚠️ Please select or provide an item description.")
                else:
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO schedules (scheduled_date, item_name, expected_quantity, unit, supplier, status, remarks)
                                VALUES (?, ?, ?, ?, ?, 'PENDING', ?)
                            """, (str(scheduled_date), selected_item, expected_qty, item_unit, supplier.strip(), remarks.strip()))
                            conn.commit()
                            st.success(f"✅ Delivery schedule created for **{selected_item}** on {scheduled_date}.")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save schedule: {e}")
