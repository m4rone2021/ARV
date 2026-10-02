import streamlit as st
from views.reminders import render_reminders

st.set_page_config(page_title="Test reminders", layout="wide")
render_reminders("admin", "Admin")
