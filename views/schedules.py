import sqlite3
import pandas as pd
import streamlit as st
from database import get_db, init_db

def ensure_schedule_columns():
    """Ensure Stock Out fields exist on the deliveries table."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(deliveries)")
            existing_cols = [col[1] for col in cursor.fetchall()]

            new_cols = {
                "requested_by": "TEXT",
                "destination": "TEXT",
                "project": "TEXT",
                "is_priority": "INTEGER DEFAULT 0",
                "driver_name": "TEXT"
            }

            for col_name, col_type in new_cols.items():
                if col_name not in existing_cols:
                    cursor.execute(f"ALTER TABLE deliveries ADD COLUMN {col_name} {col_type}")

            conn.commit()
    except Exception as e:
        st.error(f"Error initializing delivery schema: {e}")

def render_delivery_card(row):
    """Reusable function to render individual delivery item expansion and status update form."""
    prio_badge = "🔥 HIGH PRIORITY | " if row['is_priority'] == 1 else ""
    project_info = f" ({row['project']})" if row['project'] else ""
    header_label = f"{prio_badge}📦 {row['item_name']} - {row['scheduled_date']} [{row['status']}] -> {row['destination']}{project_info}"
    
    with st.expander(header_label):
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**Requested By:** {row['requested_by'] if row['requested_by'] else 'N/A'}")
        c1.markdown(f"**Destination:** {row['destination']}")
        
        c2.markdown(f"**Project:** {row['project'] if row['project'] else 'N/A'}")
        c2.markdown(f"**Quantity:** {row['quantity']} {row['unit']}")
        
        c3.markdown(f"**Priority:** {'🔴 **HIGH**' if row['is_priority'] == 1 else '🟢 Normal'}")
        c3.markdown(f"**Status:** `{row['status']}`")

        if row["driver_name"]:
            st.markdown(f"🚛 **Driver Name:** {row['driver_name']}")

        if row["notes"]:
            st.caption(f"**Notes:** {row['notes']}")

        st.divider()

        status_options = ["Pending", "In Transit", "Completed", "Cancelled"]
        current_idx = status_options.index(row["status"]) if row["status"] in status_options else 0

        new_status = st.selectbox(
            "Update Status", 
            status_options, 
            index=current_idx,
            key=f"status_select_{row['id']}"
        )

        # Additional fields conditional on selecting "Completed"
        driver_input = row["driver_name"]
        add_notes_input = ""

        if new_status == "Completed":
            st.markdown("##### 📝 Completion Details")
            col_driver, col_notes = st.columns(2)
            with col_driver:
                driver_input = st.text_input(
                    "Driver Name*", 
                    value=row["driver_name"], 
                    placeholder="e.g., John Doe",
                    key=f"driver_input_{row['id']}"
                ).strip()
            with col_notes:
                add_notes_input = st.text_input(
                    "Additional Completion Notes", 
                    placeholder="e.g., Received by site supervisor; gate pass #1024",
                    key=f"add_notes_{row['id']}"
                ).strip()

        if new_status != row["status"] or (new_status == "Completed" and driver_input != row["driver_name"]):
            if st.button("Save Changes", key=f"btn_status_{row['id']}", use_container_width=True):
                if new_status == "Completed" and not driver_input:
                    st.error("⚠️ Please specify the Driver Name before marking the dispatch as Completed.")
                else:
                    try:
                        with get_db() as conn_update:
                            cursor = conn_update.cursor()
                            old_status = row["status"]
                            qty = float(row["quantity"])
                            item_name = row["item_name"]

                            # Combine notes if extra completion notes were added
                            existing_notes = str(row['notes']).strip() if row['notes'] else ""
                            final_notes = existing_notes
                            if add_notes_input:
                                final_notes = f"{existing_notes} [Completed Note: {add_notes_input}]".strip()

                            # Update Delivery Record Status, Driver, and Notes
                            cursor.execute("""
                                UPDATE deliveries 
                                SET status = ?, driver_name = ?, notes = ? 
                                WHERE id = ?
                            """, (new_status, driver_input, final_notes, row['id']))

                            # Adjust Stock based on Status Transitions
                            if old_status in ["Pending", "In Transit"]:
                                if new_status == "Completed":
                                    cursor.execute("""
                                        UPDATE master_items 
                                        SET current_stock = current_stock - ?,
                                            reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?)
                                        WHERE item_name = ?
                                    """, (qty, qty, item_name))

                                elif new_status == "Cancelled":
                                    cursor.execute("""
                                        UPDATE master_items 
                                        SET reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?)
                                        WHERE item_name = ?
                                    """, (qty, item_name))

                            conn_update.commit()
                            st.success(f"Status updated to {new_status} and inventory adjusted accordingly!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error updating delivery status: {e}")

def render_schedules(user_name, user_role):
    st.title("🚚 Stock Out Delivery Schedules")
    st.caption("Schedule outbound material dispatches, reserve shop stock, and track project deliveries.")

    init_db()
    ensure_schedule_columns()

    tab_overview, tab_add = st.tabs([
        "📅 Dispatch Overview", 
        "➕ Schedule Stock Out Delivery"
    ])

    # -------------------------------------------------------------
    # TAB 1: OVERVIEW & STATUS MANAGEMENT
    # -------------------------------------------------------------
    with tab_overview:
        st.subheader("Dispatches Overview")
        try:
            with get_db() as conn:
                query = """
                    SELECT id, item_name, 
                           COALESCE(requested_by, '') AS requested_by,
                           COALESCE(destination, supplier, '') AS destination,
                           COALESCE(project, '') AS project,
                           expected_quantity AS quantity, unit, 
                           expected_date AS scheduled_date, status, notes,
                           COALESCE(is_priority, 0) AS is_priority,
                           COALESCE(driver_name, '') AS driver_name
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
                    search_query = st.text_input("🔍 Search Item / Requested By / Destination / Driver", placeholder="e.g., Cement, Main Site, Driver John...")

                filtered_df = df.copy()
                if status_filter != "All":
                    filtered_df = filtered_df[filtered_df["status"] == status_filter]
                
                if prio_filter == "High Priority Only":
                    filtered_df = filtered_df[filtered_df["is_priority"] == 1]
                elif prio_filter == "Normal Only":
                    filtered_df = filtered_df[filtered_df["is_priority"] == 0]

                if search_query.strip():
                    q = search_query.strip().lower()
                    filtered_df = filtered_df[
                        filtered_df["item_name"].str.lower().str.contains(q, na=False) |
                        filtered_df["requested_by"].str.lower().str.contains(q, na=False) |
                        filtered_df["destination"].str.lower().str.contains(q, na=False) |
                        filtered_df["project"].str.lower().str.contains(q, na=False) |
                        filtered_df["driver_name"].str.lower().str.contains(q, na=False)
                    ]

                st.divider()

                # Separate Active vs Completed/Cancelled DataFrames
                active_df = filtered_df[filtered_df["status"].isin(["Pending", "In Transit"])]
                completed_df = filtered_df[filtered_df["status"].isin(["Completed", "Cancelled"])]

                # Split Screen into 2 Columns
                col_active, col_completed = st.columns(2)

                # --- COLUMN 1: Active Deliveries ---
                with col_active:
                    st.markdown(f"### 🚚 Active Deliveries ({len(active_df)})")
                    st.caption("Pending or In Transit Dispatches")
                    st.divider()
                    
                    if not active_df.empty:
                        for idx, row in active_df.iterrows():
                            render_delivery_card(row)
                    else:
                        st.info("No active deliveries found.")

                # --- COLUMN 2: Completed & Cancelled Deliveries ---
                with col_completed:
                    st.markdown(f"### ✅ Completed & History ({len(completed_df)})")
                    st.caption("Finished or Cancelled Dispatches")
                    st.divider()

                    if not completed_df.empty:
                        for idx, row in completed_df.iterrows():
                            render_delivery_card(row)
                    else:
                        st.info("No completed or cancelled deliveries found.")

            else:
                st.info("No delivery dispatches scheduled yet.")
        except Exception as e:
            st.error(f"Error loading delivery dispatches: {e}")

    # -------------------------------------------------------------
    # TAB 2: SCHEDULE NEW STOCK OUT DELIVERY (RESERVE STOCK)
    # -------------------------------------------------------------
    with tab_add:
        st.subheader("Schedule New Stock Out Delivery")

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
                selected_item_name = st.selectbox("Select Item to Dispatch*", df_master["item_name"].tolist())
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
                        requested_by = st.text_input("Requested By*", placeholder="e.g., Engr. John Doe").strip()
                        destination = st.text_input("Destination / Site Location*", placeholder="e.g., Block 4 Site").strip()
                        project = st.text_input("Project Name / Code*", placeholder="e.g., Bridge Construction Phase 1").strip()
                    
                    with col2:
                        quantity = st.number_input(f"Quantity to Reserve ({unit_name})*", min_value=0.01, value=None, placeholder="0.0")
                        scheduled_date = st.date_input("Scheduled Delivery Date")
                        status = st.selectbox("Initial Status", ["Pending", "In Transit"])

                    driver_name_initial = st.text_input("Assigned Driver Name (Optional)", placeholder="e.g., John Doe").strip()
                    is_priority = st.checkbox("🔥 Mark as High Priority Delivery", help="High priority stock out deliveries appear prominently at the top of dispatches.")
                    notes = st.text_input("Notes / Delivery Instructions", placeholder="e.g., Deliver via 10-wheeler truck; contact site engineer upon arrival")
                    
                    submit_btn = st.form_submit_button("📅 Schedule Stock Out & Reserve Inventory", use_container_width=True)

                    if submit_btn:
                        if not requested_by or not destination or not project or quantity is None:
                            st.error("⚠️ Requested By, Destination, Project, and Quantity are required fields.")
                        elif quantity > stock_available:
                            st.error(f"❌ Cannot reserve stock! Requested Quantity ({quantity} {unit_name}) exceeds Available Stock ({stock_available} {unit_name}).")
                        else:
                            try:
                                with get_db() as conn_add:
                                    cursor = conn_add.cursor()
                                    
                                    priority_val = 1 if is_priority else 0

                                    # 1. Save Stock Out Delivery Record
                                    cursor.execute("""
                                        INSERT INTO deliveries (
                                            item_name, supplier, requested_by, destination, project, 
                                            expected_quantity, unit, expected_date, status, notes, is_priority, driver_name
                                        )
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """, (
                                        selected_item_name, destination, requested_by, destination, project,
                                        quantity, unit_name, str(scheduled_date), status, notes.strip(), priority_val, driver_name_initial
                                    ))

                                    # 2. Increase Reserved Stock on Master Item
                                    cursor.execute("""
                                        UPDATE master_items
                                        SET reserved_stock = COALESCE(reserved_stock, 0) + ?
                                        WHERE item_name = ?
                                    """, (quantity, selected_item_name))

                                    conn_add.commit()
                                    st.success(f"✅ Stock Out for **{selected_item_name}** scheduled to **{destination}** ({project}) and {quantity} {unit_name} reserved!")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Failed to create schedule: {e}")
            else:
                st.warning("⚠️ No master items found. Please add items to the Master Catalog first.")

        except Exception as e:
            st.error(f"Error fetching catalog items: {e}")
