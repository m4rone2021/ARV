import streamlit as st
from tests.setup_test_drive import get_drive_service, create_test_file

st.title("Google Drive Integration Test Panel")

st.sidebar.header("Admin / Test Tools")

# Button to trigger test file creation
if st.sidebar.button("🧪 Generate Test File in Google Drive"):
    with st.spinner("Connecting to Google Drive and uploading test file..."):
        try:
            # 1. Initialize Drive service
            drive_service = get_drive_service()
            
            # 2. Create and upload the file
            file_id = create_test_file(drive_service)
            
            if file_id:
                st.success("✅ File `Project_Alpha_Specs.txt` successfully generated in Google Drive!")
                st.info(f"File ID: `{file_id}`")
            else:
                st.error("❌ Failed to create file. Check server terminal logs for details.")
                
        except Exception as e:
            st.error(f"❌ Authentication or API error: {e}")

# Divider before main app code
st.markdown("---")
