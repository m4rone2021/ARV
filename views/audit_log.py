import io
import re
from pathlib import Path
import pandas as pd
import streamlit as st
from database import get_db

# Google API imports for sync
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

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


def upload_csv_to_gdrive(csv_bytes: bytes, filename: str = "audit_log.csv") -> str | None:
    """Helper function to upload CSV data directly to Google Drive using credentials in st.secrets."""
    try:
        token_info = st.secrets["gdrive_token"]
        folder_id = st.secrets["google_drive"]["folder_id"]

        creds = Credentials(
            token=token_info.get("token"),
            refresh_token=token_info.get("refresh_token"),
            token_uri=token_info.get("token_uri"),
            client_id=token_info.get("client_id"),
            client_secret=token_info.get("client_secret"),
            scopes=token_info.get("scopes"),
        )

        service = build("drive", "v3", credentials=creds)

        file_metadata = {
            "name": filename,
            "parents": [folder_id],
        }

        media = MediaIoBaseUpload(
            io.BytesIO(csv_bytes),
            mimetype="text/csv",
            resumable=True
        )

        uploaded_file = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id, webViewLink")
            .execute()
        )

        return uploaded_file.get("webViewLink")

    except Exception as e:
        st.error(f"Failed to sync with Google Drive: {e}")
        return None


def render_audit_log(user_name: str, user_role: str):
    """Renders the transaction history and audit log page with filters, downloads, and Drive sync."""
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
            # EXPORT & GOOGLE DRIVE SYNC
            # -------------------------------------------------------------
            st.divider()
            csv_data = df_display.to_csv(index=False).encode("utf-8")
            btn_col1, btn_col2 = st.columns(2)

            with btn_col1:
                st.download_button(
                    label="📥 Export Audit Log to CSV",
                    data=csv_data,
                    file_name="audit_log.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            with btn_col2:
                if st.button("☁️ Sync Audit Log to Google Drive", use_container_width=True):
                    with st.spinner("Uploading to Google Drive..."):
                        file_link = upload_csv_to_gdrive(csv_data, filename="audit_log_backup.csv")
                        if file_link:
                            st.success("Successfully uploaded to Google Drive!")
                            st.markdown(f"🔗 [Open Uploaded File in Drive]({file_link})")

        else:
            st.info("No transaction logs found matching the selected filters.")

    except Exception as e:
        st.error(f"Error loading audit log: {e}")
