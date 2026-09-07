import sqlite3
import uuid
from datetime import datetime, date
import pandas as pd
import streamlit as st
from database import get_db, init_db, backup_db_to_gdrive
from components.dispatch_card import render_dispatch_card


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


def update_dispatch_item_quantity(dispatch_id, item_name, action, change_qty, notes):
    """Updates batch item quantity, keeps reserved_stock synced, and refreshes UI."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT expected_quantity FROM deliveries WHERE dispatch_id = ? AND item_name = ?",
                (dispatch_id, item_name),
            )
            row = cursor.fetchone()

            if not row:
                st.error("Selected item not found in dispatch batch.")
                return

            current_qty = float(row[0])

            if action == "Increase Batch":
                qty_delta = change_qty
                new_qty = current_qty + change_qty
            else:
                qty_delta = -min(current_qty, change_qty)
                new_qty = max(0.0, current_qty - change_qty)

            if new_qty == 0:
                cursor.execute(
                    "DELETE FROM deliveries WHERE dispatch_id = ? AND item_name = ?",
                    (dispatch_id, item_name),
                )
            else:
                cursor.execute(
                    """
                    UPDATE deliveries 
                    SET expected_quantity = ?, notes = COALESCE(?, notes)
                    WHERE dispatch_id = ? AND item_name = ?
                    """,
                    (new_qty, notes.strip() if notes else None, dispatch_id, item_name),
                )

            # Adjust reserved stock in master inventory
            cursor.execute(
                """
                UPDATE master_items
                SET reserved_stock = MAX(0, COALESCE(reserved_stock, 0) + ?)
                WHERE item_name = ?
                """,
                (qty_delta, item_name),
            )
            conn.commit()

        backup_db_to_gdrive()
        st.toast(f"Updated {item_name} batch quantity to {new_qty:.2f}", icon="✅")
        st.rerun()
    except Exception as e:
        st.error(f"Error modifying dispatch item: {e}")


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
                col_status, col_prio, col_search = st.columns([1, 1, 2])
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
                            render_dispatch_card(
                                disp_id,
                                group,
                                get_due_status_label,
                                add_item_to_dispatch,
                            )
                            
                            # Integrated Batch Items Editor & Direct Review Table
                            with st.expander(f"✏️ Edit & Review Batch Details ({disp_id})", expanded=False):
                                items_in_batch = group["item_name"].unique().tolist()
                                if items_in_batch:
                                    st.markdown("##### ➕ Add Item or Modify Batch Quantities")
                                    mod_col1, mod_col2 = st.columns(2)
                                    with mod_col1:
                                        target_item = st.selectbox(
                                            "Select Batch Item", options=items_in_batch, key=f"sel_{disp_id}"
                                        )
                                        action_type = st.radio(
                                            "Action", ["Increase Batch", "Decrease Batch"], key=f"act_{disp_id}"
                                        )
                                    with mod_col2:
                                        change_q = st.number_input(
                                            "Quantity Change", min_value=0.01, value=1.0, step=1.0, key=f"qty_{disp_id}"
                                        )
                                        mod_notes = st.text_input(
                                            "Update Notes", placeholder="Optional batch notes...", key=f"notes_{disp_id}"
                                        )

                                    if st.button("💾 Apply Changes to Batch Item", key=f"btn_{disp_id}", type="primary"):
                                        update_dispatch_item_quantity(
                                            disp_id, target_item, action_type, change_q, mod_notes
                                        )

                                st.markdown("##### 📦 Current Batch Items To Be Dispatched")
                                review_df = group[["item_name", "quantity", "unit", "notes"]].rename(
                                    columns={
                                        "item_name": "Item Name",
                                        "quantity": "Total Quantity To Dispatch",
                                        "unit": "Unit",
                                        "notes": "Notes / Instructions",
                                    }
                                )
                                st.dataframe(review_df, use_container_width=True)

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
                            render_dispatch_card(
                                disp_id,
                                group,
                                get_due_status_label,
                                add_item_to_dispatch,
                            )
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
                                placeholder="e.g., PRJ-2026-A",
                            )

                        with col2:
                            input_scheduled_date = st.date_input(
                                "Scheduled Delivery Date*",
                                value=date.today(),
                            )
                            input_is_priority = st.checkbox(
                                "🔥 Mark as High Priority Dispatch"
                            )

                    st.markdown("##### 📦 2. Item Details")
                    col_q, col_n = st.columns([1, 2])
                    with col_q:
                        input_quantity = st.number_input(
                            f"Dispatch Quantity ({unit_name})*",
                            min_value=0.01,
                            value=1.0,
                            step=1.0,
                        )
                    with col_n:
                        input_notes = st.text_input(
                            "Item Notes / Handling Instructions",
                            placeholder="Optional site notes, batch specs...",
                        )

                    btn_add_to_cart = st.form_submit_button(
                        "➕ Add Item to Dispatch Batch", type="primary"
                    )

                if btn_add_to_cart:
                    if input_quantity > stock_available:
                        st.error(
                            f"Cannot stage {input_quantity:.2f} {unit_name}. Only {stock_available:.2f} {unit_name} is available."
                        )
                    else:
                        if not has_active_batch:
                            if not input_requested_by.strip() or not input_destination.strip():
                                st.error(
                                    "Please fill in all required fields marked with *."
                                )
                                st.stop()

                            st.session_state.current_dispatch_header = {
                                "dispatch_id": f"DISP-{uuid.uuid4().hex[:6].upper()}",
                                "requested_by": input_requested_by.strip(),
                                "destination": input_destination.strip(),
                                "project": input_project.strip() or "N/A",
                                "scheduled_date": str(input_scheduled_date),
                                "is_priority": 1 if input_is_priority else 0,
                            }

                        st.session_state.delivery_cart.append(
                            {
                                "item_name": selected_item_name,
                                "unit": unit_name,
                                "quantity": input_quantity,
                                "notes": input_notes.strip(),
                            }
                        )
                        st.toast(
                            f"Added {selected_item_name} to staging batch!",
                            icon="🛒",
                        )
                        st.rerun()

                # Staging area display & save block
                if st.session_state.delivery_cart:
                    st.divider()
                    st.markdown("### 🛒 Staged Dispatch Batch")

                    hdr = st.session_state.current_dispatch_header
                    st.caption(
                        f"**Batch ID:** `{hdr['dispatch_id']}` | **Requester:** {hdr['requested_by']} | **Destination:** {hdr['destination']} | **Date:** {hdr['scheduled_date']}"
                    )

                    cart_df = pd.DataFrame(st.session_state.delivery_cart)
                    st.dataframe(cart_df, use_container_width=True)

                    btn_col1, btn_col2 = st.columns([2, 1])

                    with btn_col1:
                        if st.button(
                            "💾 Confirm & Create Dispatch Order",
                            type="primary",
                            use_container_width=True,
                        ):
                            try:
                                with get_db() as conn_save:
                                    cursor = conn_save.cursor()
                                    for item in st.session_state.delivery_cart:
                                        cursor.execute(
                                            """
                                            INSERT INTO deliveries (
                                                dispatch_id, item_name, unit, expected_quantity,
                                                expected_date, supplier, destination, requested_by,
                                                project, status, is_priority, notes
                                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?)
                                        """,
                                            (
                                                hdr["dispatch_id"],
                                                item["item_name"],
                                                item["unit"],
                                                item["quantity"],
                                                hdr["scheduled_date"],
                                                hdr["destination"],
                                                hdr["destination"],
                                                hdr["requested_by"],
                                                hdr["project"],
                                                hdr["is_priority"],
                                                item["notes"],
                                            ),
                                        )

                                        cursor.execute(
                                            """
                                            UPDATE master_items 
                                            SET reserved_stock = COALESCE(reserved_stock, 0) + ? 
                                            WHERE item_name = ?
                                        """,
                                            (
                                                item["quantity"],
                                                item["item_name"],
                                            ),
                                        )

                                    conn_save.commit()

                                backup_db_to_gdrive()
                                st.session_state.delivery_cart = []
                                st.session_state.current_dispatch_header = (
                                    None
                                )
                                st.success(
                                    f"Successfully created dispatch order `{hdr['dispatch_id']}`!"
                                )
                                st.rerun()

                            except Exception as e:
                                st.error(f"Error creating dispatch order: {e}")

                    with btn_col2:
                        if st.button(
                            "🗑️ Clear Batch Staging",
                            use_container_width=True,
                        ):
                            st.session_state.delivery_cart = []
                            st.session_state.current_dispatch_header = None
                            st.rerun()

            else:
                st.info(
                    "No items available in Master Inventory to schedule dispatches."
                )
        except Exception as e:
            st.error(f"Error loading master items form: {e}")
