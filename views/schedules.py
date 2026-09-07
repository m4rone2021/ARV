import sqlite3
import uuid
from datetime import datetime, date
import pandas as pd
import streamlit as st
from database import get_db, init_db, backup_db_to_gdrive


def ensure_schedule_columns():
    """Ensure Stock Out fields exist on the deliveries table within a single connection."""
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
                "driver_name": "TEXT",
            }

            for col_name, col_type in new_cols.items():
                if col_name not in existing_cols:
                    cursor.execute(
                        f"ALTER TABLE deliveries ADD COLUMN {col_name} {col_type}"
                    )

            conn.commit()
    except Exception as e:
        st.error(f"Error initializing delivery schema: {e}")


def get_due_status_label(scheduled_date_str):
    """Calculate remaining days, today status, or overdue status."""
    if not scheduled_date_str:
        return "No Date Set"

    try:
        if isinstance(scheduled_date_str, (datetime, date)):
            target_date = (
                scheduled_date_str.date()
                if isinstance(scheduled_date_str, datetime)
                else scheduled_date_str
            )
        else:
            target_date = datetime.strptime(
                str(scheduled_date_str).split()[0], "%Y-%m-%d"
            ).date()

        today = date.today()
        days_left = (target_date - today).days

        if days_left == 0:
            return "📅 Due Today"
        elif days_left < 0:
            return f"⚠️ Overdue ({abs(days_left)} days)"
        else:
            return f"⏳ In {days_left} days"
    except Exception:
        return f"📅 {scheduled_date_str}"


