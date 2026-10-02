import streamlit as st
from views.edit_void import render_edit_void

st.set_page_config(page_title="Test edit_void", layout="wide")
render_edit_void("admin", "Admin")
