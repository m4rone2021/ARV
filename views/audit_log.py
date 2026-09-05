import re
from pathlib import Path
import pandas as pd
import streamlit as st
from database import get_db

# Ensure UPLOAD_DIR fallback
try:
    from database import UPLOAD_DIR
except ImportError:
    UPLOAD_DIR = Path(r"D:\Inventory System Files\uploads")


def extract_drive_link(notes_str: str) -> str:
    """Extract Google Drive URL from notes string if available."""
    if not isinstance(notes_str, str):
        return ""
    match = re.search(r"Drive Link:\s*(https?://[^\s|]+)", notes_str)
    return match.group(1) if match else ""


def extract_attachment_filename(notes_str: str) -> str:
    """Extract local attachment filename from notes string if available."""
    if not isinstance(notes_str, str):
        return ""
    match = re.search(r"Attachment:\s*([^\s|]+)", notes_str)
    return match.group(1) if match else ""


def render_audit_log(user_name: str, user_role: str):
    """Renders the transaction history and audit log page with filters and downloads."""
    st.title("📜 Audit Log & Transaction History")
    st.caption("Track all stock-in, stock-out, attached receipts, and Google Drive links.")

    # Filter controls
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        type_filter = st.selectbox(
            "Filter by Type", ["All", "STOCK IN", "STOCK OUT"]
        )

    with col2:
        search_query = st.text_input(
            "Search Item or Handler", placeholder="Type to search..."
        )

    with col3:
        st.write("")  # Spacing
        st.write("")
        st.button("🔄 Refresh", use_container_width=True)

    try:
        with get_db() as conn:
            query = """
                SELECT id, timestamp, type, item_name, quantity, unit, handled_by, notes 
                FROM transactions 
                WHERE 1=1
            """
            params = []

            if type_filter == "STOCK IN":
                query += " AND (type = 'STOCK IN' OR type = 'IN')"
            elif type_filter == "STOCK OUT":
                query += " AND (type = 'STOCK OUT' OR type = 'OUT')"

            if search_query.strip():
                query += " AND (item_name LIKE ? OR handled_by LIKE ? OR notes LIKE ?)"
                wildcard = f"%{search_query.strip()}%"
                params.extend([wildcard, wildcard, wildcard])

            query += " ORDER BY id DESC"

            df = pd.read_sql_query(query, conn, params=params)

        if not df.empty:
            # Metrics Summary calculated BEFORE column renaming
            in_count = len(df[df["type"].isin(["STOCK IN", "IN"])])
            out_count = len(df[df["type"].isin(["STOCK OUT", "OUT"])])

            m1, m2, m3 = st.columns(3)
            m1.metric("Total Transactions Logged", len(df))
            m2.metric("Stock In Logs", in_count)
            m3.metric("Stock Out Logs", out_count)

            # Display formatting
            df_display = df.rename(
                columns={
                    "id": "Trans ID",
                    "timestamp": "Date & Time",
                    "type": "Type",
                    "item_name": "Item Name",
                    "quantity": "Quantity",
                    "unit": "Unit",
                    "handled_by": "Handled By",
                    "notes": "Notes / Remarks",
                }
            )

            st.divider()
            st.dataframe(df_display, use_container_width=True, hide_index=True)

            # -------------------------------------------------------------
            # ATTACHMENT & GOOGLE DRIVE LINK EXPANDER
            # -------------------------------------------------------------
            with st.expander("📎 Transaction Attachments & Drive Files"):
                has_media = False
                for _, row in df.iterrows():
                    notes = str(row["notes"])
                    drive_url = extract_drive_link(notes)
                    local_file = extract_attachment_filename(notes)

                    if drive_url:
                        has_media = True
                        st.markdown(
                            f"🔗 **Log #{row['id']} ({row['type']} - {row['item_name']})**: "
                            f"[View Delivery Receipt / Document on Google Drive]({drive_url})"
                        )
                    elif local_file:
                        has_media = True
                        file_path = Path(UPLOAD_DIR) / local_file
                        if file_path.exists():
                            with open(file_path, "rb") as f:
                                st.download_button(
                                    label=f"📄 Download Local File: {local_file} (Log #{row['id']})",
                                    data=f.read(),
                                    file_name=local_file,
                                    key=f"audit_dl_{row['id']}",
                                )
                        else:
                            st.caption(
                                f"⚠️ Log #{row['id']} local file `{local_file}` not found on disk."
                            )

                if not has_media:
                    st.info("No external file links or attachments found in the filtered records.")

            # -------------------------------------------------------------
            # EXPORT CSV
            # -------------------------------------------------------------
            csv_data = df_display.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 Export Audit Log to CSV",
                data=csv_data,
                file_name="audit_log.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.info("No transaction logs found matching the selected filters.")

    except Exception as e:
        st.error(f"Error loading audit log: {e}")