def add_item_to_dispatch(
    dispatch_id, item_name, unit, quantity, notes, first_row
):
    """Helper function to insert a new item into an existing dispatch batch and reserve stock."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO deliveries (
                    dispatch_id, item_name, unit, expected_quantity,
                    expected_date, supplier, destination, requested_by,
                    project, status, is_priority, driver_name, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    dispatch_id,
                    item_name,
                    unit,
                    quantity,
                    first_row["scheduled_date"],
                    first_row["destination"],
                    first_row["destination"],
                    first_row["requested_by"],
                    first_row["project"],
                    first_row["status"],
                    first_row["is_priority"],
                    first_row["driver_name"],
                    notes,
                ),
            )

            # Update reserved stock in master inventory
            cursor.execute(
                """
                UPDATE master_items
                SET reserved_stock = COALESCE(reserved_stock, 0) + ?
                WHERE item_name = ?
            """,
                (quantity, item_name),
            )
            conn.commit()

        backup_db_to_gdrive()
        st.toast(f"Added {item_name} to dispatch batch!", icon="✅")
        st.rerun()
    except Exception as e:
        st.error(f"Error adding item to dispatch: {e}")


def render_dispatch_card(dispatch_id, items_df):
    """Render a single dispatch card with status updates, date adjustments, item editing, and batch management."""
    first_row = items_df.iloc[0]

    prio_badge = (
        "🔥 HIGH PRIORITY | " if first_row["is_priority"] == 1 else ""
    )
    req_info = (
        f"Requested by: {first_row['requested_by']}"
        if first_row["requested_by"]
        else "Requested by: N/A"
    )
    project_info = (
        f" | Project: {first_row['project']}"
        if first_row["project"]
        else ""
    )

    due_status = get_due_status_label(first_row["scheduled_date"])
    header_label = f"{prio_badge}🚛 {req_info}{project_info} ➔ {first_row['destination']} [{first_row['status']}] ({due_status})"

    with st.expander(header_label):
        c1, c2, c3, c4 = st.columns(4)

        requested_date_val = first_row.get(
            "created_at", first_row.get("requested_date", "N/A")
        )

        c1.markdown(
            f"**Requested By:** {first_row['requested_by'] if first_row['requested_by'] else 'N/A'}"
        )
        c1.markdown(f"**Destination:** {first_row['destination']}")

        c2.markdown(
            f"**Project:** {first_row['project'] if first_row['project'] else 'N/A'}"
        )
        c2.markdown(
            f"**Total Items in Dispatch:** `{len(items_df)}`"
        )

        c3.markdown(f"**Requested Date:** `{requested_date_val}`")
        c3.markdown(
            f"**Scheduled Date:** `{first_row['scheduled_date']}`"
        )

        c4.markdown(
            f"**Priority:** {'🔴 **HIGH**' if first_row['is_priority'] == 1 else '🟢 Normal'}"
        )
        c4.markdown(f"**Status:** `{first_row['status']}`")

        if first_row["driver_name"]:
            st.markdown(
                f"🚛 **Driver Name:** {first_row['driver_name']}"
            )

        st.divider()

        # -------------------------------------------------------------
        # EDIT DISPATCH SCHEDULE & ITEMS SECTION
        # -------------------------------------------------------------
        st.markdown("##### ✏️ Edit Dispatch Schedule & Batch Items")

        # 1. Update Scheduled Delivery Date
        current_date = datetime.strptime(
            str(first_row["scheduled_date"]).split()[0], "%Y-%m-%d"
        ).date()
        new_sched_date = st.date_input(
            "Reschedule Delivery Date",
            value=current_date,
            key=f"resched_date_{dispatch_id}",
        )

        if new_sched_date != current_date:
            if st.button(
                "📅 Save New Delivery Date",
                key=f"btn_resched_{dispatch_id}",
            ):
                try:
                    with get_db() as conn_date:
                        cursor = conn_date.cursor()
                        cursor.execute(
                            "UPDATE deliveries SET expected_date = ? WHERE dispatch_id = ? OR id IN ({})".format(
                                ",".join(str(i) for i in items_df["id"])
                            ),
                            (str(new_sched_date), dispatch_id),
                        )
                        conn_date.commit()

                    backup_db_to_gdrive()
                    st.toast(
                        "Scheduled date updated successfully!", icon="📅"
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to update date: {e}")

        st.divider()

        # 2. Editable Items Table (Quantities & Notes) + Item Deletion
        st.markdown(
            "###### 📦 Items in Batch (Edit Quantities / Notes):"
        )

        editable_df = items_df[
            ["id", "item_name", "quantity", "unit", "notes"]
        ].copy()

        edited_data = st.data_editor(
            editable_df,
            column_config={
                "id": None,  # Hide ID column
                "item_name": st.column_config.TextColumn(
                    "Item Name", disabled=True
                ),
                "unit": st.column_config.TextColumn(
                    "Unit", disabled=True
                ),
                "quantity": st.column_config.NumberColumn(
                    "Quantity", min_value=0.01, format="%.2f"
                ),
                "notes": st.column_config.TextColumn(
                    "Notes / Instructions"
                ),
            },
            use_container_width=True,
            hide_index=True,
            key=f"editor_{dispatch_id}",
        )

        col_save_items, col_del_item = st.columns([2, 1])

        with col_save_items:
            if st.button(
                "💾 Save Item Changes",
                key=f"btn_save_items_{dispatch_id}",
                use_container_width=True,
            ):
                try:
                    with get_db() as conn_edit:
                        cursor = conn_edit.cursor()
                        for _, edited_row in edited_data.iterrows():
                            item_id = edited_row["id"]
                            new_qty = float(edited_row["quantity"])
                            new_note = (
                                str(edited_row["notes"])
                                if edited_row["notes"]
                                else ""
                            )

                            # Find original quantity to calculate inventory difference
                            orig_row = items_df[
                                items_df["id"] == item_id
                            ].iloc[0]
                            old_qty = float(orig_row["quantity"])
                            qty_diff = new_qty - old_qty

                            # Update delivery record
                            cursor.execute(
                                "UPDATE deliveries SET expected_quantity = ?, notes = ? WHERE id = ?",
                                (new_qty, new_note, item_id),
                            )

                            # Adjust stock reservation if still Pending/In Transit
                            if (
                                first_row["status"]
                                in ["Pending", "In Transit"]
                                and qty_diff != 0
                            ):
                                cursor.execute(
                                    """
                                    UPDATE master_items 
                                    SET reserved_stock = COALESCE(reserved_stock, 0) + ? 
                                    WHERE item_name = ?
                                """,
                                    (
                                        qty_diff,
                                        orig_row["item_name"],
                                    ),
                                )

                        conn_edit.commit()

                    backup_db_to_gdrive()
                    st.toast(
                        "Item details and inventory reservations updated!",
                        icon="✅",
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Error updating item details: {e}")

        with col_del_item:
            # Dropdown to pick an item to remove from the dispatch
            item_to_remove = st.selectbox(
                "Remove Item",
                options=items_df["id"].tolist(),
                format_func=lambda x: items_df[items_df["id"] == x][
                    "item_name"
                ].values[0],
                key=f"select_remove_{dispatch_id}",
            )
            if st.button(
                "🗑️ Remove Selected Item",
                key=f"btn_remove_{dispatch_id}",
                use_container_width=True,
            ):
                if len(items_df) <= 1:
                    st.error(
                        "Cannot remove the only item in a dispatch batch. Cancel the dispatch instead."
                    )
                else:
                    try:
                        rem_row = items_df[
                            items_df["id"] == item_to_remove
                        ].iloc[0]
                        rem_qty = float(rem_row["quantity"])
                        rem_name = rem_row["item_name"]

                        with get_db() as conn_rem:
                            cursor = conn_rem.cursor()
                            cursor.execute(
                                "DELETE FROM deliveries WHERE id = ?",
                                (item_to_remove,),
                            )

                            if first_row["status"] in [
                                "Pending",
                                "In Transit",
                            ]:
                                cursor.execute(
                                    """
                                    UPDATE master_items 
                                    SET reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?) 
                                    WHERE item_name = ?
                                """,
                                    (rem_qty, rem_name),
                                )
                            conn_rem.commit()

                        backup_db_to_gdrive()
                        st.toast(
                            f"Removed {rem_name} from dispatch batch.",
                            icon="🗑️",
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error removing item: {e}")

        st.divider()

        # 3. Add a New Item to this Existing Dispatch Batch
        with st.expander("➕ Add Another Item to this Dispatch Batch"):
            try:
                with get_db() as conn_m:
                    df_master = pd.read_sql_query(
                        """
                        SELECT item_name, unit, current_stock, 
                               COALESCE(reserved_stock, 0) AS reserved_stock,
                               (current_stock - COALESCE(reserved_stock, 0)) AS available_stock
                        FROM master_items ORDER BY item_name ASC
                    """,
                        conn_m,
                    )

                if not df_master.empty:
                    add_item_selected = st.selectbox(
                        "Select Item to Add",
                        df_master["item_name"].tolist(),
                        key=f"add_item_sel_{dispatch_id}",
                    )
                    add_item_info = df_master[
                        df_master["item_name"] == add_item_selected
                    ].iloc[0]
                    avail_qty = float(
                        add_item_info["available_stock"]
                    )

                    st.caption(
                        f"Available Stock for **{add_item_selected}**: `{avail_qty:,.2f} {add_item_info['unit']}`"
                    )

                    col_add_q, col_add_n = st.columns([1, 2])
                    with col_add_q:
                        add_qty = st.number_input(
                            f"Quantity ({add_item_info['unit']})",
                            min_value=0.01,
                            value=1.0,
                            key=f"add_qty_{dispatch_id}",
                        )
                    with col_add_n:
                        add_notes = st.text_input(
                            "Item Notes",
                            placeholder="Optional instructions...",
                            key=f"add_notes_in_{dispatch_id}",
                        )

                    if st.button(
                        "➕ Append Item to Batch",
                        key=f"btn_append_item_{dispatch_id}",
                    ):
                        if add_qty > avail_qty:
                            st.error(
                                f"Quantity exceeds available stock ({avail_qty})."
                            )
                        else:
                            add_item_to_dispatch(
                                dispatch_id,
                                add_item_selected,
                                add_item_info["unit"],
                                add_qty,
                                add_notes,
                                first_row,
                            )
            except Exception as e:
                st.error(f"Error loading master items: {e}")

        st.divider()

        # -------------------------------------------------------------
        # STATUS UPDATE SECTION
        # -------------------------------------------------------------
        status_options = [
            "Pending",
            "In Transit",
            "Completed",
            "Cancelled",
        ]
        current_idx = (
            status_options.index(first_row["status"])
            if first_row["status"] in status_options
            else 0
        )

        new_status = st.selectbox(
            "Update Status for ENTIRE Dispatch Batch",
            status_options,
            index=current_idx,
            key=f"status_select_{dispatch_id}",
        )

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
                    key=f"driver_input_{dispatch_id}",
                ).strip()
            with col_notes:
                add_notes_input = st.text_input(
                    "Additional Completion Notes",
                    placeholder="e.g., Received by site supervisor; gate pass #1024",
                    key=f"add_notes_{dispatch_id}",
                ).strip()

        if new_status != first_row["status"] or (
            new_status == "Completed"
            and driver_input != first_row["driver_name"]
        ):
            if st.button(
                "Save Batch Status Changes",
                key=f"btn_status_{dispatch_id}",
                use_container_width=True,
            ):
                if new_status == "Completed" and not driver_input:
                    st.error(
                        "⚠️ Please specify the Driver Name before marking the dispatch as Completed."
                    )
                else:
                    try:
                        with get_db() as conn_update:
                            cursor = conn_update.cursor()
                            old_status = first_row["status"]

                            for _, item_row in items_df.iterrows():
                                qty = float(item_row["quantity"])
                                item_name = item_row["item_name"]
                                item_id = item_row["id"]

                                existing_notes = (
                                    str(item_row["notes"]).strip()
                                    if item_row["notes"]
                                    else ""
                                )
                                final_notes = (
                                    f"{existing_notes} [Completed Note: {add_notes_input}]".strip()
                                    if add_notes_input
                                    else existing_notes
                                )

                                cursor.execute(
                                    """
                                    UPDATE deliveries 
                                    SET status = ?, driver_name = ?, notes = ? 
                                    WHERE id = ?
                                """,
                                    (
                                        new_status,
                                        driver_input,
                                        final_notes,
                                        item_id,
                                    ),
                                )

                                if old_status in [
                                    "Pending",
                                    "In Transit",
                                ]:
                                    if new_status == "Completed":
                                        cursor.execute(
                                            """
                                            UPDATE master_items 
                                            SET current_stock = current_stock - ?,
                                                reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?)
                                            WHERE item_name = ?
                                        """,
                                            (qty, qty, item_name),
                                        )

                                    elif new_status == "Cancelled":
                                        cursor.execute(
                                            """
                                            UPDATE master_items 
                                            SET reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?)
                                            WHERE item_name = ?
                                        """,
                                            (qty, item_name),
                                        )

                            conn_update.commit()

                        backup_db_to_gdrive()

                        st.toast(
                            f"Dispatch status updated to {new_status} and synced to Google Drive!",
                            icon="✅",
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(
                            f"Error updating dispatch status: {e}"
                        )


def render_schedules(user_name, user_role):
    st.title("🚚 Stock Out Delivery Schedules")
    st.caption(
        "Schedule outbound material dispatches, reserve shop stock, and track project deliveries."
    )

    init_db()
    ensure_schedule_columns()

    if "delivery_cart" not in st.session_state:
        st.session_state.delivery_cart = []

    if "current_dispatch_header" not in st.session_state:
        st.session_state.current_dispatch_header = None

    tab_overview, tab_add = st.tabs(
        [
            "📅 Dispatch Overview",
            "➕ Schedule Stock Out Delivery",
        ]
    )

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
                col_status, col_prio, col_search = st.columns(
                    [1, 1, 2]
                )
                with col_status:
                    status_filter = st.selectbox(
                        "Filter Status",
                        [
                            "All",
                            "Pending",
                            "In Transit",
                            "Completed",
                            "Cancelled",
                        ],
                    )
                with col_prio:
                    prio_filter = st.selectbox(
                        "Priority Filter",
                        [
                            "All",
                            "High Priority Only",
                            "Normal Only",
                        ],
                    )
                with col_search:
                    search_query = st.text_input(
                        "🔍 Search Item / Requester / Destination / Driver",
                        placeholder="e.g., DISP-1002, Cement, Main Site...",
                    )

                filtered_df = df.copy()
                if status_filter != "All":
                    filtered_df = filtered_df[
                        filtered_df["status"] == status_filter
                    ]

                if prio_filter == "High Priority Only":
                    filtered_df = filtered_df[
                        filtered_df["is_priority"] == 1
                    ]
                elif prio_filter == "Normal Only":
                    filtered_df = filtered_df[
                        filtered_df["is_priority"] == 0
                    ]

                if search_query.strip():
                    q = search_query.strip().lower()
                    filtered_df = filtered_df[
                        filtered_df["dispatch_id"]
                        .str.lower()
                        .str.contains(q, na=False)
                        | filtered_df["item_name"]
                        .str.lower()
                        .str.contains(q, na=False)
                        | filtered_df["requested_by"]
                        .str.lower()
                        .str.contains(q, na=False)
                        | filtered_df["destination"]
                        .str.lower()
                        .str.contains(q, na=False)
                        | filtered_df["project"]
                        .str.lower()
                        .str.contains(q, na=False)
                        | filtered_df["driver_name"]
                        .str.lower()
                        .str.contains(q, na=False)
                    ]

                st.divider()

                active_df = filtered_df[
                    filtered_df["status"].isin(["Pending", "In Transit"])
                ]
                completed_df = filtered_df[
                    filtered_df["status"].isin(
                        ["Completed", "Cancelled"]
                    )
                ]

                col_active, col_completed = st.columns(2)

                with col_active:
                    active_dispatches = active_df.groupby(
                        "dispatch_id", sort=False
                    )
                    st.markdown(
                        f"### 🚚 Active Dispatches ({len(active_dispatches)})"
                    )
                    st.caption("Pending or In Transit Dispatches")
                    st.divider()

                    if not active_df.empty:
                        for disp_id, group in active_dispatches:
                            render_dispatch_card(disp_id, group)
                    else:
                        st.info("No active dispatches found.")

                with col_completed:
                    completed_dispatches = completed_df.groupby(
                        "dispatch_id", sort=False
                    )
                    st.markdown(
                        f"### ✅ Completed & History ({len(completed_dispatches)})"
                    )
                    st.caption("Finished or Cancelled Dispatches")
                    st.divider()

                    if not completed_df.empty:
                        for disp_id, group in completed_dispatches:
                            render_dispatch_card(disp_id, group)
                    else:
                        st.info(
                            "No completed or cancelled dispatches found."
                        )

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
                df_master = pd.read_sql_query(
                    """
                    SELECT item_name, unit, current_stock, 
                           COALESCE(reserved_stock, 0) AS reserved_stock,
                           (current_stock - COALESCE(reserved_stock, 0)) AS available_stock
                    FROM master_items 
                    ORDER BY item_name ASC
                """,
                    conn_items,
                )

            if not df_master.empty:
                has_active_batch = bool(st.session_state.delivery_cart)
                header_data = (
                    st.session_state.current_dispatch_header or {}
                )

                selected_item_name = st.selectbox(
                    "Select Item to Add to Dispatch*",
                    df_master["item_name"].tolist(),
                )
                item_info = df_master[
                    df_master["item_name"] == selected_item_name
                ].iloc[0]

                stock_in_shop = float(item_info["current_stock"])
                stock_reserved = float(item_info["reserved_stock"])

                staged_qty = sum(
                    item["quantity"]
                    for item in st.session_state.delivery_cart
                    if item["item_name"] == selected_item_name
                )
                stock_available = (
                    float(item_info["available_stock"]) - staged_qty
                )
                unit_name = str(item_info["unit"])

                m1, m2, m3 = st.columns(3)
                m1.metric(
                    "Stock In Shop (Total)",
                    f"{stock_in_shop:,.2f} {unit_name}",
                )
                m2.metric(
                    "Reserved Stock",
                    f"{stock_reserved:,.2f} {unit_name}",
                )
                m3.metric(
                    "Available Stock",
                    f"{stock_available:,.2f} {unit_name}",
                )

                st.divider()

                with st.form(
                    "add_dispatch_item_form", clear_on_submit=True
                ):
                    if has_active_batch:
                        st.info(
                            f"🔒 **Dispatch Order Locked:** Adding additional items to batch for **{header_data.get('requested_by')}** ➡️ **{header_data.get('destination')}** ({header_data.get('project')})"
                        )
                    else:
                        st.markdown("##### 📄 1. Dispatch Order Details")
                        col1, col2 = st.columns(2)
                        with col1:
                            input_requested_by = st.text_input(
                                "Requested By*",
                                placeholder="e.g., Engr. John Doe",
                            )
                            input_destination = st.text_input(
                                "Destination / Site Location*",
                                placeholder="e.g., Block 4 Site",
                            )
                            input_project = st.text_input(
                                "Project Name / Code*",
                                placeholder="e.g., Bridge Construction Phase 1",
                            )

                        with col2:
                            input_scheduled_date = st.date_input(
                                "Scheduled Delivery Date",
                                value=datetime.today(),
                            )
                            input_status = st.selectbox(
                                "Initial Status",
                                ["Pending", "In Transit"],
                            )

                        input_driver = st.text_input(
                            "Assigned Driver Name (Optional)",
                            placeholder="e.g., John Doe",
                        )
                        input_priority = st.checkbox(
                            "🔥 Mark as High Priority Delivery"
                        )
                        st.divider()

                    st.markdown(
                        f"##### 📦 2. Item Entry: {selected_item_name}"
                    )
                    quantity = st.number_input(
                        f"Quantity to Reserve ({unit_name})*",
                        min_value=0.01,
                        value=None,
                        placeholder="0.0",
                    )
                    item_notes = st.text_input(
                        "Item Specific Notes / Instructions",
                        placeholder="e.g., Handle with care",
                    )

                    add_to_cart_btn = st.form_submit_button(
                        "🛒 Add Item to Batch Queue",
                        use_container_width=True,
                    )

                    if add_to_cart_btn:
                        if not has_active_batch:
                            req_val = input_requested_by.strip()
                            dest_val = input_destination.strip()
                            proj_val = input_project.strip()
                            sched_val = input_scheduled_date
                            stat_val = input_status
                            driver_val = input_driver.strip()
                            prio_val = 1 if input_priority else 0
                        else:
                            req_val = header_data.get("requested_by")
                            dest_val = header_data.get("destination")
                            proj_val = header_data.get("project")
                            sched_val = header_data.get("scheduled_date")
                            stat_val = header_data.get("status")
                            driver_val = header_data.get("driver_name")
                            prio_val = header_data.get("is_priority")

                        if (
                            not req_val
                            or not dest_val
                            or not proj_val
                            or quantity is None
                        ):
                            st.error(
                                "⚠️ Requested By, Destination, Project, and Quantity are required fields."
                            )
                        elif quantity > stock_available:
                            st.error(
                                f"❌ Cannot reserve stock! Requested Quantity ({quantity} {unit_name}) exceeds Available Stock ({stock_available} {unit_name})."
                            )
                        else:
                            if not has_active_batch:
                                st.session_state.current_dispatch_header = (
                                    {
                                        "requested_by": req_val,
                                        "destination": dest_val,
                                        "project": proj_val,
                                        "scheduled_date": str(sched_val),
                                        "status": stat_val,
                                        "driver_name": driver_val,
                                        "is_priority": prio_val,
                                    }
                                )

                            st.session_state.delivery_cart.append(
                                {
                                    "item_name": selected_item_name,
                                    "unit": unit_name,
                                    "quantity": float(quantity),
                                    "notes": item_notes.strip(),
                                }
                            )
                            st.toast(
                                f"Added {selected_item_name} to batch queue!"
                            )
                            st.rerun()

                # -------------------------------------------------------------
                # STAGING QUEUE & FINAL CONFIRMATION SECTION
                # -------------------------------------------------------------
                if st.session_state.delivery_cart:
                    st.divider()
                    st.markdown(
                        f"### 📋 Dispatch Order Summary ({len(st.session_state.delivery_cart)} items queued)"
                    )
                    st.caption(
                        "All items below belong to one single dispatch request. Confirm details before finalizing."
                    )

                    cart_df = pd.DataFrame(st.session_state.delivery_cart)

                    edited_cart_df = st.data_editor(
                        cart_df,
                        column_config={
                            "item_name": st.column_config.TextColumn(
                                "Item Name", disabled=True
                            ),
                            "unit": st.column_config.TextColumn(
                                "Unit", disabled=True
                            ),
                            "quantity": st.column_config.NumberColumn(
                                "Quantity", min_value=0.01, format="%.2f"
                            ),
                            "notes": st.column_config.TextColumn(
                                "Item Notes"
                            ),
                        },
                        use_container_width=True,
                        num_rows="dynamic",
                        key="cart_editor",
                    )

                    col_confirm, col_clear = st.columns([3, 1])

                    with col_clear:
                        if st.button(
                            "🗑️ Cancel & Reset Batch",
                            use_container_width=True,
                        ):
                            st.session_state.delivery_cart = []
                            st.session_state.current_dispatch_header = (
                                None
                            )
                            st.rerun()

                    with col_confirm:
                        if st.button(
                            "📅 Confirm & Schedule Dispatch Batch",
                            type="primary",
                            use_container_width=True,
                        ):
                            try:
                                updated_cart = edited_cart_df.to_dict(
                                    "records"
                                )
                                if not updated_cart:
                                    st.warning(
                                        "⚠️ No items remaining in the dispatch queue."
                                    )
                                else:
                                    dispatch_code = f"DISP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
                                    header = st.session_state.current_dispatch_header

                                    with get_db() as conn_save:
                                        cursor = conn_save.cursor()

                                        for row in updated_cart:
                                            item_n = row["item_name"]
                                            unit_n = row["unit"]
                                            qty_val = float(
                                                row["quantity"]
                                            )
                                            note_val = row["notes"]

                                            cursor.execute(
                                                """
                                                INSERT INTO deliveries (
                                                    dispatch_id, item_name, unit, expected_quantity,
                                                    expected_date, supplier, destination, requested_by,
                                                    project, status, is_priority, driver_name, notes
                                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                            """,
                                                (
                                                    dispatch_code,
                                                    item_n,
                                                    unit_n,
                                                    qty_val,
                                                    header[
                                                        "scheduled_date"
                                                    ],
                                                    header["destination"],
                                                    header["destination"],
                                                    header[
                                                        "requested_by"
                                                    ],
                                                    header["project"],
                                                    header["status"],
                                                    header["is_priority"],
                                                    header["driver_name"],
                                                    note_val,
                                                ),
                                            )

                                            cursor.execute(
                                                """
                                                UPDATE master_items
                                                SET reserved_stock = COALESCE(reserved_stock, 0) + ?
                                                WHERE item_name = ?
                                            """,
                                                (qty_val, item_n),
                                            )

                                        conn_save.commit()

                                    backup_db_to_gdrive()

                                    st.session_state.delivery_cart = []
                                    st.session_state.current_dispatch_header = (
                                        None
                                    )

                                    st.toast(
                                        f"Batch {dispatch_code} scheduled successfully!",
                                        icon="🎉",
                                    )
                                    st.rerun()

                            except Exception as e:
                                st.error(
                                    f"Failed to process dispatch batch: {e}"
                                )

            else:
                st.warning("No master inventory items available.")
        except Exception as e:
            st.error(f"Error loading inventory items: {e}")
