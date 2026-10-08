"""Top-level water system view: sidebar, routing, admin screen."""
import streamlit as st

from watersystem import config as cfg, lookups
from watersystem.screens import manage_items, pending_lookups


def render(user_name: str, is_admin: bool):
    """Entry point called from app.py when active_domain == 'watersystem'."""
    st.sidebar.markdown(f"### 💧 {cfg.DISPLAY_NAME}")

    menu = {
        "📦 Manage Items": "items",
    }
    if is_admin:
        pending_count = lookups.count_pending()
        badge = f" ({pending_count})" if pending_count else ""
        menu[f"⚙️ Pending Lookups{badge}"] = "pending"

    picked = st.sidebar.radio(
        "Water System Menu",
        list(menu.keys()),
        label_visibility="collapsed",
        key="_ws_menu",
    )
    choice = menu[picked]

    st.sidebar.divider()

    if choice == "items":
        manage_items.render(user_name, is_admin)
    elif choice == "pending":
        pending_lookups.render(user_name)