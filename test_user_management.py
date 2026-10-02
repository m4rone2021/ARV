import streamlit as st
from views.user_management import render_user_management

st.set_page_config(page_title="Test user_management", layout="wide")
render_user_management("admin", "Admin")
