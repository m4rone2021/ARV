import sqlite3
import pandas as pd
import streamlit as st
import uuid
from datetime import datetime
from database import get_db, init_db

def ensure_schedule_columns():
    """Ensure Stock Out fields exist on the deliveries table."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(deliveries)")
            existing_cols = [col[1] for col in cursor.fetchall()]

            new_cols = {
                "dispatch_id": "TEXT",
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

def render_dispatch_card(dispatch_id, items_df):
    """Render a single unified dispatch card containing multiple items."""
    first_row = items_df.iloc[0]
    prio_badge = "🔥 HIGH PRIORITY | " if first_row['is_priority'] == 1 else ""
    project_info = f" ({first_row['project']})" if first_row['project'] else ""
    disp_label = f"{dispatch_id}" if dispatch_id else "Legacy Order"
    
    header_label = f"{prio_badge}🚛 [{disp_label}] {first_row['scheduled_date']} [{first_row['status']}] -> {first_row['destination']}{project_info}"
    
    with st.expander(header_label):
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**Requested By:** {first_row['requested_by'] if first_row['requested_by'] else 'N/A'}")
        c1.markdown(f"**Destination:** {first_row['destination']}")
        
        c2.markdown(f"**Project:** {first_row['project'] if first_row['project'] else 'N/A'}")
        c2.markdown(f"**Total Items in Dispatch:** `{len(items_df)}`")
        
        c3.markdown(f"**Priority:** {'🔴 **HIGH**' if first_row['is_priority'] == 1 else '🟢 Normal'}")
        c3.markdown(f"**Status:** `{first_row['status']}`")

        if first_row["driver_name"]:
            st.markdown(f"🚛 **Driver Name:** {first_row['driver_name']}")

        st.divider()
        st.markdown("##### 📦 Items Included in this Dispatch:")
        
        # Display table of items under this dispatch
        disp_table = items_df[['item_name', 'quantity', 'unit', 'notes']].rename(columns={
            'item_name': 'Item Name',
            'quantity': 'Quantity',
            'unit': 'Unit',
            'notes': 'Notes / Instructions'
        })
        st.dataframe(disp_table, use_container_width=True, hide_index=True)

        st.divider()

        status_options = ["Pending", "In Transit", "Completed", "Cancelled"]
        current_idx = status_options.index(first_row["status"]) if first_row["status"] in status_options else 0

        new_status = st.selectbox(
            "Update Status for ENTIRE Dispatch Batch", 
            status_options, 
            index=current_idx,
            key=f"status_select_{dispatch_id}_{first_row['id']}"
        )

        # Additional fields conditional on selecting "Completed"
        driver_input = first_row["driver_name"]
        add_notes_input = ""

        if new_status == "Completed":
            st.markdown("##### 📝 Completion Details")
            col_driver, col_notes = st.columns(2)
            with col_driver:
                driver_input = st.text_input(
                    "Driver Name*", 
                    value=first_row["driver_name"], 
                    placeholder="e.g., John Doe",
                    key=f"driver_input_{dispatch_id}_{first_row['id']}"
                ).strip()
            with col_notes:
                add_notes_input = st.text_input(
                    "Additional Completion Notes", 
                    placeholder="e.g., Received by site supervisor; gate pass #1024",
                    key=f"add_notes_{dispatch_id}_{first_row['id']}"
                ).strip()

        if new_status != first_row["status"] or (new_status == "Completed" and driver_input != first_row["driver_name"]):
            if st.button("Save Batch Status Changes", key=f"btn_status_{dispatch_id}_{first_row['id']}", use_container_width=True):
                if new_status == "Completed" and not driver_input:
                    st.error("⚠️ Please specify the Driver Name before marking the dispatch as Completed.")
                else:
                    try:
                        with get_db() as conn_update:
                            cursor = conn_update.cursor()
                            old_status = first_row["status"]

                            for _, item_row in items_df.iterrows():
                                qty = float(item_row["quantity"])
                                item_name = item_row["item_name"]
                                item_id = item_row["id"]

                                existing_notes = str(item_row['notes']).strip() if item_row['notes'] else ""
                                final_notes = existing_notes
                                if add_notes_input:
                                    final_notes = f"{existing_notes} [Completed Note: {add_notes_input}]".strip()

                                # Update Delivery Record
                                cursor.execute("""
                                    UPDATE deliveries 
                                    SET status = ?, driver_name = ?, notes = ? 
                                    WHERE id = ?
                                """, (new_status, driver_input, final_notes, item_id))

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
                            st.success(f"Dispatch status updated to {new_status} and inventory adjusted for all items!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error updating dispatch status: {e}")

def render_schedules(user_name, user_role):
    st.title("🚚 Stock Out Delivery Schedules")
    st.caption("Schedule outbound material dispatches, reserve shop stock, and track project deliveries.")

    init_db()
    ensure_schedule_columns()

    # Initialize delivery cart session state
    if "delivery_cart" not in st.session_state:
        st.session_state.delivery_cart = []
    
    if "current_dispatch_header" not in st.session_state:
        st.session_state.current_dispatch_header = None

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
                    SELECT id, 
                           COALESCE(dispatch_id, 'LEGACY-' || id) AS dispatch_id,
                           item_name, 
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
                    search_query = st.text_input("🔍 Search Item / Requested By / Destination / Driver / Dispatch ID", placeholder="e.g., DISP-1002, Cement, Main Site...")

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
                        filtered_df["dispatch_id"].str.lower().str.contains(q, na=False) |
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

                col_active, col_completed = st.columns(2)

                # --- COLUMN 1: Active Deliveries ---
                with col_active:
                    active_dispatches = active_df.groupby("dispatch_id", sort=False)
                    st.markdown(f"### 🚚 Active Dispatches ({len(active_dispatches)})")
                    st.caption("Pending or In Transit Dispatches")
                    st.divider()
                    
                    if not active_df.empty:
                        for disp_id, group in active_dispatches:
                            render_dispatch_card(disp_id, group)
                    else:
                        st.info("No active dispatches found.")

                # --- COLUMN 2: Completed & Cancelled Deliveries ---
                with col_completed:
                    completed_dispatches = completed_df.groupby("dispatch_id", sort=False)
                    st.markdown(f"### ✅ Completed & History ({len(completed_dispatches)})")
                    st.caption("Finished or Cancelled Dispatches")
                    st.divider()

                    if not completed_df.empty:
                        for disp_id, group in completed_dispatches:
                            render_dispatch_card(disp_id, group)
                    else:
                        st.info("No completed or cancelled dispatches found.")

            else:
                st.info("No delivery dispatches scheduled yet.")
        except Exception as e:
            st.error(f"Error loading delivery dispatches: {e}")

    # -------------------------------------------------------------
    # TAB 2: SCHEDULE NEW STOCK OUT DELIVERY (RESERVE STOCK)
    # -------------------------------------------------------------
    with tab_add:
        st.subheader("Schedule New Single Dispatch Batch")

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
                # If dispatch header exists, lock those values for the whole batch
                has_active_batch = bool(st.session_state.delivery_cart)
                header_data = st.session_state.current_dispatch_header or {}

                selected_item_name = st.selectbox("Select Item to Add to Dispatch*", df_master["item_name"].tolist())
                item_info = df_master[df_master["item_name"] == selected_item_name].iloc[0]

                stock_in_shop = float(item_info["current_stock"])
                stock_reserved = float(item_info["reserved_stock"])
                
                # Account for items already staged in this current dispatch batch
                staged_qty = sum(
                    item["quantity"] for item in st.session_state.delivery_cart 
                    if item["item_name"] == selected_item_name
                )
                stock_available = float(item_info["available_stock"]) - staged_qty
                unit_name = str(item_info["unit"])

                # Metric visualizer
                m1, m2, m3 = st.columns(3)
                m1.metric("Stock In Shop (Total)", f"{stock_in_shop:,.2f} {unit_name}")
                m2.metric("Reserved Stock", f"{stock_reserved:,.2f} {unit_name}")
                m3.metric("Available Stock", f"{stock_available:,.2f} {unit_name}")

                st.divider()

                if has_active_batch:
                    st.info(f"🔒 **Dispatch Order Details Locked:** Adding items to active dispatch for **{header_data.get('requested_by')}** -> **{header_data.get('destination')}** ({header_data.get('project')})")

                # Add Item Form
                with st.form("add_dispatch_item_form", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        requested_by = st.text_input(
                            "Requested By*", 
                            value=header_data.get("requested_by", ""),
                            disabled=has_active_batch,
                            placeholder="e.g., Engr. John Doe"
                        ).strip()
                        
                        destination = st.text_input(
                            "Destination / Site Location*", 
                            value=header_data.get("destination", ""),
                            disabled=has_active_batch,
                            placeholder="e.g., Block 4 Site"
                        ).strip()
                        
                        project = st.text_input(
                            "Project Name / Code*", 
                            value=header_data.get("project", ""),
                            disabled=has_active_batch,
                            placeholder="e.g., Bridge Construction Phase 1"
                        ).strip()
                    
                    with col2:
                        quantity = st.number_input(f"Quantity to Reserve ({unit_name})*", min_value=0.01, value=None, placeholder="0.0")
                        
                        scheduled_date = st.date_input(
                            "Scheduled Delivery Date", 
                            value=header_data.get("scheduled_date", datetime.today()),
                            disabled=has_active_batch
                        )
                        
                        status = st.selectbox(
                            "Initial Status", 
                            ["Pending", "In Transit"],
                            index=0 if header_data.get("status") == "Pending" else (1 if header_data.get("status") == "In Transit" else 0),
                            disabled=has_active_batch
                        )

                    driver_name_initial = st.text_input(
                        "Assigned Driver Name (Optional)", 
                        value=header_data.get("driver_name", ""),
                        disabled=has_active_batch,
                        placeholder="e.g., John Doe"
                    ).strip()
                    
                    is_priority = st.checkbox(
                        "🔥 Mark as High Priority Delivery", 
                        value=header_data.get("is_priority", False),
                        disabled=has_active_batch
                    )
                    
                    item_notes = st.text_input("Item Specific Notes / Instructions", placeholder="e.g., Handle with care, stack 5 layers max")
                    
                    add_to_cart_btn = st.form_submit_button("🛒 Add Item to This Dispatch Order", use_container_width=True)

                    if add_to_cart_btn:
                        req_val = header_data.get("requested_by", requested_by)
                        dest_val = header_data.get("destination", destination)
                        proj_val = header_data.get("project", project)

                        if not req_val or not dest_val or not proj_val or quantity is None:
                            st.error("⚠️ Requested By, Destination, Project, and Quantity are required fields.")
                        elif quantity > stock_available:
                            st.error(f"❌ Cannot reserve stock! Requested Quantity ({quantity} {unit_name}) exceeds Available Stock ({stock_available} {unit_name}).")
                        else:
                            # Set dispatch header info if first item
                            if not has_active_batch:
                                st.session_state.current_dispatch_header = {
                                    "requested_by": requested_by,
                                    "destination": destination,
                                    "project": project,
                                    "scheduled_date": scheduled_date,
                                    "status": status,
                                    "driver_name": driver_name_initial,
                                    "is_priority": is_priority
                                }

                            st.session_state.delivery_cart.append({
                                "item_name": selected_item_name,
                                "unit": unit_name,
                                "quantity": float(quantity),
                                "notes": item_notes.strip()
                            })
                            st.success(f"Added **{selected_item_name}** ({quantity} {unit_name}) to this dispatch batch!")
                            st.rerun()

                # -------------------------------------------------------------
                # STAGING QUEUE & FINAL CONFIRMATION SECTION
                # -------------------------------------------------------------
                if st.session_state.delivery_cart:
                    st.divider()
                    st.markdown(f"### 📋 Dispatch Order Summary ({len(st.session_state.delivery_cart)} items queued)")
                    st.caption("All items below belong to one single dispatch request. Confirm details before finalizing.")

                    cart_df = pd.DataFrame(st.session_state.delivery_cart)
                    
                    # Editable confirmation table
                    edited_cart_df = st.data_editor(
                        cart_df,
                        column_config={
                            "item_name": st.column_config.TextColumn("Item Name", disabled=True),
                            "unit": st.column_config.TextColumn("Unit", disabled=True),
                            "quantity": st.column_config.NumberColumn("Quantity", min_value=0.01, format="%.2f"),
                            "notes": st.column_config.TextColumn("Item Notes")
                        },
                        use_container_width=True,
                        num_rows="dynamic",
                        key="cart_editor"
                    )

                    col_confirm, col_clear = st.columns([3, 1])

                    with col_clear:
                        if st.button("🗑️ Cancel & Reset Batch", use_container_width=True):
                            st.session_state.delivery_cart = []
                            st.session_state.current_dispatch_header = None
                            st.rerun()

                    with col_confirm:
                        if st.button("📅 Confirm & Schedule Dispatch Batch", type="primary", use_container_width=True):
                            try:
                                updated_cart = edited_cart_df.to_dict("records")
                                if not updated_cart:
                                    st.warning("⚠️ No items remaining in the dispatch queue.")
                                else:
                                    # Generate unique dispatch ID for this batch
                                    dispatch_code = f"DISP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
                                    h = st.session_state.current_dispatch_header

                                    with get_db() as conn_add:
                                        cursor = conn_add.cursor()
                                        
                                        for row in updated_cart:
                                            # 1. Insert Delivery Schedule
                                            cursor.execute("""
                                                INSERT INTO deliveries (
                                                    dispatch_id, item_name, supplier, requested_by, destination, project, 
                                                    expected_quantity, unit, expected_date, status, notes, is_priority, driver_name
                                                )
                                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                            """, (
                                                dispatch_code, row["item_name"], h["destination"], h["requested_by"], 
                                                h["destination"], h["project"], row["quantity"], 
                                                row["unit"], str(h["scheduled_date"]), h["status"], 
                                                row["notes"], 1 if h["is_priority"] else 0, h["driver_name"]
                                            ))

                                            # 2. Reserve inventory on master catalog
                                            cursor.execute("""
                                                UPDATE master_items
                                                SET reserved_stock = COALESCE(reserved_stock, 0) + ?
                                                WHERE item_name = ?
                                            """, (row["quantity"], row["item_name"]))

                                        conn_add.commit()

                                    st.session_state.delivery_cart = []
                                    st.session_state.current_dispatch_header = None
                                    st.success(f"✅ Dispatch **{dispatch_code}** successfully scheduled with {len(updated_cart)} item(s) and inventory reserved!")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Failed to submit dispatch batch: {e}")
            else:
                st.warning("⚠️ No master items found. Please add items to the Master Catalog first.")

        except Exception as e:
            st.error(f"Error fetching catalog items: {e}")
