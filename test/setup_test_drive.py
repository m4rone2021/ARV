import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

def create_test_file(service):
    """Creates a sample test document in Google Drive for search/retrieval testing."""
    
    # 1. Define file metadata
    file_metadata = {
        'name': 'Project_Alpha_Specs.txt',
        'mimeType': 'text/plain',
        'description': 'Integration Test File'
    }

    # 2. Define the test content with unique keywords
    file_content = (
        "PROJECT ALPHA SPECIFICATIONS\n"
        "----------------------------\n"
        "Project Alpha budget is $50,000 using vendor ACME Corp.\n"
        "Key Deliverable: Automated inventory sync module.\n"
        "Target Date: Q4 2026."
    )

    # 3. Prepare media stream
    media = MediaIoBaseUpload(
        io.BytesIO(file_content.encode('utf-8')),
        mimetype='text/plain',
        resumable=True
    )

    # 4. Execute upload
    try:
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()

        print(f"✅ Test file created successfully!")
        print(f"File ID: {file.get('id')}")
        print(f"File Name: {file.get('name')}")
        print(f"Drive Link: {file.get('webViewLink')}")
        return file.get('id')

    except Exception as e:
        print(f"❌ Error creating test file: {e}")
        return None

# Usage example (assuming authenticated 'service' object):
# file_id = create_test_file(drive_service)
