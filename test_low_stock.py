import streamlit as st
from views.low_stock import render_low_stock

st.set_page_config(page_title="Test low_stock", layout="wide")
render_low_stock("admin", "Admin")
