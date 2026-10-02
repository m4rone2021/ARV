import streamlit as st
from views.physical_inventory import render_physical_inventory

st.set_page_config(page_title="Test physical_inventory", layout="wide")
render_physical_inventory("admin", "Admin")
