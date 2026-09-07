import pandas as pd
import streamlit as st
from datetime import datetime, date

# Set page configuration for mobile responsiveness
st.set_page_config(page_title="Deliveries Dashboard", layout="wide")

# Mock function to compute remaining days
def calculate_days_left(due_date_str):
    try:
        due_date = datetime.strptime(str(due_date_str), "%Y-%m-%d").date()
        today = date.today()
        diff = (due_date - today).days
        if diff < 0:
            return (diff, f"⚠️ Overdue ({abs(diff)}d)")
        elif diff == 0:
            return (diff, "⚡ Due Today")
        else:
            return (diff, f"⏳ {diff} days left")
    except Exception:
        return (9999, "Unknown")

# Sample Data Generation
@st.cache_data
def load_sample_data():
    return pd.DataFrame([
        {
            "due_date": "2026-09-10",
            "item_name": "Steel Beams 20ft",
            "project_name": "Site Alpha",
            "quantity": 15.0,
            "supplier": "BuildCorp",
            "requestor": "john_doe",
            "created_by": "john_doe"
        },
        {
            "due_date": "2026-09-05",
            "item_name": "Portland Cement Bags",
            "project_name": "Site Beta",
            "quantity": 100.0,
            "supplier": "Concrete Co.",
            "requestor": "jane_smith",
            "created_by": "admin"
        },
        {
            "due_date": "2026-09-15",
            "item_name": "Copper Wiring Spools",
            "project_name": "Site Alpha",
            "quantity": 8.0,
            "supplier": "Electro Supplies",
            "requestor": "john_doe",
            "created_by": "jane_smith"
        },
        {
            "due_date": "2026-09-07",
            "item_name": "Safety Helmets",
            "project_name": "Site Gamma",
            "quantity": 50.0,
            "supplier": "SafeGear Ltd",
            "requestor": "alex_gear",
            "created_by": "alex_gear"
        }
    ])

# Application State Setup
clean_user = "john_doe"
deliveries_df = load_sample_data()

# Main Application Layout
st.title("📦 Logistics & Procurement Tracker")

# ---------------------------------------------------------
# 2. Scheduled Deliveries Log
# ---------------------------------------------------------
st.subheader("🚚 Scheduled Deliveries Log")

if not deliveries_df.empty:

    # UI Filter & Sort Controls optimized for Mobile Viewports
    filter_col, sort_col, order_col = st.columns([2, 2, 1])

    with filter_col:
        delivery_view_mode = st.radio(
            "Filter View",
            options=["All Deliveries", f"My Deliveries ({clean_user})"],
            index=0,
            key="delivery_filter_radio",
            horizontal=True,
        )

    # Apply User Filtering
    if delivery_view_mode == f"My Deliveries ({clean_user})":
        filtered_del_df = deliveries_df[
            (deliveries_df["requestor"].astype(str).str.lower() == clean_user.lower())
            | (deliveries_df["created_by"].astype(str).str.lower() == clean_user.lower())
        ].copy()
    else:
        filtered_del_df = deliveries_df.copy()

    if not filtered_del_df.empty:
        # Parse target dates
        parsed_del_dates = filtered_del_df["due_date"].apply(calculate_days_left)
        filtered_del_df["days_left_num"] = [d[0] for d in parsed_del_dates]
        filtered_del_df["days_left_str"] = [d[1] for d in parsed_del_dates]

        # Mobile-Friendly Sorting Inputs
        with sort_col:
            sort_field = st.selectbox(
                "Sort By",
                options=[
                    "due_date",
                    "item_name",
                    "project_name",
                    "quantity",
                    "supplier",
                ],
                format_func=lambda x: {
                    "due_date": "Due Date",
                    "item_name": "Item Description",
                    "project_name": "Project",
                    "quantity": "Quantity",
                    "supplier": "Supplier",
                }.get(x, x),
                key="delivery_sort_field",
            )

        with order_col:
            sort_order = st.radio(
                "Order",
                options=["Asc", "Desc"],
                horizontal=True,
                key="delivery_sort_order",
            )

        # Perform sorting directly on the DataFrame
        is_ascending = (sort_order == "Asc")
        filtered_del_df = filtered_del_df.sort_values(
            by=sort_field, ascending=is_ascending
        )

        st.caption(
            f"Sorted by **{sort_field.replace('_', ' ').title()}** ({'Ascending' if is_ascending else 'Descending'})"
        )

        # Format Due Date for Display
        filtered_del_df["Due Date"] = filtered_del_df["due_date"].apply(
            lambda d: f"**{d}**"
        )

        display_log = filtered_del_df[
            [
                "Due Date",
                "days_left_str",
                "project_name",
                "item_name",
                "quantity",
                "supplier",
                "requestor",
                "created_by",
            ]
        ].rename(
            columns={
                "days_left_str": "Status",
                "project_name": "Project",
                "item_name": "Item Description",
                "quantity": "Qty",
                "supplier": "Supplier / Vendor",
                "requestor": "Requestor",
                "created_by": "Created By (Access)",
            }
        )

        # Dynamic key forces Streamlit to re-render component state on touch devices
        table_key = f"del_tbl_{delivery_view_mode}_{sort_field}_{sort_order}"

        st.dataframe(
            display_log,
            use_container_width=True,
            hide_index=True,
            key=table_key,
            column_config={
                "Due Date": st.column_config.TextColumn(
                    "Due Date", help="Target delivery arrival date"
                ),
                "Qty": st.column_config.NumberColumn(format="%.1f"),
            },
        )
    else:
        st.info(f"No pending deliveries found specifically for {clean_user}.")
else:
    st.success("✅ No pending scheduled deliveries found.")
