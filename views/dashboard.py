# views/dashboard.py
import streamlit as st
import pandas as pd
from database import get_db

def render_dashboard():
    st.title("📊 Inventory Overview Dashboard")
    
    with get_db() as conn:
        df_items = pd.read_sql_query("SELECT * FROM master_items ORDER BY category ASC, item_name ASC", conn)
        df_tx = pd.read_sql_query("SELECT * FROM transactions ORDER BY id DESC LIMIT 10", conn)

    # Top summary metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Master Items", len(df_items))
    
    low_stock_cnt = len(df_items[df_items['current_stock'] <= df_items['min_threshold']]) if not df_items.empty else 0
    col2.metric("Low Stock Alerts", low_stock_cnt, delta_color="inverse")
    
    total_tx = len(df_tx) if not df_tx.empty else 0
    col3.metric("Recent Transactions Logged", total_tx)

    st.divider()
    st.subheader("📦 Available Inventory & Physical Audit Balance")

    if df_items.empty:
        st.info("No master items configured yet. Go to 'Manage Master Items' to add items.")
    else:
        categories = df_items['category'].unique()

        for cat in categories:
            st.markdown(f"### **{cat.upper()}**")
            cat_df = df_items[df_items['category'] == cat].copy()
            
            display_rows = []
            for _, row in cat_df.iterrows():
                stock = row['current_stock']
                min_t = row['min_threshold']
                status = "⚠️ Lacking / Low Stock" if stock <= min_t else "✅ Normal / Surplus Available"
                
                display_rows.append({
                    "Item Name": row['item_name'],
                    "Unit": row['unit'],
                    "Current Actual Stock": f"{stock:,.2f}".rstrip('0').rstrip('.'),
                    "Min Threshold": f"{min_t:,.2f}".rstrip('0').rstrip('.'),
                    "Physical Audit Variance / Status": status
                })
            
            st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
            st.markdown("<br>", unsafe_allow_html=True)

    st.divider()
    st.subheader("⏱️ Recent Activity (Stock IN / OUT / Adjustments)")
    if not df_tx.empty:
        recent_display = df_tx[['timestamp', 'item_name', 'type', 'quantity', 'user_name', 'project_name', 'remarks', 'edit_status']].copy()
        recent_display.columns = ['Timestamp', 'Item Name', 'Type', 'Qty', 'Logged By', 'Project / Destination', 'Remarks / Details', 'Status']
        st.dataframe(recent_display, use_container_width=True, hide_index=True)
    else:
        st.info("No transaction activity recorded yet.")
