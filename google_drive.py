import io
import os
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaFileUpload
import streamlit as st

# Scope for full access to drive files created by service account
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def get_drive_service():
    """Authenticate and build the Google Drive API service client using Streamlit secrets."""
    if "gcp_service_account" not in st.secrets:
        raise ValueError(
            "Missing 'gcp_service_account' in Streamlit secrets configuration."
        )

    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds)


def upload_file_to_drive(file_buffer, filename, mime_type):
    """
    Uploads a Streamlit UploadedFile byte stream directly to the configured Google Drive folder.
    """
    try:
        service = get_drive_service()
        folder_id = st.secrets.get("google_drive", {}).get("folder_id")

        file_metadata = {"name": filename}
        if folder_id:
            file_metadata["parents"] = [folder_id]

        # Convert Streamlit UploadedFile to IO byte stream
        media = MediaIoBaseUpload(
            io.BytesIO(file_buffer.getvalue()),
            mimetype=mime_type,
            resumable=True,
        )

        uploaded_file = (
            service.files()
            .create(
                body=file_metadata, media_body=media, fields="id, webViewLink"
            )
            .execute()
        )

        # Grant general read permissions so anyone with the link can view receipt/document
        service.permissions().create(
            fileId=uploaded_file.get("id"),
            body={"type": "anyone", "role": "reader"},
        ).execute()

        return uploaded_file.get("webViewLink")

    except Exception as e:
        st.error(f"Google Drive Upload Error: {e}")
        return None


def backup_local_file_to_drive(file_path: Path, mime_type: str = "application/x-sqlite3"):
    """
    Uploads a local disk file (e.g. D:\\Inventory System Files\\inventory.db) directly to Google Drive.
    Used for automated background backups.
    """
    if not file_path.exists():
        st.warning(f"Backup target file not found: {file_path}")
        return None

    try:
        service = get_drive_service()
        folder_id = st.secrets.get("google_drive", {}).get("folder_id")

        file_metadata = {"name": file_path.name}
        if folder_id:
            file_metadata["parents"] = [folder_id]

        media = MediaFileUpload(
            str(file_path),
            mimetype=mime_type,
            resumable=True
        )

        uploaded_file = (
            service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink"
            )
            .execute()
        )

        return uploaded_file.get("webViewLink")

    except Exception as e:
        st.error(f"Failed to backup local file to Google Drive: {e}")
        return None
