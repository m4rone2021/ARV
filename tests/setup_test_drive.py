import io
import streamlit as st
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

SCOPES = ['https://www.googleapis.com/auth/drive']

def clean_private_key(key_str: str) -> str:
    """Sanitizes raw private key strings into valid multi-line PEM format."""
    if not key_str:
        return key_str
    
    key_str = key_str.strip('\'"')
    key_str = key_str.replace('\\n', '\n')
    
    if "-----BEGIN PRIVATE KEY-----" in key_str and not key_str.startswith("-----BEGIN PRIVATE KEY-----"):
        key_str = "-----BEGIN PRIVATE KEY-----" + key_str.split("-----BEGIN PRIVATE KEY-----")[-1]
        
    return key_str

def get_drive_service():
    """
    Returns (service_object, auth_type_string).
    """
    # 1. PRIMARY: GCP Service Account
    if "gcp_service_account" in st.secrets:
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict:
                creds_dict["private_key"] = clean_private_key(creds_dict["private_key"])

            creds = service_account.Credentials.from_service_account_info(
                creds_dict, 
                scopes=SCOPES
            )
            return build('drive', 'v3', credentials=creds), "Service Account"
        except Exception as e:
            st.warning(f"⚠️ Service Account Auth failed: {e}")

    # 2. FALLBACK: User OAuth Refresh Token
    if "gdrive_token" in st.secrets:
        try:
            token_info = dict(st.secrets["gdrive_token"])
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
            
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                
            return build('drive', 'v3', credentials=creds), "OAuth Token"
        except Exception as e:
            st.error(f"❌ OAuth Fallback Auth Error: {e}")

    return None, None

def create_test_file(service_arg=None):
    """Creates a sample test file in the specified Google Drive folder."""
    # Obtain service and auth label safely
    if service_arg is None or isinstance(service_arg, tuple):
        service, auth_type = get_drive_service()
    else:
        service, auth_type = service_arg, "Service Account"

    if not service:
        st.error("❌ Drive service initialization failed.")
        return None

    try:
        folder_id = st.secrets.get("google_drive", {}).get("folder_id", None)
        
        if not folder_id:
            st.error("❌ 'folder_id' missing under [google_drive] in Streamlit Secrets.")
            return None

        file_metadata = {
            'name': 'Project_Alpha_Specs.txt',
            'mimeType': 'text/plain',
            'parents': [folder_id]
        }

        file_content = f"PROJECT ALPHA SPECIFICATIONS\n----------------------------\nUploaded via {auth_type}."
        media = MediaIoBaseUpload(
            io.BytesIO(file_content.encode('utf-8')),
            mimetype='text/plain',
            resumable=True
        )

        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()

        return file.get('id')
    except Exception as e:
        st.error(f"❌ Drive File Creation Error ({auth_type}): {e}")
        return None
