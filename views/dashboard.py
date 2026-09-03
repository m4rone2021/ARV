# views/dashboard.py
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db

def render_dashboard(user_name, user_role):
    st.title("📊 Inventory Dashboard")
    st.caption(f"Welcome back, **{user_name}** ({user_role})")

    # Fetch inventory metrics
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Total Master Items
        cursor.execute("SELECT COUNT(*) FROM master_items")
        total_items = cursor.fetchone()[0] or 0

        # 2. Total Low Stock Items
        cursor.execute("SELECT COUNT(*) FROM master_items WHERE current_stock <= min_threshold")
        low_stock_count = cursor.fetchone()[0] or 0

        # 3. Total Transactions Logged
        cursor.execute("SELECT COUNT(*) FROM transactions")
        total_tx = cursor.fetchone()[0] or 0

    # Display Top Metric Cards
    col1, col2, col3 = st.columns(3)
    col1.metric("📦 Total Master Items", total_items)
    col2.metric("⚠️ Low Stock Alerts", low_stock_count, delta_color="inverse")
    col3.metric("📝 Total Transactions", total_tx)

    st.divider()

    # Low Stock Items Warning Table
    st.subheader("⚠️ Low Stock Items Warning")
    with get_db() as conn:
        df_low_stock = pd.read_sql_query("""
            SELECT item_name, category, unit, current_stock, min_threshold 
            FROM master_items 
            WHERE current_stock <= min_threshold 
            ORDER BY current_stock ASC
        """, conn)

    if not df_low_stock.empty:
        df_low_stock = df_low_stock.rename(columns={
            "item_name": "Item Name",
            "category": "Category",
            "unit": "Unit",
            "current_stock": "Current Stock",
            "min_threshold": "Threshold Limit"
        })
        st.dataframe(df_low_stock, use_container_width=True, hide_index=True)
    else:
        st.success("✅ All stock levels are above low-stock threshold limits.")

    st.divider()

    # Recent Transactions Ledger
    st.subheader("📑 Recent Inventory Activity")
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, type, item_name, quantity, user_name, remarks 
                FROM transactions 
                ORDER BY id DESC LIMIT 10
            """)
            rows = cursor.fetchall()

        if rows:
            df_recent = pd.DataFrame(rows, columns=[
                "Date & Time", "Type", "Item Name", "Quantity", "User", "Remarks"
            ])
            st.dataframe(df_recent, use_container_width=True, hide_index=True)
        else:
            st.info("No transaction records logged yet.")
    except sqlite3.OperationalError:
        st.info("No transaction activity found. Start by adding items or logging Stock IN/OUT.")
