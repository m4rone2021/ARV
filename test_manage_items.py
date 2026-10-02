import streamlit as st
from views.manage_items import render_manage_items

st.set_page_config(page_title="Test manage_items", layout="wide")
render_manage_items("admin", "Admin")
