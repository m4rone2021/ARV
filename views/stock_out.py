import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

from database import UPLOAD_DIR, sb, upload_file_to_gdrive


def render_stock_out(user_name, user_role):
    st.title("Stock Out Workflow")
    st.caption(
        "Record outgoing materials, validate real-time stock balances, and track stock dispatches."
    )

    flash = st.session_state.pop("flash_msg", None)
    if flash and isinstance(flash, tuple) and len(flash) == 2:
        msg_type, msg_text = flash
        if msg_type == "success":
            st.success(msg_text)
        elif msg_type == "warning":
            st.warning(msg_text)

    tab_record, tab_history = st.tabs(
        ["Issue Stock / Material Requisition", "Outgoing Stock History"]
    )

    # ================================================================
    # TAB 1: ISSUE STOCK
    # ================================================================
    with tab_record:
        st.subheader("Record Outgoing Material")

        try:
            res = (
                sb()
                .table("master_items")
                .select("item_name, category, unit, current_stock, min_threshold")
                .order("item_name")
                .execute()
            )
            items_df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error loading items catalog: {e}")
            return

        if items_df.empty:
            st.info("No items found. Add items first before issuing stock.")
            return

        selected_item_name = st.selectbox(
            "Select Item to Issue*",
            items_df["item_name"].tolist(),
            key="select_stock_out_item",
        )

        item_row = items_df[items_df["item_name"] == selected_item_name].iloc[0]
        current_available = float(item_row["current_stock"] or 0)
        unit = str(item_row["unit"])
        min_thresh = float(item_row["min_threshold"] or 0)

        st.divider()
        st.metric("Current Available Stock", f"{current_available:,.2f} {unit}")
        st.metric("Category", str(item_row["category"]))
        st.metric("Minimum Threshold", f"{min_thresh:,.2f} {unit}")

        is_out_of_stock = current_available <= 0
        if is_out_of_stock:
            st.error(
                f"⚠️ **{selected_item_name}** is OUT OF STOCK. Submissions are disabled."
            )

        st.divider()

        with st.form("stock_out_form", clear_on_submit=True):
            quantity_out = st.number_input(
                f"Quantity to Issue ({unit})*",
                min_value=0.01,
                value=1.00,
                step=1.00,
                format="%.2f",
                disabled=is_out_of_stock,
            )
            recipient = st.text_input(
                "Issued To / Department / Project*",
                placeholder="e.g., Site Phase 2 / John Doe",
                disabled=is_out_of_stock,
            )
            req_file = st.file_uploader(
                "Attach Requisition Form / Release Pass",
                type=["png", "jpg", "jpeg", "pdf"],
                disabled=is_out_of_stock,
            )
            notes = st.text_input(
                "Purpose / Requisition Details",
                placeholder="e.g., Formwork preparation, Maintenance release",
                disabled=is_out_of_stock,
            )

            submit_btn = st.form_submit_button(
                "Submit Stock Out",
                use_container_width=True,
                disabled=is_out_of_stock,
            )

            if submit_btn:
                clean_recipient = recipient.strip()
                clean_notes = notes.strip()

                if not clean_recipient:
                    st.error("Please specify the recipient, department, or project.")
                elif quantity_out <= 0:
                    st.error("Quantity to issue must be greater than zero.")
                else:
                    drive_link = None
                    if req_file is not None:
                        with st.spinner("Uploading document to Google Drive..."):
                            file_bytes = req_file.getvalue()
                            file_name = f"StockOut_{selected_item_name}_{req_file.name}"
                            drive_link = upload_file_to_gdrive(
                                file_bytes=file_bytes,
                                file_name=file_name,
                                mime_type=req_file.type,
                            )

                    # Build notes string
                    formatted_notes = f"Issued to: {clean_recipient}"
                    if clean_notes:
                        formatted_notes += f" | Notes: {clean_notes}"
                    if drive_link:
                        formatted_notes += f" | Attachment: {drive_link}"

                    # Run the atomic RPC. If insufficient stock, it raises.
                    try:
                        sb().rpc(
                            "record_stock_transaction",
                            {
                                "p_type": "OUT",
                                "p_item_name": selected_item_name,
                                "p_quantity": float(quantity_out),
                                "p_unit": unit,
                                "p_handled_by": user_name,
                                "p_notes": formatted_notes,
                                "p_project_name": None,
                            },
                        ).execute()
                    except Exception as e:
                        st.error(f"Error executing Stock Out: {e}")
                        st.stop()

                    # Re-read updated stock for the flash message
                    fresh = (
                        sb()
                        .table("master_items")
                        .select("current_stock")
                        .eq("item_name", selected_item_name)
                        .limit(1)
                        .execute()
                        .data
                    )
                    updated_stock = float(fresh[0]["current_stock"]) if fresh else 0.0

                    msg = f"Issued {quantity_out:,.2f} {unit} of {selected_item_name}. Remaining: {updated_stock:,.2f} {unit}."
                    if updated_stock <= min_thresh:
                        msg += " 🔔 Low Stock Alert triggered!"

                    st.session_state["flash_msg"] = ("success", msg)
                    st.rerun()

    # ================================================================
    # TAB 2: OUTGOING STOCK HISTORY
    # ================================================================
    with tab_history:
        st.subheader("Outgoing Stock Transaction Logs")

        try:
            res = (
                sb()
                .table("transactions")
                .select("id, timestamp, item_name, quantity, unit, handled_by, notes")
                .eq("type", "OUT")
                .order("timestamp", desc=True)
                .limit(100)
                .execute()
            )
            history_df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error loading Stock Out history: {e}")
            return

        if history_df.empty:
            st.info("No outgoing stock transactions recorded yet.")
            return

        df_display = history_df.rename(
            columns={
                "id": "Log ID",
                "timestamp": "Date & Time",
                "item_name": "Item Name",
                "quantity": "Quantity Issued",
                "unit": "Unit",
                "handled_by": "Handled By",
                "notes": "Recipient / Purpose",
            }
        )
        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Recipient / Purpose": st.column_config.LinkColumn(
                    "Recipient / Purpose",
                    help="Contains recipient details and Google Drive attachment links.",
                )
            },
        )
