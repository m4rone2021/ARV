import sqlite3
from datetime import date, datetime
import pandas as pd
import streamlit as st
from database import backup_db_to_gdrive, get_db


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
        scheduled_date = first_row.get("scheduled_date") or first_row.get("expected_date")
        destination = first_row.get("destination") or ""
        requested_by = first_row.get("requested_by") or ""
        project = first_row.get("project") or ""
        status = first_row.get("status") or "Pending"
        is_priority = first_row.get("is_priority", 0)
        driver_name = first_row.get("driver_name") or ""

        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO deliveries (
                    dispatch_id, item_name, unit, expected_quantity,
                    expected_date, destination, requested_by,
                    project, status, is_priority, driver_name, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    dispatch_id,
                    item_name,
                    unit,
                    quantity,
                    scheduled_date,
                    destination,
                    requested_by,
                    project,
                    status,
                    is_priority,
                    driver_name,
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


def update_dispatch_status(dispatch_id, new_status, driver_name=None, delivery_notes=None):
    """Updates status for all items in a dispatch batch and handles inventory stock deduct on completion."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            if new_status == "Completed":
                # Deduct stock permanently from current_stock and clear reserved_stock
                cursor.execute(
                    "SELECT item_name, expected_quantity FROM deliveries WHERE dispatch_id = ?",
                    (dispatch_id,),
                )
                items = cursor.fetchall()

                for item_name, qty in items:
                    cursor.execute(
                        """
                        UPDATE master_items
                        SET current_stock = MAX(0, current_stock - ?),
                            reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?)
                        WHERE item_name = ?
                    """,
                        (qty, qty, item_name),
                    )

            elif new_status == "Cancelled":
                # Release reserved stock back to available stock
                cursor.execute(
                    "SELECT item_name, expected_quantity FROM deliveries WHERE dispatch_id = ?",
                    (dispatch_id,),
                )
                items = cursor.fetchall()

                for item_name, qty in items:
                    cursor.execute(
                        """
                        UPDATE master_items
                        SET reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?)
                        WHERE item_name = ?
                    """,
                        (qty, item_name),
                    )

            cursor.execute(
                """
                UPDATE deliveries
                SET status = ?,
                    driver_name = COALESCE(?, driver_name),
                    notes = CASE 
                        WHEN ? IS NOT NULL AND ? != '' THEN ? 
                        ELSE notes 
                    END
                WHERE dispatch_id = ?
            """,
                (new_status, driver_name, delivery_notes, delivery_notes, delivery_notes, dispatch_id),
            )

            conn.commit()

        backup_db_to_gdrive()
        st.toast(f"Dispatch {dispatch_id} marked as {new_status}!", icon="🚚")
        st.rerun()
    except Exception as e:
        st.error(f"Error updating status: {e}")


def update_dispatch_schedule_date(dispatch_id, new_date):
    """Reschedules the delivery date for the entire dispatch order."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE deliveries SET expected_date = ? WHERE dispatch_id = ?",
                (str(new_date), dispatch_id),
            )
            conn.commit()

        backup_db_to_gdrive()
        st.toast(f"Dispatch {dispatch_id} rescheduled to {new_date}", icon="📅")
        st.rerun()
    except Exception as e:
        st.error(f"Error updating schedule date: {e}")


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


