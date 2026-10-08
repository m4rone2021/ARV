import pandas as pd
import streamlit as st

from database import sb


def render_low_stock(user_name: str, user_role: str):
    st.title("Low Stock Alerts")
    st.caption(
        "Monitor items below minimum safety thresholds and queue restock orders based on effective stock."
    )

    # Fetch all items — compute effective stock in Python for flexibility
    try:
        res = (
            sb()
            .table("master_items")
            .select("id, item_name, category, unit, current_stock, reserved_stock, min_threshold, remarks")
            .eq("warehouse", "construction")
            .execute()
        )
        df = pd.DataFrame(res.data or [])
    except Exception as e:
        st.error(f"Error loading low stock alerts: {e}")
        return

    if df.empty:
        st.info("ℹ️ No inventory items found in the master catalog.")
        return

    # Compute effective stock + shortage
    df["current_stock"] = df["current_stock"].fillna(0.0)
    df["reserved_stock"] = df["reserved_stock"].fillna(0.0)
    df["min_threshold"] = df["min_threshold"].fillna(0.0)
    df["effective_stock"] = df["current_stock"] - df["reserved_stock"]
    df["Shortage Quantity"] = (df["min_threshold"] - df["effective_stock"]).clip(lower=0)

    low_stock_df = df[df["effective_stock"] <= df["min_threshold"]].copy()

    # KPI metrics
    m1, m2, m3 = st.columns([1, 1, 1])
    m1.metric("Total Items", len(df))
    m2.metric("Low Stock", len(low_stock_df), delta=-len(low_stock_df), delta_color="inverse")
    critical_count = len(low_stock_df[low_stock_df["effective_stock"] <= 0])
    m3.metric("Critical", critical_count, delta=-critical_count, delta_color="inverse")

    if low_stock_df.empty:
        st.success(
            "✅ Great news! All inventory items are currently above their minimum safety thresholds."
        )
        return

    low_stock_df = low_stock_df.sort_values(by="Shortage Quantity", ascending=False)

    st.warning(
        f"⚠️ **Attention Required:** There are **{len(low_stock_df)}** item(s) running low on available stock."
    )

    df_display = low_stock_df.rename(
        columns={
            "id": "ID",
            "item_name": "Item Description",
            "category": "Category",
            "unit": "Unit",
            "current_stock": "Physical Stock",
            "reserved_stock": "Reserved",
            "effective_stock": "Available Stock",
            "min_threshold": "Min Threshold",
            "remarks": "Storage / Remarks",
        }
    )

    view_mode = st.radio(
        "Display View Mode",
        ["Cards (Mobile)", "Full Table"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if view_mode == "Cards (Mobile)":
        for _, item in df_display.iterrows():
            is_critical = item["Available Stock"] <= 0
            badge = "🔴 CRITICAL" if is_critical else "🟡 LOW"
            with st.expander(f"{badge} {item['Item Description']} ({item['Category']})"):
                st.markdown(
                    f"**Available:** `{item['Available Stock']:.2f} {item['Unit']}` (Min: `{item['Min Threshold']:.2f}`)"
                )
                st.markdown(f"**Shortage Deficit:** `{item['Shortage Quantity']:.2f} {item['Unit']}`")
                st.caption(f"Physical: {item['Physical Stock']:.2f} | Reserved: {item['Reserved']:.2f}")
                if item["Storage / Remarks"]:
                    st.caption(f"Remarks: {item['Storage / Remarks']}")
    else:
        st.dataframe(
            df_display[
                [
                    "ID",
                    "Item Description",
                    "Category",
                    "Unit",
                    "Physical Stock",
                    "Reserved",
                    "Available Stock",
                    "Min Threshold",
                    "Shortage Quantity",
                    "Storage / Remarks",
                ]
            ],
            width='stretch',
            hide_index=True,
            column_config={
                "Physical Stock": st.column_config.NumberColumn(format="%.2f"),
                "Reserved": st.column_config.NumberColumn(format="%.2f"),
                "Available Stock": st.column_config.NumberColumn(format="%.2f"),
                "Shortage Quantity": st.column_config.NumberColumn(format="%.2f"),
                "Min Threshold": st.column_config.NumberColumn(format="%.2f"),
            },
        )

    st.divider()

    # Quick reorder form
    st.subheader("📅 Schedule Restock Delivery")

    item_options = low_stock_df["item_name"].tolist()
    selected_item = st.selectbox("Select Low Stock Item", item_options, key="low_stock_selector")

    selected_info = low_stock_df[low_stock_df["item_name"] == selected_item].iloc[0]
    suggested_qty = float(max(1.0, selected_info["Shortage Quantity"]))

    with st.form("quick_schedule_form", clear_on_submit=True):
        expected_qty = st.number_input(
            f"Expected Restock Quantity ({selected_info['unit']})*",
            min_value=0.01,
            value=suggested_qty,
            step=1.0,
            format="%.2f",
        )
        supplier = st.text_input("Supplier / Source", placeholder="e.g., Prime Steel Corp")
        expected_date = st.date_input("Expected Delivery Date*")
        schedule_notes = st.text_input("Delivery Notes", placeholder="e.g., Urgent site restock")

        submit_schedule = st.form_submit_button("➕ Schedule Delivery", width='stretch')

        if submit_schedule:
            try:
                sb().table("deliveries").insert({
                    "item_name": selected_item,
                    "expected_quantity": float(expected_qty),
                    "unit": selected_info["unit"],
                    "supplier": supplier.strip() or None,
                    "expected_date": str(expected_date),
                    "status": "Pending",
                    "notes": schedule_notes.strip() or None,
                    "created_by": user_name or "System",
                    "warehouse": "construction",
                }).execute()

                st.toast(f"✅ Delivery scheduled for {selected_item}!", icon="📅")
                st.success(
                    f"Successfully logged pending delivery for **{selected_item}** "
                    f"({expected_qty} {selected_info['unit']}) arriving on {expected_date}."
                )
            except Exception as e:
                st.error(f"Failed to record delivery schedule: {e}")
