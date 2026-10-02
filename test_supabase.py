import streamlit as st
from supabase import create_client, Client

@st.cache_resource
def get_supabase():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

st.title("🧪 Supabase Connection Test")

try:
    supabase: Client = get_supabase()
    st.success("✅ Connected to Supabase!")
    
    # Test: Fetch users
    response = supabase.table("users").select("*").execute()
    st.write("**Users in database:**")
    st.dataframe(response.data)
    
    st.info("✅ All systems go! Ready to migrate data.")
    
except Exception as e:
    st.error(f"❌ Error: {e}")
    st.write("Check your secrets.toml file and Supabase credentials")