def remove_item_from_dispatch(dispatch_id, item_name, qty):
    """Removes a single item from a dispatch order and releases its reserved stock."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM deliveries WHERE dispatch_id = ? AND item_name = ?",
                (dispatch_id, item_name),
            )
            cursor.execute(
                """
                UPDATE master_items
                SET reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?)
                WHERE item_name = ?
            """,
                (qty, item_name),
            )
            conn.commit()

        backup_db_to_gdrive()
        st.toast(f"Removed {item_name} from dispatch batch.", icon="🗑️")
        st.rerun()
    except Exception as e:
        st.error(f"Error removing item: {e}")


def render_dispatch_card(
    dispatch_id, items_df, get_due_status_label_fn, add_item_to_dispatch_fn
):
    """Renders a single unified dispatch card with status updating, date rescheduling,
    notes, and item quantity editing inside a single expandable container.
    """

    def fetch_latest_items_df(d_id):
        with get_db() as conn_fetch:
            return pd.read_sql_query(
                """
                SELECT id, dispatch_id, item_name, unit, 
                       expected_quantity AS quantity, notes, status,
                       destination, expected_date AS scheduled_date, requested_by, project,
                       is_priority, driver_name, created_at
                FROM deliveries 
                WHERE dispatch_id = ?
            """,
                conn_fetch,
                params=(d_id,),
            )

    current_items_df = (
        fetch_latest_items_df(dispatch_id)
        if items_df is None or items_df.empty
        else items_df.copy()
    )

    if current_items_df.empty:
        st.warning(f"No records found for Dispatch #{dispatch_id}")
        return

    first_row = current_items_df.iloc[0]

    prio_badge = "🔥 HIGH PRIORITY | " if first_row["is_priority"] == 1 else ""
    req_info = (
        f"Requested by: {first_row['requested_by']}"
        if first_row["requested_by"]
        else "Requested by: N/A"
    )
    project_info = (
        f" | Project: {first_row['project']}" if first_row["project"] else ""
    )

    due_status = get_due_status_label_fn(first_row["scheduled_date"])
    header_label = f"{prio_badge}🚛 Dispatch #{dispatch_id} | {req_info}{project_info} ➔ {first_row['destination']} [{first_row['status']}] ({due_status})"

    key_prefix = f"disp_{dispatch_id}"

    with st.expander(header_label, expanded=False):
        # ---------------------------------------------------------
        # 1. DISPATCH DETAILS HEADER
        # ---------------------------------------------------------
        c1, c2, c3, c4 = st.columns(4)

        requested_date_val = first_row.get(
            "created_at", first_row.get("requested_date", "N/A")
        )

        c1.markdown(f"**Dispatch ID:** `{dispatch_id}`")
        c1.markdown(f"**Requested By:** {first_row['requested_by'] or 'N/A'}")
        c1.markdown(f"**Destination:** {first_row['destination']}")

        c2.markdown(f"**Project:** {first_row['project'] or 'N/A'}")
        c2.markdown(f"**Total Items:** `{len(current_items_df)}`")

        c3.markdown(f"**Requested Date:** `{requested_date_val}`")
        c3.markdown(f"**Scheduled Date:** `{first_row['scheduled_date']}`")

        c4.markdown(f"**Priority:** {'🔴 **HIGH**' if first_row['is_priority'] == 1 else '🟢 Normal'}")
        c4.markdown(f"**Status:** `{first_row['status']}`")

        if first_row["driver_name"]:
            st.markdown(f"🚛 **Assigned Driver:** {first_row['driver_name']}")

        st.divider()

        # ---------------------------------------------------------
        # 2. STATUS, RESCHEDULE & DRIVER CONTROLS
        # ---------------------------------------------------------
        st.markdown("##### ⚙️ Dispatch Management & Reschedule")
        ctl_col1, ctl_col2, ctl_col3 = st.columns(3)

        with ctl_col1:
            status_options = ["Pending", "In Transit", "Completed", "Cancelled"]
            current_status = first_row["status"]
            selected_status = st.selectbox(
                "Update Dispatch Status",
                options=status_options,
                index=status_options.index(current_status) if current_status in status_options else 0,
                key=f"status_sel_{key_prefix}",
            )

        with ctl_col2:
            try:
                curr_date = datetime.strptime(
                    str(first_row["scheduled_date"]).split()[0], "%Y-%m-%d"
                ).date()
            except Exception:
                curr_date = date.today()

            new_scheduled_date = st.date_input(
                "Reschedule Delivery Date",
                value=curr_date,
                key=f"date_input_{key_prefix}",
            )

        with ctl_col3:
            input_driver = st.text_input(
                "Assigned Driver Name",
                value=first_row["driver_name"] or "",
                placeholder="e.g., John Smith",
                key=f"driver_input_{key_prefix}",
            )

        input_notes = st.text_input(
            "General / Dispatch Delivery Notes",
            value=first_row["notes"] or "",
            placeholder="Add special instructions or dispatch notes...",
            key=f"notes_input_{key_prefix}",
        )

        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button("🔄 Update Status & Driver Notes", key=f"btn_status_{key_prefix}", type="primary", use_container_width=True):
                update_dispatch_status(
                    dispatch_id, selected_status, input_driver, input_notes
                )

        with btn_c2:
            if str(new_scheduled_date) != str(curr_date):
                if st.button("📅 Save Rescheduled Date", key=f"btn_date_{key_prefix}", use_container_width=True):
                    update_dispatch_schedule_date(dispatch_id, new_scheduled_date)

        st.divider()

        # ---------------------------------------------------------
        # 3. MODIFY BATCH ITEMS & QUANTITIES
        # ---------------------------------------------------------
        items_in_batch = current_items_df["item_name"].unique().tolist()
        if items_in_batch:
            st.markdown("##### ➕ Modify Batch Item Quantities")
            mod_col1, mod_col2 = st.columns(2)
            with mod_col1:
                target_item = st.selectbox(
                    "Select Batch Item", options=items_in_batch, key=f"sel_item_{key_prefix}"
                )
                action_type = st.radio(
                    "Action", ["Increase Batch", "Decrease Batch"], key=f"act_item_{key_prefix}"
                )
            with mod_col2:
                change_q = st.number_input(
                    "Quantity Change", min_value=0.01, value=1.0, step=1.0, key=f"qty_item_{key_prefix}"
                )
                mod_notes = st.text_input(
                    "Item Notes", placeholder="Optional item notes...", key=f"item_notes_{key_prefix}"
                )

            if st.button("💾 Apply Quantity Adjustment", key=f"btn_qty_{key_prefix}"):
                update_dispatch_item_quantity(
                    dispatch_id, target_item, action_type, change_q, mod_notes
                )

        st.divider()

        # ---------------------------------------------------------
        # 4. CURRENT BATCH TABLE & ITEM REMOVAL
        # ---------------------------------------------------------
        st.markdown("##### 📦 Current Batch Items To Be Dispatched")
        
        for idx, row in current_items_df.iterrows():
            item_col1, item_col2, item_col3, item_col4 = st.columns([3, 2, 3, 1])
            item_col1.markdown(f"**{row['item_name']}**")
            item_col2.markdown(f"`{row['quantity']:.2f} {row['unit']}`")
            item_col3.markdown(f"_{row['notes'] or 'No notes'}_")
            
            if item_col4.button("🗑️", key=f"del_{dispatch_id}_{row['item_name']}"):
                remove_item_from_dispatch(dispatch_id, row['item_name'], row['quantity'])
