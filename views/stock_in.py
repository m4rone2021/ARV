import os
import tempfile
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

from database import UPLOAD_DIR, sb, upload_file_to_gdrive


def sanitize_filename(filename: str) -> str:
    clean_name = os.path.basename(filename)
    return "".join(c for c in clean_name if c.isalnum() or c in "._- ")


def render_stock_in(user_name: str, user_role: str):
    st.title("Stock IN Receive Log")
    st.caption("Record site material receipts, deliveries, and stock replenishment.")

    try:
        res = (
            sb()
            .table("master_items")
            .select("item_name, category, unit, current_stock")
            .order("item_name")
            .execute()
        )
        items_df = pd.DataFrame(res.data or [])
    except Exception as e:
        st.error(f"Failed to fetch master items: {e}")
        return

    if items_df.empty:
        st.warning("No master items found. Please add items in Manage Master Items first.")
        return

    tab_receive, tab_history = st.tabs(
        ["Receive Stock", "Recent Stock IN History"]
    )

    with tab_receive:
        selected_item = st.selectbox(
            "Select Master Item*", items_df["item_name"].tolist()
        )

        item_info = items_df[items_df["item_name"] == selected_item].iloc[0]
        current_stock = float(item_info["current_stock"] or 0)
        unit = str(item_info["unit"])
        category = str(item_info["category"])

        st.info(
            f"Category: **{category}** | Current Balance: **{current_stock:,.2f} {unit}**"
        )

        with st.form("stock_in_form", clear_on_submit=True):
            quantity = st.number_input(
                f"Received Quantity ({unit})*",
                min_value=0.01,
                value=1.00,
                step=1.00,
                format="%.2f",
            )
            supplier_source = st.text_input(
                "Supplier / Source / DR No.*",
                placeholder="e.g., ABC Hardware, DR #10293",
            )
            remarks = st.text_input(
                "Remarks / Notes",
                placeholder="e.g., Batch code, Storage bay A-3",
            )
            uploaded_file = st.file_uploader(
                "Attach Delivery Receipt / Invoice (Optional)",
                type=["png", "jpg", "jpeg", "pdf"],
            )

            submit_btn = st.form_submit_button(
                "Log Stock IN Receipt", use_container_width=True
            )

            if submit_btn:
                supplier_clean = supplier_source.strip()
                remarks_clean = remarks.strip()

                if not supplier_clean:
                    st.error("Supplier / Source / DR No. is required.")
                elif quantity <= 0:
                    st.error("Quantity must be greater than zero.")
                else:
                    attachment_filename = None
                    drive_link = None

                    if uploaded_file is not None:
                        clean_original = sanitize_filename(uploaded_file.name)
                        attachment_filename = f"IN_{uuid.uuid4().hex[:8]}_{clean_original}"
                        save_path = Path(UPLOAD_DIR) / attachment_filename
                        file_bytes = uploaded_file.getvalue()

                        try:
                            with open(save_path, "wb") as f:
                                f.write(file_bytes)
                            drive_link = upload_file_to_gdrive(
                                file_bytes=file_bytes,
                                file_name=attachment_filename,
                                mime_type=uploaded_file.type or "application/octet-stream",
                            )
                        except Exception as file_err:
                            st.error(f"Failed to process attachment: {file_err}")
                            attachment_filename = None

                    notes_parts = [f"Supplier/DR: {supplier_clean}"]
                    if remarks_clean:
                        notes_parts.append(f"Remarks: {remarks_clean}")
                    if drive_link:
                        notes_parts.append(f"Drive Link: {drive_link}")
                    elif attachment_filename:
                        notes_parts.append(f"Attachment: {attachment_filename}")
                    full_notes = " | ".join(notes_parts)

                    try:
                        sb().rpc(
                            "record_stock_transaction",
                            {
                                "p_type": "IN",
                                "p_item_name": selected_item,
                                "p_quantity": float(quantity),
                                "p_unit": unit,
                                "p_handled_by": user_name,
                                "p_notes": full_notes,
                                "p_project_name": None,
                            },
                        ).execute()
                    except Exception as e:
                        st.error(f"Error executing stock-in transaction: {e}")
                        st.stop()

                    st.toast(f"Received {quantity:,.2f} {unit} of {selected_item}.")
                    st.rerun()

    with tab_history:
        st.subheader("Recent Stock IN Entries")
        try:
            res = (
                sb()
                .table("transactions")
                .select("id, timestamp, item_name, quantity, unit, handled_by, notes")
                .eq("type", "IN")
                .order("timestamp", desc=True)
                .limit(50)
                .execute()
            )
            history_df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error loading stock-in history: {e}")
            return

        if history_df.empty:
            st.info("No recent Stock IN transactions recorded yet.")
            return

        def extract_drive_link(notes: str):
            if "Drive Link: " in str(notes):
                return notes.split("Drive Link: ")[-1].split(" | ")[0].strip()
            return None

        history_df["Drive Receipt"] = history_df["notes"].apply(extract_drive_link)

        st.dataframe(
            history_df.rename(
                columns={
                    "id": "ID",
                    "timestamp": "Timestamp",
                    "item_name": "Item Name",
                    "quantity": "Quantity",
                    "unit": "Unit",
                    "handled_by": "Received By",
                    "notes": "Details & Attachment Ref",
                }
            ),
            column_config={
                "Drive Receipt": st.column_config.LinkColumn(
                    "Drive Link", display_text="View Receipt"
                )
            },
            use_container_width=True,
            hide_index=True,
        )

        with st.expander("Download Local Fallback Attachments"):
            has_local = False
            for _, row in history_df.iterrows():
                notes_str = str(row["notes"])
                if "Attachment: " in notes_str and "Drive Link: " not in notes_str:
                    has_local = True
                    att_file = notes_str.split("Attachment: ")[-1].split(" | ")[0].strip()
                    file_path = Path(UPLOAD_DIR) / att_file
                    if file_path.exists():
                        with open(file_path, "rb") as f:
                            st.download_button(
                                label=f"Download {att_file} (Log #{row['id']} - {row['item_name']})",
                                data=f.read(),
                                file_name=att_file,
                                key=f"dl_btn_{row['id']}",
                                use_container_width=True,
                            )
                    else:
                        st.caption(f"Attachment {att_file} not found locally.")
            if not has_local:
                st.info("No local fallback attachments in recent history.")
