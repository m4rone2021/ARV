import streamlit as st
from views.dashboard import render_dashboard

st.set_page_config(page_title="Test dashboard", layout="wide")
render_dashboard("admin", "Admin")
