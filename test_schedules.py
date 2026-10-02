import streamlit as st
from views.schedules import render_schedules

st.set_page_config(page_title="Test schedules", layout="wide")
render_schedules("admin", "Admin")
