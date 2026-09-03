# views/dashboard.py
import sqlite3
import pandas as pd
import streamlit as st
import plotly.express as px
from database import get_db, init_db

def render_dashboard(user_name, user_role):
    st.title("📊 Executive Dashboard")
    st.caption("Real-time summary of current stock levels, category distributions, and alerts.")

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

    # Fetch master items summary from database
    try:
        with get_db() as conn:
            df = pd.read_sql_query("""
                SELECT id, item_name, category, unit, current_stock, min_threshold 
                FROM master_items 
                ORDER BY category ASC, item_name ASC
            """, conn)
            
            # Fetch total transactions count
            tx_df = pd.read_sql_query("SELECT COUNT(*) as total_tx FROM transactions", conn)
            total_tx_count = tx_df["total_tx"].iloc[0] if not tx_df.empty else 0

    except Exception as e:
        st.error(f"Error loading dashboard metrics: {e}")
        return

    # Calculate Summary Metrics
    total_items = len(df)
    low_stock_df = df[df["current_stock"] <= df["min_threshold"]] if not df.empty else pd.DataFrame()
    low_stock_count = len(low_stock_df)
    total_units_stocked = df["current_stock"].sum() if not df.empty else 0.0

    # -------------------------------------------------------------
    # 1. TOP METRICS CARDS
    # -------------------------------------------------------------
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(label="📦 Unique Items in Catalog", value=f"{total_items:,}")

    with col2:
        st.metric(
            label="⚠️ Low Stock Items", 
            value=f"{low_stock_count}", 
            delta=f"-{low_stock_count}" if low_stock_count > 0 else "Optimal",
            delta_color="inverse" if low_stock_count > 0 else "normal"
        )

    with col3:
        st.metric(label="📊 Total Quantity On-Hand", value=f"{total_units_stocked:,.1f}")

    with col4:
        st.metric(label="📜 Total Ledger Transactions", value=f"{total_tx_count:,}")

    st.divider()

    if df.empty:
        st.info("ℹ️ No items currently registered in the Master Catalog. Go to **Manage Master Items** to seed inventory.")
        return

    # -------------------------------------------------------------
    # 2. CATEGORY BREAKDOWN CHART & LOW STOCK HIGHLIGHTS
    # -------------------------------------------------------------
    chart_col, alert_col = st.columns([3, 2])

    with chart_col:
        st.subheader("📦 Available Stock by Site Category")
        cat_summary = df.groupby("category")["current_stock"].sum().reset_index()
        
        # Plotly Bar Chart
        fig = px.bar(
            cat_summary, 
            x="category", 
            y="current_stock", 
            labels={"category": "Site Category", "current_stock": "Total Available Stock"},
            text_auto=".1f",
            color="category",
            color_discrete_sequence=px.colors.qualitative.Bold
        )
        fig.update_layout(showlegend=False, xaxis_tickangle=-30, height=350, margin=dict(l=20, r=20, t=20, b=50))
        st.plotly_chart(fig, use_container_width=True)

    with alert_col:
        st.subheader("⚠️ Critical Low Stock Warnings")
        if not low_stock_df.empty:
            st.warning(f"Attention: {low_stock_count} item(s) are at or below their safety threshold!")
            
            low_stock_display = low_stock_df[["item_name", "category", "current_stock", "unit", "min_threshold"]].rename(columns={
                "item_name": "Item Description",
                "category": "Category",
                "current_stock": "Current",
                "unit": "Unit",
                "min_threshold": "Limit"
            })
            st.dataframe(low_stock_display, use_container_width=True, hide_index=True)
        else:
            st.success("✅ All stock items are currently above their minimum safety thresholds.")

    st.divider()

    # -------------------------------------------------------------
    # 3. CURRENT STOCKS AVAILABLE TABLE
    # -------------------------------------------------------------
    st.subheader("📋 Current Stock Levels Overview")

    col_filter1, col_filter2 = st.columns([1, 2])
    with col_filter1:
        cat_filter = st.selectbox("Filter Category", ["All Categories"] + categories, key="dash_cat_filter")
    with col_filter2:
        dash_search = st.text_input("🔍 Quick Search Item", placeholder="Type item name to filter...", key="dash_search")

    filtered_df = df.copy()

    if cat_filter != "All Categories":
        filtered_df = filtered_df[filtered_df["category"] == cat_filter]

    if dash_search.strip():
        filtered_df = filtered_df[filtered_df["item_name"].str.contains(dash_search.strip(), case=False, na=False)]

    if not filtered_df.empty:
        display_df = filtered_df.rename(columns={
            "id": "ID",
            "item_name": "Item Description",
            "category": "Category",
            "unit": "Unit",
            "current_stock": "Available Stock",
            "min_threshold": "Safety Limit"
        })

        # Highlight items low on stock in the table
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Available Stock": st.column_config.NumberColumn(
                    "Available Stock",
                    format="%.2f"
                )
            }
        )
    else:
        st.info("No matching stock items found.")
