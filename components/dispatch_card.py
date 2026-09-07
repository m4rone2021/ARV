import pandas as pd
import streamlit as st
from datetime import datetime

from database import get_db, backup_db_to_gdrive


def render_dispatch_card(
    dispatch_id, items_df, get_due_status_label_fn, add_item_to_dispatch_fn
):
    """
    Renders a single dispatch card with isolated batch adjustments and state-safe editing.
    """
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

    due_status = get_due_status_label_fn(first_row["scheduled_date"])
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
        c2.markdown(f"**Total Items in Dispatch:** `{len(items_df)}`")

        c3.markdown(f"**Requested Date:** `{requested_date_val}`")
        c3.markdown(f"**Scheduled Date:** `{first_row['scheduled_date']}`")

        c4.markdown(
            f"**Priority:** {'🔴 **HIGH**' if first_row['is_priority'] == 1 else '🟢 Normal'}"
        )
        c4.markdown(f"**Status:** `{first_row['status']}`")

        if first_row["driver_name"]:
            st.markdown(f"🚛 **Driver Name:** {first_row['driver_name']}")

        st.divider()

        # -------------------------------------------------------------
        # 1. ADD OR EDIT ITEM SECTION (OUTSIDE THE FORM)
        # -------------------------------------------------------------
        with st.expander("➕ Add Item or Edit to this Dispatch Batch"):
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
                        "Select Item to Add or Modify",
                        df_master["item_name"].tolist(),
                        key=f"add_item_sel_{dispatch_id}",
                    )
                    add_item_info = df_master[
                        df_master["item_name"] == add_item_selected
                    ].iloc[0]
                    avail_qty = float(add_item_info["available_stock"])

                    existing_match = items_df[
                        items_df["item_name"] == add_item_selected
                    ]
                    is_existing = not existing_match.empty

                    if is_existing:
                        current_batch_qty = float(
                            existing_match.iloc[0]["quantity"]
                        )
                        st.info(
                            f"💡 **{add_item_selected}** is already in this batch (Current quantity: `{current_batch_qty} {add_item_info['unit']}`)."
                        )

                    st.caption(
                        f"Available Stock in Inventory for **{add_item_selected}**: `{avail_qty:,.2f} {add_item_info['unit']}`"
                    )

                    col_action, col_add_q, col_add_n = st.columns(
                        [1.5, 1, 2]
                    )

                    with col_action:
                        adjustment_type = st.radio(
                            "Action",
                            options=["Increase Batch", "Decrease Batch"],
                            key=f"adj_type_{dispatch_id}",
                            horizontal=True,
                        )

                    with col_add_q:
                        adj_qty = st.number_input(
                            f"Quantity Difference ({add_item_info['unit']})",
                            min_value=0.01,
                            value=1.0,
                            step=1.0,
                            key=f"add_qty_{dispatch_id}",
                        )

                    with col_add_n:
                        add_notes = st.text_input(
                            "Item Notes",
                            placeholder="Optional instructions...",
                            key=f"add_notes_in_{dispatch_id}",
                        )

                    if st.button(
                        "💾 Apply Changes to Batch Item",
                        key=f"btn_append_item_{dispatch_id}",
                    ):
                        if adjustment_type == "Increase Batch":
                            if adj_qty > avail_qty:
                                st.error(
                                    f"Quantity exceeds available stock ({avail_qty})."
                                )
                            else:
                                if is_existing:
                                    item_id_to_upd = existing_match.iloc[0]["id"]
                                    new_total = current_batch_qty + adj_qty
                                    with get_db() as conn_upd:
                                        c = conn_upd.cursor()
                                        c.execute(
                                            "UPDATE deliveries SET expected_quantity = ? WHERE id = ?",
                                            (new_total, item_id_to_upd),
                                        )
                                        if first_row["status"] in [
                                            "Pending",
                                            "In Transit",
                                        ]:
                                            c.execute(
                                                "UPDATE master_items SET reserved_stock = COALESCE(reserved_stock, 0) + ? WHERE item_name = ?",
                                                (adj_qty, add_item_selected),
                                            )
                                        conn_upd.commit()

                                    # Clear state editor cache before reload
                                    if f"editor_{dispatch_id}" in st.session_state:
                                        del st.session_state[f"editor_{dispatch_id}"]

                                    backup_db_to_gdrive()
                                    st.toast(
                                        f"Increased {add_item_selected} by {adj_qty}.",
                                        icon="✅",
                                    )
                                    st.rerun()
                                else:
                                    add_item_to_dispatch_fn(
                                        dispatch_id,
                                        add_item_selected,
                                        add_item_info["unit"],
                                        adj_qty,
                                        add_notes,
                                        first_row,
                                    )
                                    if f"editor_{dispatch_id}" in st.session_state:
                                        del st.session_state[f"editor_{dispatch_id}"]
                                    st.rerun()

                        elif adjustment_type == "Decrease Batch":
                            if not is_existing:
                                st.error(
                                    f"Cannot decrease {add_item_selected} because it is not currently in this dispatch batch."
                                )
                            elif adj_qty >= current_batch_qty:
                                st.error(
                                    f"Decrease quantity must be less than current batch quantity ({current_batch_qty}). Use the 'Remove Item' section below to remove it completely."
                                )
                            else:
                                item_id_to_upd = existing_match.iloc[0]["id"]
                                new_total = current_batch_qty - adj_qty
                                with get_db() as conn_upd:
                                    c = conn_upd.cursor()
                                    c.execute(
                                        "UPDATE deliveries SET expected_quantity = ? WHERE id = ?",
                                        (new_total, item_id_to_upd),
                                    )
                                    if first_row["status"] in [
                                        "Pending",
                                        "In Transit",
                                    ]:
                                        c.execute(
                                            "UPDATE master_items SET reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?) WHERE item_name = ?",
                                            (adj_qty, add_item_selected),
                                        )
                                    conn_upd.commit()

                                if f"editor_{dispatch_id}" in st.session_state:
                                    del st.session_state[f"editor_{dispatch_id}"]

                                backup_db_to_gdrive()
                                st.toast(
                                    f"Decreased {add_item_selected} by {adj_qty}.",
                                    icon="✅",
                                )
                                st.rerun()

            except Exception as e:
                st.error(f"Error loading master items: {e}")

        st.divider()

        # -------------------------------------------------------------
        # 2. MAIN UNIFIED UPDATE FORM
        # -------------------------------------------------------------
        st.markdown("##### ✏️ Edit & Review Dispatch Details")

        with st.form(key=f"update_dispatch_form_{dispatch_id}"):
            current_date = datetime.strptime(
                str(first_row["scheduled_date"]).split()[0], "%Y-%m-%d"
            ).date()
            new_sched_date = st.date_input(
                "Reschedule Delivery Date",
                value=current_date,
                key=f"resched_date_{dispatch_id}",
            )

            st.markdown(
                "###### 📦 Review & Edit Batch Items (Quantities & Notes)"
            )

            editable_df = items_df[
                ["id", "item_name", "quantity", "unit", "notes"]
            ].copy()

            edited_data = st.data_editor(
                editable_df,
                column_config={
                    "id": None,
                    "item_name": st.column_config.TextColumn(
                        "Item Name", disabled=True
                    ),
                    "unit": st.column_config.TextColumn(
                        "Unit", disabled=True
                    ),
                    "quantity": st.column_config.NumberColumn(
                        "Quantity",
                        min_value=0.01,
                        step=1.0,
                        format="%.2f",
                        disabled=False,
                    ),
                    "notes": st.column_config.TextColumn(
                        "Notes / Instructions",
                        disabled=False,
                    ),
                },
                disabled=["id", "item_name", "unit"],
                use_container_width=True,
                hide_index=True,
                key=f"editor_{dispatch_id}",
            )

            st.divider()
            st.markdown("###### 🚦 Dispatch Status & Info")

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

            col_status_sel, col_driver_sel = st.columns(2)

            with col_status_sel:
                new_status = st.selectbox(
                    "Update Status for Batch",
                    status_options,
                    index=current_idx,
                    key=f"status_select_{dispatch_id}",
                )

            with col_driver_sel:
                driver_input = st.text_input(
                    "Driver Name",
                    value=first_row["driver_name"] or "",
                    placeholder="e.g., John Doe",
                    key=f"driver_input_{dispatch_id}",
                ).strip()

            add_notes_input = st.text_input(
                "Completion / Overall Notes",
                placeholder="Optional delivery details, gate passes, site instructions...",
                key=f"add_notes_{dispatch_id}",
            ).strip()

            st.write("")
            submit_dispatch_update = st.form_submit_button(
                "💾 Update Dispatch & Confirm Changes",
                use_container_width=True,
                type="primary",
            )

        if submit_dispatch_update:
            if new_status == "Completed" and not driver_input:
                st.error(
                    "⚠️ Please specify the Driver Name before marking the dispatch as Completed."
                )
            else:
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        old_status = first_row["status"]

                        for _, edited_row in edited_data.iterrows():
                            item_id = edited_row["id"]
                            new_qty = float(edited_row["quantity"])
                            edited_note = (
                                str(edited_row["notes"]).strip()
                                if pd.notna(edited_row["notes"])
                                and str(edited_row["notes"]).strip()
                                else ""
                            )

                            orig_row = items_df[
                                items_df["id"] == item_id
                            ].iloc[0]
                            old_qty = float(orig_row["quantity"])
                            qty_diff = new_qty - old_qty
                            item_name = orig_row["item_name"]

                            final_notes = edited_note
                            if add_notes_input:
                                final_notes = (
                                    f"{edited_note} [{add_notes_input}]".strip()
                                )

                            cursor.execute(
                                """
                                UPDATE deliveries 
                                SET expected_quantity = ?, expected_date = ?, status = ?, driver_name = ?, notes = ? 
                                WHERE id = ?
                            """,
                                (
                                    new_qty,
                                    str(new_sched_date),
                                    new_status,
                                    driver_input,
                                    final_notes,
                                    item_id,
                                ),
                            )

                            if old_status in ["Pending", "In Transit"]:
                                if new_status == "Completed":
                                    cursor.execute(
                                        """
                                        UPDATE master_items 
                                        SET current_stock = current_stock - ?,
                                            reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?)
                                        WHERE item_name = ?
                                    """,
                                        (new_qty, old_qty, item_name),
                                    )
                                elif new_status == "Cancelled":
                                    cursor.execute(
                                        """
                                        UPDATE master_items 
                                        SET reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?)
                                        WHERE item_name = ?
                                    """,
                                        (old_qty, item_name),
                                    )
                                elif (
                                    new_status in ["Pending", "In Transit"]
                                    and qty_diff != 0
                                ):
                                    cursor.execute(
                                        """
                                        UPDATE master_items 
                                        SET reserved_stock = COALESCE(reserved_stock, 0) + ?
                                        WHERE item_name = ?
                                    """,
                                        (qty_diff, item_name),
                                    )

                        conn.commit()

                    if f"editor_{dispatch_id}" in st.session_state:
                        del st.session_state[f"editor_{dispatch_id}"]

                    backup_db_to_gdrive()
                    st.toast(
                        "Dispatch batch and item quantities successfully updated!",
                        icon="✅",
                    )
                    st.rerun()

                except Exception as e:
                    st.error(f"Error updating dispatch batch: {e}")

        st.divider()

        # -------------------------------------------------------------
        # 3. REMOVE ITEM SECTION
        # -------------------------------------------------------------
        col_del_item, _ = st.columns([2, 1])
        with col_del_item:
            item_to_remove = st.selectbox(
                "Remove Single Item from Batch",
                options=items_df["id"].tolist(),
                format_func=lambda x: items_df[items_df["id"] == x][
                    "item_name"
                ].values[0],
                key=f"select_remove_{dispatch_id}",
            )
            if st.button(
                "🗑️ Remove Selected Item", key=f"btn_remove_{dispatch_id}"
            ):
                if len(items_df) <= 1:
                    st.error(
                        "Cannot remove the only item in a dispatch batch. Cancel the dispatch status instead."
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

                        if f"editor_{dispatch_id}" in st.session_state:
                            del st.session_state[f"editor_{dispatch_id}"]

                        backup_db_to_gdrive()
                        st.toast(
                            f"Removed {rem_name} from dispatch batch.",
                            icon="🗑️",
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error removing item: {e}")
