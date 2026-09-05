import io
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    """Authenticates using GCP Service Account secrets on Streamlit Cloud."""
    try:
        if "gcp_service_account" in st.secrets:
            # Load credentials directly from Streamlit secrets
            creds_dict = dict(st.secrets["gcp_service_account"])
            
            # Handle escaped newlines in private key if necessary
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

            creds = service_account.Credentials.from_service_account_info(
                creds_dict, 
                scopes=SCOPES
            )
            return build('drive', 'v3', credentials=creds)
        else:
            st.error("❌ 'gcp_service_account' block missing in Streamlit Secrets.")
            return None
    except Exception as e:
        st.error(f"❌ Service Account Auth Error: {e}")
        return None

def create_test_file(service):
    """Creates a sample test file in the specified Google Drive folder."""
    if not service:
        return None

    try:
        # Retrieve target folder ID from secrets if available
        folder_id = st.secrets.get("google_drive", {}).get("folder_id", None)
        
        file_metadata = {
            'name': 'Project_Alpha_Specs.txt',
            'mimeType': 'text/plain'
        }
        
        # Target specific folder if defined
        if folder_id and folder_id != "your-folder-id":
            file_metadata['parents'] = [folder_id]

        file_content = "PROJECT ALPHA SPECIFICATIONS\n----------------------------\nInventory sync integration test."
        media = MediaIoBaseUpload(
            io.BytesIO(file_content.encode('utf-8')),
            mimetype='text/plain',
            resumable=True
        )

        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()

        return file.get('id')
    except Exception as e:
        st.error(f"❌ Drive File Creation Error: {e}")
        return None
