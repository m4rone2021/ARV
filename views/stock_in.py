# views/stock_in.py
import os
import uuid
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from database import get_db, init_db, upload_file_to_gdrive, backup_db_to_gdrive

# Safe fallback directory resolution across OS platforms
try:
    from database import UPLOAD_DIR
except ImportError:
    UPLOAD_DIR = Path(tempfile.gettempdir()) / "inventory_uploads"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_filename(filename: str) -> str:
    """Sanitize uploaded filenames to prevent path traversal issues."""
    clean_name = os.path.basename(filename)
    return "".join(c for c in clean_name if c.isalnum() or c in "._- ")


def trigger_gdrive_sync():
    """Helper function to run backup to Google Drive without breaking UI flow on failure."""
    try:
        backup_db_to_gdrive()
        st.toast("☁️ Synced database to Google Drive!", icon="✅")
    except Exception as e:
        st.warning(f"⚠️ Saved transaction locally, but Drive backup failed: {e}")


def render_stock_in(user_name: str, user_role: str):
    st.title("📥 Stock IN Receive Log")
    st.caption("Record site material receipts, deliveries, and stock replenishment.")

    init_db()

    # Load master items catalog
    try:
        with get_db() as conn:
            items_df = pd.read_sql_query(
                "SELECT item_name, category, unit, current_stock FROM master_items ORDER BY item_name ASC",
                conn,
            )
    except Exception as e:
        st.error(f"Failed to fetch master items: {e}")
        return

    if items_df.empty:
        st.warning(
            "⚠️ No master items found in the database. Please add items in **Manage Master Items** first."
        )
        return

    tab_receive, tab_history = st.tabs(["📥 Receive Stock", "📜 Recent Stock IN History"])

    # -------------------------------------------------------------
    # TAB 1: RECEIVE STOCK FORM
    # -------------------------------------------------------------
    with tab_receive:
        with st.form("stock_in_form", clear_on_submit=True):
            col1, col2 = st.columns(2)

            with col1:
                selected_item = st.selectbox(
                    "Select Master Item*", items_df["item_name"].tolist()
                )

                item_info = items_df[items_df["item_name"] == selected_item].iloc[0]
                current_stock = float(item_info["current_stock"])
                unit = str(item_info["unit"])
                category = str(item_info["category"])

                st.info(
                    f"Category: **{category}** | Current Balance: **{current_stock:,.2f} {unit}**"
                )

                quantity = st.number_input(
                    f"Received Quantity ({unit})*",
                    min_value=0.01,
                    value=1.00,
                    step=1.00,
                    format="%.2f",
                )

            with col2:
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
                "📥 Log Stock IN Receipt", use_container_width=True
            )

            if submit_btn:
                supplier_clean = supplier_source.strip()
                remarks_clean = remarks.strip()

                if not supplier_clean:
                    st.error("⚠️ 'Supplier / Source / DR No.' is required.")
                elif quantity <= 0:
                    st.error("⚠️ Received quantity must be greater than zero.")
                else:
                    attachment_filename = None
                    drive_link = None

                    # Handle file saving and drive synchronization
                    if uploaded_file is not None:
                        clean_original = sanitize_filename(uploaded_file.name)
                        attachment_filename = f"IN_{uuid.uuid4().hex[:8]}_{clean_original}"
                        save_path = Path(UPLOAD_DIR) / attachment_filename

                        try:
                            with open(save_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())

                            drive_link = upload_file_to_gdrive(save_path)
                        except Exception as file_err:
                            st.error(f"Failed to save uploaded receipt: {file_err}")
                            attachment_filename = None

                    try:
                        # Construct audit details string
                        notes_parts = [f"Supplier/DR: {supplier_clean}"]
                        if remarks_clean:
                            notes_parts.append(f"Remarks: {remarks_clean}")
                        if drive_link:
                            notes_parts.append(f"Drive Link: {drive_link}")
                        elif attachment_filename:
                            notes_parts.append(f"Attachment: {attachment_filename}")

                        full_notes = " | ".join(notes_parts)

                        # Atomic transaction write
                        with get_db() as conn:
                            cursor = conn.cursor()
                            
                            cursor.execute(
                                """
                                UPDATE master_items 
                                SET current_stock = current_stock + ? 
                                WHERE item_name = ?
                                """,
                                (quantity, selected_item),
                            )

                            cursor.execute(
                                """
                                INSERT INTO transactions (type, item_name, quantity, unit, handled_by, notes)
                                VALUES ('STOCK IN', ?, ?, ?, ?, ?)
                                """,
                                (selected_item, quantity, unit, user_name, full_notes),
                            )

                            conn.commit()

                        # Run Google Drive backup safely
                        trigger_gdrive_sync()

                        st.toast(
                            f"✅ Received {quantity:,.2f} {unit} of {selected_item}.",
                            icon="📥",
                        )
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error executing stock-in transaction: {e}")

    # -------------------------------------------------------------
    # TAB 2: RECEIPT HISTORY & AUDIT LOG
    # -------------------------------------------------------------
    with tab_history:
        st.subheader("Recent Stock IN Entries")
        try:
            with get_db() as conn:
                history_df = pd.read_sql_query(
                    """
                    SELECT id, timestamp, item_name, quantity, unit, handled_by, notes 
                    FROM transactions 
                    WHERE type = 'STOCK IN' 
                    ORDER BY id DESC LIMIT 50
                    """,
                    conn,
                )

            if not history_df.empty:
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
                    use_container_width=True,
                    hide_index=True,
                )

                # Expandable Inspector for Attachments
                with st.expander("📎 Download / View Log Attachments"):
                    has_attachments = False
                    for _, row in history_df.iterrows():
                        notes_str = str(row["notes"])

                        if "Drive Link: " in notes_str:
                            has_attachments = True
                            link = notes_str.split("Drive Link: ")[-1].split(" | ")[0].strip()
                            st.markdown(
                                f"🔗 **Log #{row['id']} ({row['item_name']})**: [View Attachment on Google Drive]({link})"
                            )

                        elif "Attachment: " in notes_str:
                            has_attachments = True
                            att_file = notes_str.split("Attachment: ")[-1].split(" | ")[0].strip()
                            file_path = Path(UPLOAD_DIR) / att_file

                            if file_path.exists():
                                with open(file_path, "rb") as f:
                                    st.download_button(
                                        label=f"📄 Download {att_file} (Log #{row['id']} - {row['item_name']})",
                                        data=f.read(),
                                        file_name=att_file,
                                        key=f"dl_btn_{row['id']}",
                                    )
                            else:
                                st.caption(f"⚠️ Attachment `{att_file}` not found on local storage.")

                    if not has_attachments:
                        st.info("No attachments logged in recent history entries.")
            else:
                st.info("No recent Stock IN transactions recorded yet.")
        except Exception as e:
            st.error(f"Error loading stock-in transaction history: {e}")
