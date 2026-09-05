import io
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# Use the full drive scope so the file is visible everywhere in Drive
SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    """Handles Google OAuth authentication and returns a service client."""
    creds = None
    # Delete token.json manually if you recently changed SCOPES
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return build('drive', 'v3', credentials=creds)

def create_test_file(service):
    """Creates a sample test document in Google Drive for search/retrieval testing."""
    file_metadata = {
        'name': 'Project_Alpha_Specs.txt',
        'mimeType': 'text/plain',
        'description': 'Integration Test File'
    }

    file_content = (
        "PROJECT ALPHA SPECIFICATIONS\n"
        "----------------------------\n"
        "Project Alpha budget is $50,000 using vendor ACME Corp.\n"
        "Key Deliverable: Automated inventory sync module.\n"
        "Target Date: Q4 2026."
    )

    media = MediaIoBaseUpload(
        io.BytesIO(file_content.encode('utf-8')),
        mimetype='text/plain',
        resumable=True
    )

    try:
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()

        print(f"✅ Test file upload call finished!")
        print(f"File ID: {file.get('id')}")
        print(f"Drive Link: {file.get('webViewLink')}\n")
        return file.get('id')

    except Exception as e:
        print(f"❌ Error creating test file: {e}\n")
        return None

if __name__ == "__main__":
    # 1. Initialize Drive client
    drive_service = get_drive_service()
    
    # 2. Upload the test file
    create_test_file(drive_service)

    # 3. VERIFY IF THE FILE IS LISTED VIA API
    print("🔍 Checking API index for the file...")
    results = drive_service.files().list(
        q="name = 'Project_Alpha_Specs.txt' and trashed = false",
        fields="files(id, name, parents, owners)"
    ).execute()

    files = results.get('files', [])
    if files:
        print(f"Found {len(files)} file(s):")
        for f in files:
            owner_email = f.get('owners')[0].get('emailAddress') if f.get('owners') else 'Unknown'
            print(f"ID: {f['id']} | Name: {f['name']} | Owner: {owner_email}")
    else:
        print("❌ No file found via API check.")
