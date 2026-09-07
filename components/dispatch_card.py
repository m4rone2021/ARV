import sqlite3
from datetime import datetime
import pandas as pd
import streamlit as st

from database import backup_db_to_gdrive, get_db


def render_dispatch_card(
    dispatch_id, items_df, get_due_status_label_fn, add_item_to_dispatch_fn
):
    """Renders a single dispatch card with a unified review table where item quantities, 
    units, notes, and dispatch status are directly editable.
    """

    def fetch_latest_items_df(d_id):
        """Helper to re-fetch the latest items for this dispatch batch directly from DB."""
        with get_db() as conn_fetch:
            return pd.read_sql_query(
                """
                SELECT id, dispatch_id, item_name, unit, 
                       expected_quantity AS quantity, notes, status,
                       destination, scheduled_date, requested_by, project,
                       is_priority, driver_name, created_at
                FROM deliveries 
                WHERE dispatch_id = ?
            """,
                conn_fetch,
                params=(d_id,),
            )

    # Always ensure fresh state
    current_items_df = fetch_latest_items_df(dispatch_id) if items_df is None or items_df.empty else items_df.copy()

    # Initialize state for data editor re-rendering
    if f"editor_ver_{dispatch_id}" not in st.session_state:
        st.session_state[f"editor_ver_{dispatch_id}"] = 0

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

    with st.expander(header_label):
        c1, c2, c3, c4 = st.columns(4)

        requested_date_val = first_row.get(
            "created_at", first_row.get("requested_date", "N/A")
        )

        c1.markdown(f"**Dispatch ID:** `{dispatch_id}`")
        c1.markdown(f"**Requested By:** {first_row['requested_by'] if first_row['requested_by'] else 'N/A'}")
        c1.markdown(f"**Destination:** {first_row['destination']}")

        c2.markdown(f"**Project:** {first_row['project'] if first_row['project'] else 'N/A'}")
        c2.markdown(f"**Total Items in Dispatch:** `{len(current_items_df)}`")

        c3.markdown(f"**Requested Date:** `{requested_date_val}`")
        c3.markdown(f"**Scheduled Date:** `{first_row['scheduled_date']}`")

        c4.markdown(f"**Priority:** {'🔴 **HIGH**' if first_row['is_priority'] == 1 else '🟢 Normal'}")
        c4.markdown(f"**Status:** `{first_row['status']}`")

        if first_row["driver_name"]:
            st.markdown(f"🚛 **Driver Name:** {first_row['driver_name']}")

        st.divider()

        # -------------------------------------------------------------
        # UNIFIED EDIT & REVIEW DISPATCH DETAILS FORM
        # -------------------------------------------------------------
        st.markdown(f"##### ✏️ Edit & Review Batch Details — Dispatch #{dispatch_id}")

        with st.form(key=f"update_dispatch_form_{dispatch_id}"):
            current_date = pd.to_datetime(first_row["scheduled_date"]).date()
            new_sched_date = st.date_input(
                "Reschedule Delivery Date",
                value=current_date,
                key=f"resched_date_{dispatch_id}",
            )

            st.markdown("###### 📦 Dispatch Items Review Table (Edit quantities and notes directly below)")

            editable_df = current_items_df[
                ["id", "item_name", "quantity", "unit", "notes"]
            ].copy()

            editor_key = f"editor_{dispatch_id}_v{st.session_state[f'editor_ver_{dispatch_id}']}"

            edited_data = st.data_editor(
                editable_df,
                column_config={
                    "id": None,
                    "item_name": st.column_config.TextColumn("Item Name", disabled=True),
                    "quantity": st.column_config.NumberColumn(
                        "Dispatch Quantity",
                        min_value=0.01,
                        step=1.0,
                        format="%.2f",
                        disabled=False,
                    ),
                    "unit": st.column_config.TextColumn("Unit", disabled=True),
                    "notes": st.column_config.TextColumn(
                        "Notes / Instructions",
                        disabled=False,
                    ),
                },
                disabled=["id", "item_name", "unit"],
                use_container_width=True,
                hide_index=True,
                key=editor_key,
            )

            st.divider()
            st.markdown("###### 🚦 Status & Assignment")

            status_options = ["Pending", "In Transit", "Completed", "Cancelled"]
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
                f"💾 Save Changes to Dispatch #{dispatch_id}",
                use_container_width=True,
                type="primary",
            )

        if submit_dispatch_update:
            if new_status == "Completed" and not driver_input:
                st.error("⚠️ Please specify the Driver Name before marking the dispatch as Completed.")
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
                                if pd.notna(edited_row["notes"]) and str(edited_row["notes"]).strip()
                                else ""
                            )

                            orig_row = current_items_df[current_items_df["id"] == item_id].iloc[0]
                            old_qty = float(orig_row["quantity"])
                            item_name = orig_row["item_name"]
                            qty_diff = new_qty - old_qty

                            final_notes = edited_note
                            if add_notes_input:
                                final_notes = f"{edited_note} [{add_notes_input}]".strip()

                            # 1. Update delivery record
                            cursor.execute(
                                """
                                UPDATE deliveries 
                                SET expected_quantity = ?, scheduled_date = ?, status = ?, driver_name = ?, notes = ? 
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

                            # 2. Manage reserved stock and current inventory balance
                            if old_status in ["Pending", "In Transit"]:
                                if new_status in ["Pending", "In Transit"]:
                                    # Adjust reserved stock by the quantity difference
                                    if qty_diff != 0:
                                        cursor.execute(
                                            """
                                            UPDATE master_items 
                                            SET reserved_stock = MAX(0, COALESCE(reserved_stock, 0) + ?)
                                            WHERE item_name = ?
                                        """,
                                            (qty_diff, item_name),
                                        )
                                elif new_status == "Completed":
                                    # Deduct current stock and clear reserved allocation
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
                                    # Clear reserved allocation
                                    cursor.execute(
                                        """
                                        UPDATE master_items 
                                        SET reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?)
                                        WHERE item_name = ?
                                    """,
                                        (old_qty, item_name),
                                    )

                        conn.commit()

                    st.session_state[f"editor_ver_{dispatch_id}"] += 1
                    backup_db_to_gdrive()
                    st.toast(f"Dispatch #{dispatch_id} successfully updated!", icon="✅")
                    st.rerun()

                except Exception as e:
                    st.error(f"Error updating dispatch batch: {e}")

        st.divider()

        # -------------------------------------------------------------
        # REMOVE ITEM SECTION
        # -------------------------------------------------------------
        col_del_item, _ = st.columns([2, 1])
        with col_del_item:
            item_to_remove = st.selectbox(
                "Remove Single Item from Batch",
                options=current_items_df["id"].tolist(),
                format_func=lambda x: current_items_df[
                    current_items_df["id"] == x
                ]["item_name"].values[0],
                key=f"select_remove_{dispatch_id}",
            )
            if st.button("🗑️ Remove Selected Item", key=f"btn_remove_{dispatch_id}"):
                if len(current_items_df) <= 1:
                    st.error(
                        "Cannot remove the only item in a dispatch batch. Cancel the dispatch status instead."
                    )
                else:
                    try:
                        rem_row = current_items_df[
                            current_items_df["id"] == item_to_remove
                        ].iloc[0]
                        rem_qty = float(rem_row["quantity"])
                        rem_name = rem_row["item_name"]

                        with get_db() as conn_rem:
                            cursor = conn_rem.cursor()
                            cursor.execute(
                                "DELETE FROM deliveries WHERE id = ?",
                                (item_to_remove,),
                            )

                            if first_row["status"] in ["Pending", "In Transit"]:
                                cursor.execute(
                                    """
                                    UPDATE master_items 
                                    SET reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?) 
                                    WHERE item_name = ?
                                """,
                                    (rem_qty, rem_name),
                                )
                            conn_rem.commit()

                        st.session_state[f"editor_ver_{dispatch_id}"] += 1
                        backup_db_to_gdrive()
                        st.toast(
                            f"Removed {rem_name} from Dispatch #{dispatch_id}.",
                            icon="🗑️",
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error removing item: {e}")
