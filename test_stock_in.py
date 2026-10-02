import streamlit as st
from views.stock_in import render_stock_in

st.set_page_config(page_title="Test stock_in", layout="wide")
render_stock_in("admin", "Admin")
