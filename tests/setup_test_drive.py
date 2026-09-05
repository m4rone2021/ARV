import io
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCOPES = ['https://www.googleapis.com/auth/drive']

def clean_private_key(key_str: str) -> str:
    """Sanitizes raw private key strings into valid multi-line PEM format."""
    if not key_str:
        return key_str
    
    # Strip quotes if accidental double wrapping occurred in secrets
    key_str = key_str.strip('\'"')
    
    # Replace literal '\\n' or '\n' characters with actual line breaks
    key_str = key_str.replace('\\n', '\n')
    
    # Ensure correct PEM boundaries
    if "-----BEGIN PRIVATE KEY-----" in key_str and not key_str.startswith("-----BEGIN PRIVATE KEY-----"):
        key_str = "-----BEGIN PRIVATE KEY-----" + key_str.split("-----BEGIN PRIVATE KEY-----")[-1]
        
    return key_str

def get_drive_service():
    """Authenticates using GCP Service Account secrets on Streamlit Cloud."""
    try:
        if "gcp_service_account" in st.secrets:
            # Copy secrets dict to avoid modifying in-memory config directly
            creds_dict = dict(st.secrets["gcp_service_account"])
            
            # Clean and re-format the private key for OpenSSL
            if "private_key" in creds_dict:
                creds_dict["private_key"] = clean_private_key(creds_dict["private_key"])

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
