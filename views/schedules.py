# views/schedules.py
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db, init_db

def ensure_priority_column():
    """Ensure the is_priority column exists on the deliveries table."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(deliveries)")
            columns = [col[1] for col in cursor.fetchall()]
            if "is_priority" not in columns:
                cursor.execute("ALTER TABLE deliveries ADD COLUMN is_priority INTEGER DEFAULT 0")
                conn.commit()
    except Exception as e:
        st.error(f"Error initializing priority schema: {e}")

def render_schedules(user_name, user_role):
    st.title("🚚 Schedules & Deliveries")
    st.caption("Track material shipments, dispatch schedules, and real-time reserved inventory.")

    init_db()
    ensure_priority_column()

    tab_overview, tab_add = st.tabs([
        "📅 Delivery Schedules", 
        "➕ Schedule New Delivery"
    ])

    # -------------------------------------------------------------
    # TAB 1: OVERVIEW & STATUS MANAGEMENT
    # -------------------------------------------------------------
    with tab_overview:
        st.subheader("Upcoming & Active Deliveries")
        try:
            with get_db() as conn:
                query = """
                    SELECT id, item_name, supplier AS supplier_or_destination, 
                           expected_quantity AS quantity, unit, 
                           expected_date AS scheduled_date, status, notes,
                           COALESCE(is_priority, 0) AS is_priority
                    FROM deliveries 
                    ORDER BY is_priority DESC, expected_date ASC
                """
                df = pd.read_sql_query(query, conn)

            if not df.empty:
                col_status, col_prio, col_search = st.columns([1, 1, 2])
                with col_status:
                    status_filter = st.selectbox("Filter Status", ["All", "Pending", "In Transit", "Completed", "Cancelled"])
                with col_prio:
                    prio_filter = st.selectbox("Priority Filter", ["All", "High Priority Only", "Normal Only"])
                with col_search:
                    search_query = st.text_input("🔍 Search Item / Supplier / Destination", placeholder="e.g., Cement, Main Site...")

                filtered_df = df.copy()
                if status_filter != "All":
                    filtered_df = filtered_df[filtered_df["status"] == status_filter]
                
                if prio_filter == "High Priority Only":
                    filtered_df = filtered_df[filtered_df["is_priority"] == 1]
                elif prio_filter == "Normal Only":
                    filtered_df = filtered_df[filtered_df["is_priority"] == 0]

                if search_query.strip():
                    filtered_df = filtered_df[
                        filtered_df["item_name"].str.contains(search_query.strip(), case=False, na=False) |
                        filtered_df["supplier_or_destination"].str.contains(search_query.strip(), case=False, na=False)
                    ]

                st.divider()

                for idx, row in filtered_df.iterrows():
                    prio_badge = "🔥 HIGH PRIORITY | " if row['is_priority'] == 1 else ""
                    header_label = f"{prio_badge}📦 {row['item_name']} - {row['scheduled_date']} [{row['status']}]"
                    
                    with st.expander(header_label):
                        c1, c2, c3 = st.columns(3)
                        c1.markdown(f"**Supplier/Destination:** {row['supplier_or_destination']}")
                        c2.markdown(f"**Quantity:** {row['quantity']} {row['unit']}")
                        c3.markdown(f"**Priority:** {'🔴 **HIGH**' if row['is_priority'] == 1 else '🟢 Normal'}")

                        if row["notes"]:
                            st.caption(f"**Notes:** {row['notes']}")

                        status_options = ["Pending", "In Transit", "Completed", "Cancelled"]
                        current_idx = status_options.index(row["status"]) if row["status"] in status_options else 0

                        col_sel, col_btn = st.columns([2, 1])
                        with col_sel:
                            new_status = st.selectbox(
                                "Update Status", 
                                status_options, 
                                index=current_idx,
                                key=f"status_select_{row['id']}"
                            )

                        if new_status != row["status"]:
                            with col_btn:
                                st.write("") # Alignment spacing
                                if st.button("Save Status", key=f"btn_status_{row['id']}"):
                                    try:
                                        with get_db() as conn_update:
                                            cursor = conn_update.cursor()
                                            old_status = row["status"]
                                            qty = float(row["quantity"])
                                            item_name = row["item_name"]

                                            # Update Delivery Record
                                            cursor.execute("UPDATE deliveries SET status = ? WHERE id = ?", (new_status, row['id']))

                                            # Adjust Stock based on Status Transitions
                                            if old_status in ["Pending", "In Transit"]:
                                                if new_status == "Completed":
                                                    # Deduct physical stock and release reservation
                                                    cursor.execute("""
                                                        UPDATE master_items 
                                                        SET current_stock = current_stock - ?,
                                                            reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?)
                                                        WHERE item_name = ?
                                                    """, (qty, qty, item_name))

                                                elif new_status == "Cancelled":
                                                    # Release reservation back to available stock
                                                    cursor.execute("""
                                                        UPDATE master_items 
                                                        SET reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?)
                                                        WHERE item_name = ?
                                                    """, (qty, item_name))

                                            conn_update.commit()
                                            st.success(f"Status updated to {new_status} and stock adjusted accordingly!")
                                            st.rerun()
                                    except Exception as e:
                                        st.error(f"Error updating delivery status: {e}")
            else:
                st.info("No delivery schedules recorded yet.")
        except Exception as e:
            st.error(f"Error loading delivery schedules: {e}")

    # -------------------------------------------------------------
    # TAB 2: SCHEDULE NEW DELIVERY (RESERVE STOCK)
    # -------------------------------------------------------------
    with tab_add:
        st.subheader("Add Delivery Schedule & Reserve Stock")

        try:
            with get_db() as conn_items:
                df_master = pd.read_sql_query("""
                    SELECT item_name, unit, current_stock, 
                           COALESCE(reserved_stock, 0) AS reserved_stock,
                           (current_stock - COALESCE(reserved_stock, 0)) AS available_stock
                    FROM master_items 
                    ORDER BY item_name ASC
                """, conn_items)

            if not df_master.empty:
                selected_item_name = st.selectbox("Select Master Item*", df_master["item_name"].tolist())
                item_info = df_master[df_master["item_name"] == selected_item_name].iloc[0]

                stock_in_shop = float(item_info["current_stock"])
                stock_reserved = float(item_info["reserved_stock"])
                stock_available = float(item_info["available_stock"])
                unit_name = str(item_info["unit"])

                # Metric visualizer
                m1, m2, m3 = st.columns(3)
                m1.metric("Stock In Shop (Total)", f"{stock_in_shop:,.2f} {unit_name}")
                m2.metric("Reserved Stock", f"{stock_reserved:,.2f} {unit_name}")
                m3.metric("Available Stock", f"{stock_available:,.2f} {unit_name}")

                st.divider()

                with st.form("add_delivery_form", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        supplier_dest = st.text_input("Supplier or Destination*", placeholder="e.g., Block 4 Site").strip()
                        scheduled_date = st.date_input("Scheduled Date")
                    with col2:
                        quantity = st.number_input("Quantity to Reserve*", min_value=0.01, value=None, placeholder="0.0")
                        status = st.selectbox("Initial Status", ["Pending", "In Transit"])

                    is_priority = st.checkbox("🔥 Mark as High Priority Delivery", help="High priority deliveries appear prominently at the top of schedules.")
                    notes = st.text_input("Notes / Special Instructions", placeholder="e.g., Requires forklift unloader")
                    
                    submit_btn = st.form_submit_button("📅 Confirm Schedule & Reserve Stock", use_container_width=True)

                    if submit_btn:
                        if not supplier_dest or quantity is None:
                            st.error("⚠️ Supplier/Destination and Quantity are required.")
                        elif quantity > stock_available:
                            st.error(f"❌ Cannot reserve stock! Quantity ({quantity}) exceeds Available Stock ({stock_available} {unit_name}).")
                        else:
                            try:
                                with get_db() as conn_add:
                                    cursor = conn_add.cursor()
                                    
                                    priority_val = 1 if is_priority else 0

                                    # 1. Save Delivery Record
                                    cursor.execute("""
                                        INSERT INTO deliveries (item_name, supplier, expected_quantity, unit, expected_date, status, notes, is_priority)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                    """, (selected_item_name, supplier_dest, quantity, unit_name, str(scheduled_date), status, notes.strip(), priority_val))

                                    # 2. Increase Reserved Stock on Master Item
                                    cursor.execute("""
                                        UPDATE master_items
                                        SET reserved_stock = COALESCE(reserved_stock, 0) + ?
                                        WHERE item_name = ?
                                    """, (quantity, selected_item_name))

                                    conn_add.commit()
                                    st.success(f"✅ Delivery for **{selected_item_name}** scheduled and {quantity} {unit_name} reserved!")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Failed to create schedule: {e}")
            else:
                st.warning("⚠️ No master items found. Please add items to the Master Catalog first.")

        except Exception as e:
            st.error(f"Error fetching catalog items: {e}")
