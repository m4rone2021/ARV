from datetime import date, datetime
import pandas as pd
import streamlit as st

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


# Sample Data Generation (Including multiple items for the same dispatch)
@st.cache_data
def load_sample_data():
    return pd.DataFrame(
        [
            {
                "dispatch_id": "DSP-1001",
                "due_date": "2026-09-10",
                "item_name": "Steel Beams 20ft",
                "project_name": "Site Alpha",
                "quantity": 15.0,
                "supplier": "BuildCorp",
                "requestor": "john_doe",
                "created_by": "john_doe",
            },
            {
                "dispatch_id": "DSP-1001",
                "due_date": "2026-09-10",
                "item_name": "Rebar 12mm",
                "project_name": "Site Alpha",
                "quantity": 50.0,
                "supplier": "BuildCorp",
                "requestor": "john_doe",
                "created_by": "john_doe",
            },
            {
                "dispatch_id": "DSP-1002",
                "due_date": "2026-09-05",
                "item_name": "Portland Cement Bags",
                "project_name": "Site Beta",
                "quantity": 100.0,
                "supplier": "Concrete Co.",
                "requestor": "jane_smith",
                "created_by": "admin",
            },
            {
                "dispatch_id": "DSP-1003",
                "due_date": "2026-09-15",
                "item_name": "Copper Wiring Spools",
                "project_name": "Site Alpha",
                "quantity": 8.0,
                "supplier": "Electro Supplies",
                "requestor": "john_doe",
                "created_by": "jane_smith",
            },
            {
                "dispatch_id": "DSP-1004",
                "due_date": "2026-09-07",
                "item_name": "Safety Helmets",
                "project_name": "Site Gamma",
                "quantity": 50.0,
                "supplier": "SafeGear Ltd",
                "requestor": "alex_gear",
                "created_by": "alex_gear",
            },
        ]
    )


# Application State Setup
clean_user = "john_doe"
deliveries_df = load_sample_data()

# Main Application Layout
st.title("📦 Logistics & Procurement Tracker")

# ---------------------------------------------------------
# 2. Scheduled Dispatches Log
# ---------------------------------------------------------
st.subheader("🚚 Scheduled Dispatches Log")

if not deliveries_df.empty:

    # Fallback to composite key if dispatch_id does not exist
    if "dispatch_id" in deliveries_df.columns:
        deliveries_df["dispatch_key"] = deliveries_df["dispatch_id"]
    else:
        deliveries_df["dispatch_key"] = (
            deliveries_df["due_date"].astype(str)
            + " | "
            + deliveries_df["supplier"].astype(str)
            + " | "
            + deliveries_df["project_name"].astype(str)
        )

    # UI Filter & Sort Controls optimized for Mobile Viewports
    filter_col, sort_col, order_col = st.columns([2, 2, 1])

    with filter_col:
        delivery_view_mode = st.radio(
            "Filter View",
            options=["All Dispatches", f"My Dispatches ({clean_user})"],
            index=0,
            key="delivery_filter_radio",
            horizontal=True,
        )

    # Apply User Filtering
    if delivery_view_mode == f"My Dispatches ({clean_user})":
        filtered_del_df = deliveries_df[
            (
                deliveries_df["requestor"].astype(str).str.lower()
                == clean_user.lower()
            )
            | (
                deliveries_df["created_by"].astype(str).str.lower()
                == clean_user.lower()
            )
        ].copy()
    else:
        filtered_del_df = deliveries_df.copy()

    if not filtered_del_df.empty:
        # Group raw item entries into single dispatch summaries
        grouped = (
            filtered_del_df.groupby("dispatch_key")
            .agg(
                {
                    "due_date": "first",
                    "supplier": "first",
                    "project_name": "first",
                    "item_name": lambda items: ", ".join(items.unique()),
                    "quantity": ["count", "sum"],
                    "requestor": lambda reqs: ", ".join(reqs.unique()),
                    "created_by": "first",
                }
            )
            .reset_index()
        )

        # Flatten multi-level columns
        grouped.columns = [
            "dispatch_key",
            "due_date",
            "supplier",
            "project_name",
            "items_summary",
            "item_count",
            "total_qty",
            "requestor",
            "created_by",
        ]

        # Calculate time remaining
        parsed_del_dates = grouped["due_date"].apply(calculate_days_left)
        grouped["days_left_num"] = [d[0] for d in parsed_del_dates]
        grouped["days_left_str"] = [d[1] for d in parsed_del_dates]

        # Mobile-Friendly Sorting Inputs
        with sort_col:
            sort_field = st.selectbox(
                "Sort By",
                options=[
                    "due_date",
                    "supplier",
                    "project_name",
                    "item_count",
                    "total_qty",
                ],
                format_func=lambda x: {
                    "due_date": "Due Date",
                    "supplier": "Supplier",
                    "project_name": "Project",
                    "item_count": "Total Item Types",
                    "total_qty": "Total Quantity",
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

        # Perform sorting directly on grouped Dataframe
        is_ascending = sort_order == "Asc"
        grouped = grouped.sort_values(by=sort_field, ascending=is_ascending)

        st.caption(
            f"Sorted by **{sort_field.replace('_', ' ').title()}** ({'Ascending' if is_ascending else 'Descending'})"
        )

        # Format Display DataFrame
        grouped["Due Date"] = grouped["due_date"].apply(lambda d: f"**{d}**")

        display_log = grouped[
            [
                "dispatch_key",
                "Due Date",
                "days_left_str",
                "project_name",
                "supplier",
                "items_summary",
                "item_count",
                "total_qty",
                "requestor",
            ]
        ].rename(
            columns={
                "dispatch_key": "Dispatch Ref",
                "days_left_str": "Status",
                "project_name": "Project",
                "supplier": "Supplier / Vendor",
                "items_summary": "Included Items",
                "item_count": "Item Types",
                "total_qty": "Total Qty",
                "requestor": "Requestor(s)",
            }
        )

        table_key = f"del_tbl_{delivery_view_mode}_{sort_field}_{sort_order}"

        st.dataframe(
            display_log,
            use_container_width=True,
            hide_index=True,
            key=table_key,
            column_config={
                "Due Date": st.column_config.TextColumn(
                    "Due Date", help="Target dispatch arrival date"
                ),
                "Item Types": st.column_config.NumberColumn(format="%d"),
                "Total Qty": st.column_config.NumberColumn(format="%.1f"),
            },
        )

        # Detailed Breakdown Expander
        with st.expander("🔍 Inspect Dispatch Line Items", expanded=False):
            selected_dispatch = st.selectbox(
                "Select a dispatch reference to view individual items:",
                options=grouped["dispatch_key"].unique(),
                key="dispatch_detail_select",
            )

            if selected_dispatch:
                items_in_dispatch = filtered_del_df[
                    filtered_del_df["dispatch_key"] == selected_dispatch
                ][
                    [
                        "item_name",
                        "quantity",
                        "requestor",
                        "created_by",
                    ]
                ].rename(
                    columns={
                        "item_name": "Item Description",
                        "quantity": "Quantity",
                        "requestor": "Requested By",
                        "created_by": "Created By",
                    }
                )
                st.dataframe(
                    items_in_dispatch, use_container_width=True, hide_index=True
                )

    else:
        st.info(f"No pending dispatches found specifically for {clean_user}.")
else:
    st.success("✅ No pending scheduled dispatches found.")
