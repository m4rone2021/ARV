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
    Dual-Auth Authentication Strategy:
    1. Primary: Tries GCP Service Account.
    2. Fallback: Tries User OAuth Refresh Token if Service Account is unavailable.
    """
    # 1. PRIMARY METHOD: GCP Service Account
    if "gcp_service_account" in st.secrets:
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict:
                creds_dict["private_key"] = clean_private_key(creds_dict["private_key"])

            creds = service_account.Credentials.from_service_account_info(
                creds_dict, 
                scopes=SCOPES
            )
            service = build('drive', 'v3', credentials=creds)
            return service, "Service Account"
        except Exception as e:
            st.warning(f"⚠️ Service Account Auth failed ({e}). Trying OAuth fallback...")

    # 2. FALLBACK METHOD: User OAuth Refresh Token
    if "gdrive_token" in st.secrets:
        try:
            token_info = dict(st.secrets["gdrive_token"])
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
            
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                
            service = build('drive', 'v3', credentials=creds)
            return service, "OAuth Token"
        except Exception as e:
            st.error(f"❌ OAuth Fallback Auth Error: {e}")
            return None, None

    st.error("❌ No valid authentication secrets found ([gcp_service_account] or [gdrive_token]).")
    return None, None

def create_test_file(service, auth_type="Service Account"):
    """Creates a sample test file in the specified Google Drive folder."""
    if not service:
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

        # supportsAllDrives=True bypasses shared drive/folder quota errors
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()

        return file.get('id')
    except Exception as e:
        # Handles 403 Storage Quota issue specifically for Service Accounts on personal drives
        if "storageQuotaExceeded" in str(e) and auth_type == "Service Account" and "gdrive_token" in st.secrets:
            st.warning("⚠️ Service Account blocked by personal drive quota limits. Attempting OAuth Fallback...")
            fallback_service, _ = get_drive_service_oauth_only()
            return create_test_file(fallback_service, auth_type="OAuth Token (Fallback)")
        else:
            st.error(f"❌ Drive File Creation Error ({auth_type}): {e}")
            return None

def get_drive_service_oauth_only():
    """Dedicated helper to force OAuth fallback when Service Account hits quota limits."""
    try:
        token_info = dict(st.secrets["gdrive_token"])
        creds = Credentials.from_authorized_user_info(token_info, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build('drive', 'v3', credentials=creds), "OAuth Token"
    except Exception as e:
        st.error(f"❌ OAuth Auth Error: {e}")
        return None, None
