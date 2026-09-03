# views/manage_items.py
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db, init_db

def render_manage_items(user_name, user_role):
    st.title("📦 Master Items Catalog")
    st.caption("Read-only view of current master stock items and site categories.")

    # Ensure database schema exists
    init_db()

    categories = st.session_state.get("categories", [
        "Fuel & Oils",
        "Construction Materials",
        "Steel / Rebar",
        "Nails & Fasteners",
        "Cutting & Grinding Consumables",
        "Welding Supplies & PPE",
        "General Site Supplies"
    ])

    # -------------------------------------------------------------
    # MASTER CATALOG READ-ONLY VIEW
    # -------------------------------------------------------------
    # Filtering Controls
    col_f1, col_f2 = st.columns([1, 2])
    with col_f1:
        filter_cat = st.selectbox("Filter by Category", ["All Categories"] + categories)
    with col_f2:
        search_query = st.text_input("🔍 Search Item Name", placeholder="Type item name to filter...")

    # Build SQL Query dynamically based on search filters
    query = "SELECT id, item_name, category, unit, current_stock, min_threshold, remarks FROM master_items WHERE 1=1"
    params = []

    if filter_cat != "All Categories":
        query += " AND category = ?"
        params.append(filter_cat)

    if search_query.strip():
        query += " AND item_name LIKE ?"
        params.append(f"%{search_query.strip()}%")

    query += " ORDER BY category ASC, item_name ASC"

    try:
        with get_db() as conn:
            df_items = pd.read_sql_query(query, conn, params=params)

        if not df_items.empty:
            df_display = df_items.rename(columns={
                "id": "ID",
                "item_name": "Item Name / Description",
                "category": "Category",
                "unit": "Unit",
                "current_stock": "Current Stock",
                "min_threshold": "Low Stock Limit",
                "remarks": "Remarks"
            })
            
            # Display master items table
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            st.caption(f"Showing {len(df_display)} item(s) in catalog.")
        else:
            st.info("No items found matching the selected filters.")

    except Exception as e:
        st.error(f"Database error while loading inventory items: {e}")
