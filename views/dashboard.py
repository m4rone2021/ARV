from datetime import date, datetime
import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st
from database import get_db


def apply_calm_dashboard_theme():
    """Injects fluid, responsive CSS optimized for touch controls and mobile containers."""
    st.markdown(
        """
        <style>
            :root {
                --primary-accent: #E65100;
                --secondary-accent: #00897B;
                --alert-bg: #FFF3E0;
                --card-bg: #FAFAFA;
                --border-color: #E0E0E0;
            }

            /* Responsive container padding */
            .main .block-container {
                padding-top: 1rem !important;
                padding-bottom: 2rem !important;
                padding-left: 0.5rem !important;
                padding-right: 0.5rem !important;
            }

            /* Metric Cards Flex Styling */
            div[data-testid="stMetric"] {
                background-color: var(--card-bg);
                border: 1px solid var(--border-color);
                border-left: 4px solid var(--secondary-accent);
                border-radius: 8px;
                padding: 8px 10px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            }

            /* Touch-Friendly Button Heights */
            div.stButton > button,
            div.stFormSubmitButton > button,
            div[data-testid="stPopover"] > button {
                background-color: var(--primary-accent) !important;
                color: #FFFFFF !important;
                border: none !important;
                border-radius: 6px !important;
                font-weight: 600 !important;
                min-height: 48px !important;
                width: 100% !important;
                font-size: 15px !important;
            }

            /* Native Card Design for Mobile Data */
            .mobile-card {
                background: #FFFFFF;
                border: 1px solid var(--border-color);
                border-radius: 8px;
                padding: 12px;
                margin-bottom: 10px;
                box-shadow: 0 1px 2px rgba(0,0,0,0.03);
            }
            .mobile-card-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-bottom: 1px solid #F0F0F0;
                padding-bottom: 6px;
                margin-bottom: 6px;
            }
            .mobile-card-title {
                font-weight: bold;
                font-size: 0.95rem;
                color: #333;
            }
            .mobile-card-badge {
                background: #E0F2F1;
                color: #004D40;
                font-size: 0.75rem;
                padding: 2px 6px;
                border-radius: 4px;
                font-weight: 600;
            }

            /* Mobile Breakpoints & Fluid Typography */
            @media (max-width: 640px) {
                div[data-testid="stMetricValue"] {
                    font-size: 1.1rem !important;
                }
                div[data-testid="stMetricLabel"] {
                    font-size: 0.75rem !important;
                }
                /* Stacks radio options for easier touch selection */
                div[data-testid="stRadio"] > div {
                    flex-direction: column !important;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def calculate_days_left(due_date_str):
    """Calculate days remaining from today until the due date safely handling timestamps."""
    if not due_date_str:
        return 9999, "Unknown"
    try:
        clean_date = str(due_date_str).strip().split(" ")[0]
        due_dt = datetime.strptime(clean_date, "%Y-%m-%d").date()
        today = date.today()
        days_diff = (due_dt - today).days

        if days_diff < 0:
            return days_diff, f"⚠️ Overdue ({abs(days_diff)}d)"
        elif days_diff == 0:
            return days_diff, "⚡ Due Today"
        elif days_diff == 1:
            return days_diff, "⏳ 1 day left"
        else:
            return days_diff, f"⏳ {days_diff} days left"
    except Exception:
        return 9999, "Unknown"


def render_dashboard(user_name="Guest", user_role="User"):
    apply_calm_dashboard_theme()

    st.title("📊 Executive Dashboard")

    is_admin = user_role.lower() in ["admin", "manager"] if user_role else False
    st.caption("Real-time inventory, task reminders, and scheduled dispatches.")

    categories = st.session_state.get(
        "categories",
        [
            "Fuel & Oils",
            "Construction Materials",
            "Steel / Rebar",
            "Nails & Fasteners",
            "Cutting & Grinding Consumables",
            "Welding Supplies & PPE",
            "General Site Supplies",
        ],
    )

    deliveries_df = pd.DataFrame()
    reminders_df = pd.DataFrame()

    clean_user = str(user_name).strip() if user_name else "Guest"

    try:
        with get_db() as conn:
            # 1. Fetch master inventory items
            df = pd.read_sql_query(
                """
                SELECT id, item_name, category, unit, 
                       COALESCE(current_stock, 0.0) AS current_stock, 
                       COALESCE(reserved_stock, 0.0) AS reserved_stock, 
                       COALESCE(min_threshold, 0.0) AS min_threshold 
                FROM master_items 
                ORDER BY category ASC, item_name ASC
            """,
                conn,
            )

            if not df.empty:
                df["effective_stock"] = df["current_stock"] - df["reserved_stock"]
            else:
                df = pd.DataFrame(
                    columns=[
                        "id",
                        "item_name",
                        "category",
                        "unit",
                        "current_stock",
                        "reserved_stock",
                        "min_threshold",
                        "effective_stock",
                    ]
                )

            # 2. Check database tables
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('tasks', 'reminders', 'scheduled_deliveries', 'deliveries')"
            )
            tables = [row[0] for row in cursor.fetchall()]

            # 3. Fetch Pending Scheduled Deliveries
            delivery_table = next(
                (t for t in ["scheduled_deliveries", "deliveries"] if t in tables), None
            )

            if delivery_table:
                cursor.execute(f"PRAGMA table_info({delivery_table})")
                del_cols = [col[1] for col in cursor.fetchall()]

                date_col = next(
                    (
                        c
                        for c in ["due_date", "delivery_date", "expected_date", "date"]
                        if c in del_cols
                    ),
                    "NULL",
                )
                item_col = next(
                    (
                        c
                        for c in ["item_name", "item", "description", "title"]
                        if c in del_cols
                    ),
                    "'N/A'",
                )

                dispatch_id_col = next(
                    (
                        c
                        for c in [
                            "dispatch_id",
                            "dispatch_no",
                            "po_number",
                            "delivery_ref",
                            "group_id",
                        ]
                        if c in del_cols
                    ),
                    None,
                )

                qty_col = (
                    "quantity"
                    if "quantity" in del_cols
                    else "qty" if "qty" in del_cols else "amount" if "amount" in del_cols else "1"
                )
                supplier_col = next(
                    (c for c in ["supplier", "vendor", "source"] if c in del_cols),
                    "'Unspecified'",
                )
                status_col = next(
                    (c for c in ["status", "delivery_status", "state"] if c in del_cols),
                    "'Pending'",
                )
                requestor_col = next(
                    (
                        c
                        for c in ["requestor", "requested_by", "requested_person"]
                        if c in del_cols
                    ),
                    "'N/A'",
                )
                project_col = next(
                    (c for c in ["project_name", "project", "site_name"] if c in del_cols),
                    "'Main Site'",
                )
                created_by_col = next(
                    (
                        c
                        for c in ["created_by", "created_user", "author"]
                        if c in del_cols
                    ),
                    "'System'",
                )

                dispatch_select = (
                    f"{dispatch_id_col} AS dispatch_ref,"
                    if dispatch_id_col
                    else "NULL AS dispatch_ref,"
                )

                query_del = f"""
                    SELECT id, 
                           {dispatch_select}
                           {date_col} AS due_date, 
                           {item_col} AS item_name, 
                           {qty_col} AS quantity, 
                           {supplier_col} AS supplier, 
                           {requestor_col} AS requestor,
                           {project_col} AS project_name,
                           {created_by_col} AS created_by,
                           {status_col} AS status
                    FROM {delivery_table}
                    WHERE UPPER({status_col}) NOT IN ('COMPLETED', 'DELIVERED', 'CANCELLED')
                """
                deliveries_df = pd.read_sql_query(query_del, conn)

                if not deliveries_df.empty:
                    if (
                        "dispatch_ref" not in deliveries_df.columns
                        or deliveries_df["dispatch_ref"].isnull().all()
                    ):
                        deliveries_df["dispatch_key"] = (
                            deliveries_df["due_date"].astype(str)
                            + " | "
                            + deliveries_df["supplier"].astype(str)
                            + " | "
                            + deliveries_df["project_name"].astype(str)
                        )
                    else:
                        deliveries_df["dispatch_key"] = deliveries_df["dispatch_ref"].astype(str)

            # 4. Fetch Active Tasks
            task_table = next((t for t in ["tasks", "reminders"] if t in tables), None)

            if task_table:
                cursor.execute(f"PRAGMA table_info({task_table})")
                rem_cols = [col[1] for col in cursor.fetchall()]

                task_col = next(
                    (
                        c
                        for c in ["task_description", "task", "description", "title"]
                        if c in rem_cols
                    ),
                    "'Task'",
                )
                has_priority = "priority" in rem_cols
                select_priority = ", priority" if has_priority else ""

                if is_admin:
                    query_rem = f"""
                        SELECT id, due_date, {task_col} AS task, assigned_to, status {select_priority}
                        FROM {task_table}
                        WHERE UPPER(status) IN ('OPEN', 'PENDING')
                    """
                    params_rem = []
                else:
                    query_rem = f"""
                        SELECT id, due_date, {task_col} AS task, assigned_to, status {select_priority}
                        FROM {task_table}
                        WHERE UPPER(status) IN ('OPEN', 'PENDING') AND LOWER(assigned_to) = LOWER(?)
                    """
                    params_rem = [clean_user]

                reminders_df = pd.read_sql_query(query_rem, conn, params=params_rem)
                if not has_priority or "priority" not in reminders_df.columns:
                    reminders_df["priority"] = "NORMAL"

    except Exception as e:
        st.error(f"Error loading dashboard metrics: {e}")
        return

    # Metrics Calculations
    total_items = len(df)
    low_stock_df = (
        df[df["effective_stock"] <= df["min_threshold"]]
        if not df.empty
        else pd.DataFrame()
    )
    low_stock_count = len(low_stock_df)
    total_units_stocked = df["current_stock"].sum() if not df.empty else 0.0
    pending_dispatches_count = (
        deliveries_df["dispatch_key"].nunique() if not deliveries_df.empty else 0
    )

    # 1. Metric Cards Grid (2x2 Grid for Mobile Balance)
    m_col1, m_col2 = st.columns(2)
    m_col1.metric(label="📦 Unique Items", value=f"{total_items:,}")
    m_col2.metric(label="📊 Physical Stock", value=f"{total_units_stocked:,.1f}")

    m_col3, m_col4 = st.columns(2)
    m_col3.metric(
        label="⚠️ Low Stock",
        value=f"{low_stock_count}",
        delta=f"-{low_stock_count}" if low_stock_count > 0 else "Optimal",
        delta_color="inverse" if low_stock_count > 0 else "normal",
    )
    m_col4.metric(
        label="🚚 Pending",
        value=f"{pending_dispatches_count}",
        delta="Required" if pending_dispatches_count > 0 else "None",
        delta_color="off",
    )

    st.divider()

    # View Mode Switcher for Dispatches Log
    st.subheader("🚚 Scheduled Dispatches Log")
    
    use_mobile_cards = st.toggle("📱 Mobile Card View", value=True, key="mobile_card_toggle")

    if not deliveries_df.empty:
        # Full-width container stacking for touch devices
        delivery_view_mode = st.radio(
            "Filter View",
            options=["All Dispatches", f"My Dispatches ({clean_user})"],
            index=0,
            key="delivery_filter_radio",
            horizontal=True,
        )

        if delivery_view_mode == f"My Dispatches ({clean_user})":
            filtered_del_df = deliveries_df[
                (deliveries_df["requestor"].astype(str).str.lower() == clean_user.lower())
                | (deliveries_df["created_by"].astype(str).str.lower() == clean_user.lower())
            ].copy()
        else:
            filtered_del_df = deliveries_df.copy()

        if not filtered_del_df.empty:
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

            parsed_del_dates = grouped["due_date"].apply(calculate_days_left)
            grouped["days_left_num"] = [d[0] for d in parsed_del_dates]
            grouped["days_left_str"] = [d[1] for d in parsed_del_dates]

            c1, c2 = st.columns([2, 1])
            with c1:
                sort_field = st.selectbox(
                    "Sort By",
                    options=["due_date", "supplier", "project_name", "item_count", "total_qty"],
                    format_func=lambda x: {
                        "due_date": "Due Date",
                        "supplier": "Supplier",
                        "project_name": "Project",
                        "item_count": "Total Item Types",
                        "total_qty": "Total Quantity",
                    }.get(x, x),
                    key="delivery_sort_field",
                )
            with c2:
                sort_order = st.radio("Order", options=["Asc", "Desc"], key="delivery_sort_order", horizontal=True)

            grouped = grouped.sort_values(by=sort_field, ascending=(sort_order == "Asc"))

            # Mobile Native Responsive Cards Output
            if use_mobile_cards:
                for _, row in grouped.iterrows():
                    st.markdown(
                        f"""
                        <div class="mobile-card">
                            <div class="mobile-card-header">
                                <span class="mobile-card-title">{row['supplier']} ({row['project_name']})</span>
                                <span class="mobile-card-badge">{row['days_left_str']}</span>
                            </div>
                            <div style="font-size: 0.85rem; color: #555;">
                                📅 <b>Due:</b> {row['due_date']}<br>
                                📦 <b>Items:</b> {row['items_summary']}<br>
                                🔢 <b>Qty:</b> {row['total_qty']} ({row['item_count']} types)<br>
                                👤 <b>Requestor:</b> {row['requestor']}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                display_log = grouped[
                    ["dispatch_key", "due_date", "days_left_str", "project_name", "supplier", "items_summary", "item_count", "total_qty", "requestor"]
                ]
                st.dataframe(display_log, use_container_width=True, hide_index=True)

            with st.expander("🔍 Inspect Dispatch Details", expanded=False):
                selected_dispatch = st.selectbox(
                    "Select reference:",
                    options=grouped["dispatch_key"].unique(),
                    key="dispatch_detail_select",
                )
                if selected_dispatch:
                    items_in_dispatch = filtered_del_df[
                        filtered_del_df["dispatch_key"] == selected_dispatch
                    ][["item_name", "quantity", "requestor", "status"]]
                    st.dataframe(items_in_dispatch, use_container_width=True, hide_index=True)

        else:
            st.info(f"No dispatches found for {clean_user}.")
    else:
        st.success("✅ No pending scheduled dispatches.")

    st.divider()

    # 3. Action Items & Reminders
    st.subheader("📌 Action Items & Reminders" if is_admin else f"📌 My Tasks ({user_name})")
    if not reminders_df.empty:
        parsed_dates = reminders_df["due_date"].apply(calculate_days_left)
        reminders_df["days_left_num"] = [d[0] for d in parsed_dates]
        reminders_df["days_left_str"] = [d[1] for d in parsed_dates]

        reminders_df = reminders_df.sort_values(by=["days_left_num", "priority"], ascending=[True, False])

        if use_mobile_cards:
            for _, row in reminders_df.iterrows():
                st.markdown(
                    f"""
                    <div class="mobile-card">
                        <div class="mobile-card-header">
                            <span class="mobile-card-title">{row['task']}</span>
                            <span class="mobile-card-badge">{row['days_left_str']}</span>
                        </div>
                        <div style="font-size: 0.85rem; color: #555;">
                            📅 <b>Due:</b> {row['due_date']} | 👤 <b>Assigned:</b> {row['assigned_to']}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            display_reminders = reminders_df[["due_date", "days_left_str", "task", "assigned_to"]]
            st.dataframe(display_reminders, use_container_width=True, hide_index=True)
    else:
        st.success("✅ No pending tasks found.")

    st.divider()

    # 4. Critical Low Stock Warnings
    st.subheader("⚠️ Critical Low Stock Warnings")
    if not low_stock_df.empty:
        st.warning(f"Attention: {low_stock_count} item(s) below threshold!")

        if use_mobile_cards:
            for _, row in low_stock_df.iterrows():
                st.markdown(
                    f"""
                    <div class="mobile-card" style="border-left: 4px solid var(--primary-accent);">
                        <div class="mobile-card-header">
                            <span class="mobile-card-title">{row['item_name']}</span>
                            <span class="mobile-card-badge" style="background: var(--alert-bg); color: var(--primary-accent);">Limit: {row['min_threshold']}</span>
                        </div>
                        <div style="font-size: 0.85rem; color: #555;">
                            📂 <b>Category:</b> {row['category']}<br>
                            📊 <b>Available:</b> {row['effective_stock']} {row['unit']} (Reserved: {row['reserved_stock']})
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            low_stock_display = low_stock_df[["item_name", "category", "current_stock", "reserved_stock", "effective_stock", "unit", "min_threshold"]]
            st.dataframe(low_stock_display, use_container_width=True, hide_index=True)
    else:
        st.success("✅ Stock levels optimal.")

    st.divider()

    # 5. Mobile Horizontal Bar Chart Breakdown
    st.subheader("📦 Stock Breakdown per Item")
    if not df.empty:
        chart_cat_filter = st.selectbox(
            "Filter Category",
            ["All Categories"] + categories,
            key="item_chart_cat_filter",
        )

        chart_source = df.copy()
        if chart_cat_filter != "All Categories":
            chart_source = chart_source[chart_source["category"] == chart_cat_filter]

        if not chart_source.empty:
            chart_source["Available Stock"] = chart_source["effective_stock"]

            chart_df = pd.melt(
                chart_source,
                id_vars=["item_name", "category"],
                value_vars=["Available Stock", "reserved_stock"],
                var_name="Stock Type",
                value_name="Quantity",
            )
            chart_df["Stock Type"] = chart_df["Stock Type"].replace({"reserved_stock": "Reserved Stock"})

            fig = px.bar(
                chart_df,
                y="item_name",
                x="Quantity",
                color="Stock Type",
                orientation="h",
                hover_data=["category"],
                labels={"item_name": "Item", "Quantity": "Units"},
                text_auto=".1f",
                color_discrete_map={
                    "Available Stock": "#00897B",
                    "Reserved Stock": "#E65100",
                },
            )

            # Mobile view optimization for Plotly Chart
            fig.update_layout(
                barmode="stack",
                height=max(320, len(chart_source) * 45),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="#F9F9F9",
                font=dict(family="sans-serif", size=10, color="#333333"),
                margin=dict(l=5, r=5, t=30, b=10),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="left",
                    x=0,
                    title_text="",
                ),
            )
            fig.update_xaxes(showgrid=True, gridcolor="#E5E5E5")

            st.plotly_chart(fig, use_container_width=True, config={"responsive": True, "displayModeBar": False})
