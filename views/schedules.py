# views/schedules.py
import pandas as pd
import streamlit as st
from database import get_db, init_db

def render_schedules(user_name, user_role):
    st.title("🚚 Schedules & Deliveries")
    st.caption("Track incoming material shipments, dispatch schedules, and delivery statuses.")

    init_db()

    tab_overview, tab_add = st.tabs([
        "📅 Delivery Schedules", 
        "➕ Schedule New Delivery"
    ])

    # OVERVIEW TAB
    with tab_overview:
        st.subheader("Upcoming & Active Deliveries")
        try:
            with get_db() as conn:
                df = pd.read_sql_query("""
                    SELECT id, item_name, supplier_or_destination, quantity, unit, scheduled_date, status, notes
                    FROM deliveries
                    ORDER BY scheduled_date ASC
                """, conn)

            if not df.empty:
                col_status, col_search = st.columns([1, 2])
                with col_status:
                    status_filter = st.selectbox("Filter Status", ["All", "Pending", "In Transit", "Completed", "Cancelled"])
                with col_search:
                    search_query = st.text_input("🔍 Search Item / Supplier / Destination", placeholder="e.g., Cement, Main Site...")

                filtered_df = df.copy()
                if status_filter != "All":
                    filtered_df = filtered_df[filtered_df["status"] == status_filter]
                if search_query.strip():
                    filtered_df = filtered_df[
                        filtered_df["item_name"].str.contains(search_query.strip(), case=False, na=False) |
                        filtered_df["supplier_or_destination"].str.contains(search_query.strip(), case=False, na=False)
                    ]

                st.divider()

                for idx, row in filtered_df.iterrows():
                    with st.expander(f"📦 {row['item_name']} - {row['scheduled_date']} [{row['status']}]"):
                        c1, c2, c3 = st.columns(3)
                        c1.markdown(f"**Supplier/Destination:** {row['supplier_or_destination']}")
                        c2.markdown(f"**Quantity:** {row['quantity']} {row['unit']}")
                        c3.markdown(f"**Status:** `{row['status']}`")

                        if row["notes"]:
                            st.caption(f"**Notes:** {row['notes']}")

                        new_status = st.selectbox(
                            "Update Status", 
                            ["Pending", "In Transit", "Completed", "Cancelled"], 
                            index=["Pending", "In Transit", "Completed", "Cancelled"].index(row["status"]),
                            key=f"status_select_{row['id']}"
                        )

                        if new_status != row["status"]:
                            if st.button("Save Status Change", key=f"btn_status_{row['id']}"):
                                try:
                                    with get_db() as conn_update:
                                        cursor = conn_update.cursor()
                                        cursor.execute("UPDATE deliveries SET status = ? WHERE id = ?", (new_status, row['id']))
                                        conn_update.commit()
                                        st.success("Status updated successfully!")
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"Error updating delivery status: {e}")
            else:
                st.info("No delivery schedules recorded yet.")
        except Exception as e:
            st.error(f"Error loading delivery schedules: {e}")

    # NEW DELIVERY TAB
    with tab_add:
        st.subheader("Add Delivery Schedule")
        with st.form("add_delivery_form"):
            col1, col2 = st.columns(2)
            with col1:
                item_name = st.text_input("Item Name*", placeholder="e.g., Ready-Mix Concrete").strip()
                supplier_dest = st.text_input("Supplier or Destination*", placeholder="e.g., Supplier ABC / Site B").strip()
                scheduled_date = st.date_input("Scheduled Date")
            with col2:
                quantity = st.number_input("Quantity*", min_value=0.01, value=1.0, step=1.0)
                unit = st.text_input("Unit*", placeholder="e.g., bags, cu.m, pcs").strip()
                status = st.selectbox("Initial Status", ["Pending", "In Transit", "Completed"])

            notes = st.text_input("Notes / Special Instructions", placeholder="e.g., Requires forklift unloader")
            submit_btn = st.form_submit_button("📅 Schedule Delivery", use_container_width=True)

            if submit_btn:
                if not item_name or not supplier_dest or not unit:
                    st.error("⚠️ Item Name, Supplier/Destination, and Unit are required.")
                else:
                    try:
                        with get_db() as conn_add:
                            cursor = conn_add.cursor()
                            cursor.execute("""
                                INSERT INTO deliveries (item_name, supplier_or_destination, quantity, unit, scheduled_date, status, notes, created_by)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (item_name, supplier_dest, quantity, unit, str(scheduled_date), status, notes, user_name))
                            conn_add.commit()
                            st.success(f"✅ Delivery for **{item_name}** scheduled successfully!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Failed to create schedule: {e}")
