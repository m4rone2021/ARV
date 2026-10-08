"""Water system low stock alerts — filtered to warehouse='watersystem'."""
import pandas as pd
import streamlit as st

from database import sb
from watersystem import config as cfg


def render(user_name: str, is_admin: bool):
    st.title("⚠️ Water System — Low Stock Alerts")
    st.caption("Monitor water system items below minimum safety thresholds.")

    try:
        res = (
            sb().table("master_items")
            .select("id, item_name, category, unit, current_stock, reserved_stock, min_threshold, remarks")
            .eq("warehouse", cfg.WAREHOUSE)
            .execute()
        )
        df = pd.DataFrame(res.data or [])
    except Exception as e:
        st.error(f"Error loading water items: {e}")
        return

    if df.empty:
        st.info("ℹ️ No water system items yet.")
        return

    df["current_stock"] = df["current_stock"].fillna(0.0)
    df["reserved_stock"] = df["reserved_stock"].fillna(0.0)
    df["min_threshold"] = df["min_threshold"].fillna(0.0)
    df["effective_stock"] = df["current_stock"] - df["reserved_stock"]
    df["Shortage Quantity"] = (df["min_threshold"] - df["effective_stock"]).clip(lower=0)

    low_stock_df = df[df["effective_stock"] <= df["min_threshold"]].copy()

    m1, m2, m3 = st.columns([1, 1, 1])
    m1.metric("Total Items", len(df))
    m2.metric("Low Stock", len(low_stock_df), delta=-len(low_stock_df), delta_color="inverse")
    critical_count = len(low_stock_df[low_stock_df["effective_stock"] <= 0])
    m3.metric("Critical", critical_count, delta=-critical_count, delta_color="inverse")

    if low_stock_df.empty:
        st.success("✅ All water system items are above their minimum thresholds.")
        return

    low_stock_df = low_stock_df.sort_values(by="Shortage Quantity", ascending=False)

    st.warning(f"⚠️ **{len(low_stock_df)}** water item(s) running low.")

    df_display = low_stock_df.rename(columns={
        "id": "ID", "item_name": "Item Description", "category": "Category",
        "unit": "Unit", "current_stock": "Physical Stock",
        "reserved_stock": "Reserved", "effective_stock": "Available Stock",
        "min_threshold": "Min Threshold", "remarks": "Storage / Remarks",
    })

    view_mode = st.radio(
        "Display View Mode", ["Cards (Mobile)", "Full Table"],
        horizontal=True, label_visibility="collapsed", key="_wsls_mode",
    )

    if view_mode == "Cards (Mobile)":
        for _, item in df_display.iterrows():
            is_critical = item["Available Stock"] <= 0
            badge = "🔴 CRITICAL" if is_critical else "🟡 LOW"
            with st.expander(f"{badge} {item['Item Description']} ({item['Category']})"):
                st.markdown(f"**Available:** `{item['Available Stock']:.2f} {item['Unit']}` (Min: `{item['Min Threshold']:.2f}`)")
                st.markdown(f"**Shortage Deficit:** `{item['Shortage Quantity']:.2f} {item['Unit']}`")
                st.caption(f"Physical: {item['Physical Stock']:.2f} | Reserved: {item['Reserved']:.2f}")
                if item["Storage / Remarks"]:
                    st.caption(f"Remarks: {item['Storage / Remarks']}")
    else:
        st.dataframe(
            df_display[
                ["ID", "Item Description", "Category", "Unit",
                 "Physical Stock", "Reserved", "Available Stock",
                 "Min Threshold", "Shortage Quantity", "Storage / Remarks"]
            ],
            width="stretch", hide_index=True,
            column_config={
                "Physical Stock": st.column_config.NumberColumn(format="%.2f"),
                "Reserved": st.column_config.NumberColumn(format="%.2f"),
                "Available Stock": st.column_config.NumberColumn(format="%.2f"),
                "Shortage Quantity": st.column_config.NumberColumn(format="%.2f"),
                "Min Threshold": st.column_config.NumberColumn(format="%.2f"),
            },
        )