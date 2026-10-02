import streamlit as st
from views.audit_log import render_audit_log

st.set_page_config(page_title="Test audit_log", layout="wide")
render_audit_log("admin", "Admin")
