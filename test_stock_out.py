import streamlit as st
from views.stock_out import render_stock_out

st.set_page_config(page_title="Test stock_out", layout="wide")
render_stock_out("admin", "Admin")
