import io
import streamlit as st
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    """Authenticates using User OAuth Refresh Token from Streamlit Secrets."""
    try:
        if "gdrive_token" in st.secrets:
            token_info = dict(st.secrets["gdrive_token"])
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
            
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                
            return build('drive', 'v3', credentials=creds)
        else:
            st.error("❌ 'gdrive_token' block missing in Streamlit Secrets.")
            return None
    except Exception as e:
        st.error(f"❌ OAuth Auth Error: {e}")
        return None

def create_test_file(service):
    """Creates a sample test file in the user's Google Drive folder."""
    if not service:
        return None

    try:
        folder_id = st.secrets.get("google_drive", {}).get("folder_id", None)
        
        file_metadata = {
            'name': 'Project_Alpha_Specs.txt',
            'mimeType': 'text/plain'
        }
        
        if folder_id:
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
