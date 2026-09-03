# views/low_stock.py
import streamlit as st
import pandas as pd
from database import get_db

def render_low_stock():
    st.title("⚠️ Low Stock & Restock Alerts")
    st.caption("Monitor items running low on site to prioritize procurement and reordering.")

    with get_db() as conn:
        df_items = pd.read_sql_query(
            "SELECT item_name, category, unit, current_stock, min_threshold FROM master_items ORDER BY category ASC, item_name ASC", 
            conn
        )

    if df_items.empty:
        st.info("No master items configured yet. Go to 'Manage Master Items' to set up inventory items.")
        return

    # Filter items where current stock is less than or equal to minimum threshold
    df_low = df_items[df_items['current_stock'] <= df_items['min_threshold']].copy()

    col1, col2 = st.columns(2)
    col1.metric("Total Items Tracked", len(df_items))
    col2.metric("Items Needing Restock", len(df_low), delta_color="inverse")

    st.divider()

    if df_low.empty:
        st.success("✅ All stock levels are currently healthy! No items are below their minimum threshold.")
    else:
        st.subheader("🚨 Items At or Below Minimum Threshold")

        # Calculate shortage quantity
        df_low['shortage'] = df_low['min_threshold'] - df_low['current_stock']
        
        display_df = df_low.rename(columns={
            "item_name": "Item Name",
            "category": "Category",
            "unit": "Unit",
            "current_stock": "Current Stock",
            "min_threshold": "Min Threshold",
            "shortage": "Deficit Qty"
        })

        # Format numeric columns cleanly
        display_df['Current Stock'] = display_df['Current Stock'].apply(lambda x: f"{x:,.2f}".rstrip('0').rstrip('.'))
        display_df['Min Threshold'] = display_df['Min Threshold'].apply(lambda x: f"{x:,.2f}".rstrip('0').rstrip('.'))
        display_df['Deficit Qty'] = display_df['Deficit Qty'].apply(lambda x: f"{x:,.2f}".rstrip('0').rstrip('.'))

        st.dataframe(display_df, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("💡 Restock Summary by Category")

        low_cats = df_low['category'].unique()
        for cat in low_cats:
            cat_items = df_low[df_low['category'] == cat]
            st.markdown(f"**{cat.upper()}**")
            for _, item in cat_items.iterrows():
                st.markdown(
                    f"- **{item['item_name']}**: Current: `{item['current_stock']:,.2f} {item['unit']}` "
                    f"| Minimum Needed: `{item['min_threshold']:,.2f} {item['unit']}`"
                )
