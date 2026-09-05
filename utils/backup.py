import sqlite3
import tempfile
import io
from datetime import datetime
from pathlib import Path
import streamlit as st
from googleapiclient.http import MediaFileUpload
from tests.setup_test_drive import get_drive_service

def create_local_sqlite_dump(db_path: str) -> str:
    """
    Creates a safe, consistent copy of the active SQLite database
    using SQLite's online backup API (prevents corrupted backup reads).
    """
    source_path = Path(db_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Database file not found at {db_path}")

    # Create a temporary file to store the backup
    temp_dir = tempfile.gettempdir()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"inventory_backup_{timestamp}.db"
    backup_filepath = Path(temp_dir) / backup_filename

    # Connect to live DB and backup safely
    con = sqlite3.connect(db_path)
    bck = sqlite3.connect(backup_filepath)
    with bck:
        con.backup(bck)
    bck.close()
    con.close()

    return str(backup_filepath), backup_filename

def backup_db_to_gdrive(db_path: str = "inventory.db"):
    """
    Backs up the SQLite database and uploads it to the configured Google Drive folder.
    """
    service, auth_type = get_drive_service()
    if not service:
        st.error("❌ Drive service authentication failed. Check Streamlit secrets.")
        return None

    folder_id = st.secrets.get("google_drive", {}).get("folder_id", None)
    if not folder_id:
        st.error("❌ 'folder_id' missing under [google_drive] in secrets.")
        return None

    backup_filepath = None
    try:
        # 1. Generate safe SQLite dump file
        backup_filepath, backup_filename = create_local_sqlite_dump(db_path)

        # 2. Prepare Google Drive metadata
        file_metadata = {
            'name': backup_filename,
            'parents': [folder_id]
        }

        # 3. Upload file
        media = MediaFileUpload(
            backup_filepath,
            mimetype='application/x-sqlite3',
            resumable=True
        )

        uploaded_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name',
            supportsAllDrives=True
        ).execute()

        file_id = uploaded_file.get('id')
        st.success(f"✅ Database backup uploaded successfully via {auth_type}! File ID: `{file_id}`")
        return file_id

    except Exception as e:
        st.error(f"❌ Backup upload failed ({auth_type}): {e}")
        return None
    finally:
        # Clean up temporary local backup file
        if backup_filepath and Path(backup_filepath).exists():
            Path(backup_filepath).unlink()
