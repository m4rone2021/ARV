import sqlite3
from datetime import datetime, date
import pandas as pd
import streamlit as st
import plotly.express as px
from database import get_db


def calculate_days_left(due_date_str):
    """Calculate days remaining from today until the due date safely handling timestamps."""
    if not due_date_str:
        return 9999, "No Date"
    try:
        clean_date = str(due_date_str).strip().split(" ")[0]
        due_dt = datetime.strptime(clean_date, "%Y-%m-%d").date()
        today = date.today()
        days_diff = (due_dt - today).days

        if days_diff < 0:
            return days_diff, f"🔴 OVERDUE ({abs(days_diff)}d ago)"
        elif days_diff == 0:
            return days_diff, "🟠 DUE TODAY"
        elif days_diff == 1:
            return days_diff, "🟡 1 day left"
        else:
            return days_diff, f"🟢 {days_diff} days left"
    except Exception:
        return 9999, "Invalid Date"


def render_dashboard(user_name, user_role):
    st.title("📊 Executive Dashboard")

    is_admin = user_role.lower() in ["admin", "manager"] if user_role else False
    st.caption(
        "Real-time summary of current stock levels, reserved stock, item distributions, and task reminders."
    )

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

            # 2. Fetch active tasks/reminders safely
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('tasks', 'reminders')"
            )
            tables = [row[0] for row in cursor.fetchall()]

            reminders_df = pd.DataFrame()

            if "tasks" in tables or "reminders" in tables:
                task_table = "tasks" if "tasks" in tables else "reminders"
                
                # Fetch columns for safe mapping
                cursor.execute(f"PRAGMA table_info({task_table})")
                rem_cols = [col[1] for col in cursor.fetchall()]

                task_col = (
                    "task_description"
                    if "task_description" in rem_cols
                    else ("task" if "task" in rem_cols else "description")
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
                    params_rem = [user_name.strip()]

                reminders_df = pd.read_sql_query(query_rem, conn, params=params_rem)
                
                if not has_priority or "priority" not in reminders_df.columns:
                    reminders_df["priority"] = "NORMAL"

    except Exception as e:
        st.error(f"Error loading dashboard metrics: {e}")
        return

    # Metrics Calculations
    total_items = len(df)
    low_stock_df = df[df["effective_stock"] <= df["min_threshold"]] if not df.empty else pd.DataFrame()
    low_stock_count = len(low_stock_df)
    total_units_stocked = df["current_stock"].sum() if not df.empty else 0.0
    total_units_reserved = df["reserved_stock"].sum() if not df.empty else 0.0

    open_tasks_count = len(reminders_df)
    high_priority_count = (
        len(reminders_df[reminders_df["priority"].astype(str).str.upper() == "HIGH"])
        if not reminders_df.empty and "priority" in reminders_df.columns
        else 0
    )

    # 1. Top Metrics Display
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric(label="📦 Unique Items", value=f"{total_items:,}")
    col2.metric(label="📊 Physical Stock", value=f"{total_units_stocked:,.1f}")
    col3.metric(label="🔒 Reserved Stock", value=f"{total_units_reserved:,.1f}")
    col4.metric(
        label="⚠️ Low Stock Warnings",
        value=f"{low_stock_count}",
        delta=f"-{low_stock_count}" if low_stock_count > 0 else "Optimal",
        delta_color="inverse" if low_stock_count > 0 else "normal",
    )
    col5.metric(
        label="📝 Total Tasks" if is_admin else "📝 My Tasks",
        value=f"{open_tasks_count}",
        delta=f"🚨 {high_priority_count} High" if high_priority_count > 0 else "All Normal",
        delta_color="inverse" if high_priority_count > 0 else "normal",
    )

    st.divider()

    # 2. Charts and Task List
    chart_col, alert_col = st.columns([3, 2])

    with chart_col:
        st.subheader("📦 Stock Breakdown per Item")
        if not df.empty:
            chart_cat_filter = st.selectbox(
                "Filter Chart Category",
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
                chart_df["Stock Type"] = chart_df["Stock Type"].replace(
                    {"reserved_stock": "Reserved Stock"}
                )

                fig = px.bar(
                    chart_df,
                    x="item_name",
                    y="Quantity",
                    color="Stock Type",
                    hover_data=["category"],
                    labels={"item_name": "Item Description", "Quantity": "Units"},
                    text_auto=".1f",
                    color_discrete_map={
                        "Available Stock": "#00CC96",
                        "Reserved Stock": "#EF553B",
                    },
                )
                fig.update_layout(
                    barmode="stack",
                    xaxis_tickangle=-45,
                    height=380,
                    margin=dict(l=20, r=20, t=20, b=60),
                    legend=dict(
                        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
                    ),
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No items found for the selected category filter.")
        else:
            st.info("ℹ️ No items currently registered in the Master Catalog.")

    with alert_col:
        st.subheader("📌 Action Items & Reminders" if is_admin else f"📌 My Tasks ({user_name})")
        if not reminders_df.empty:
            parsed_dates = reminders_df["due_date"].apply(calculate_days_left)
            reminders_df["days_left_num"] = [d[0] for d in parsed_dates]
            reminders_df["days_left_str"] = [d[1] for d in parsed_dates]

            reminders_df = reminders_df.sort_values(
                by=["days_left_num", "priority"], ascending=[True, False]
            )

            reminders_df["Priority"] = reminders_df["priority"].apply(
                lambda x: "🚨 HIGH" if str(x).upper() == "HIGH" else "NORMAL"
            )

            display_reminders = reminders_df[
                ["due_date", "days_left_str", "Priority", "task", "assigned_to"]
            ].rename(
                columns={
                    "due_date": "Due Date",
                    "days_left_str": "Days Left",
                    "task": "Task Description",
                    "assigned_to": "Assigned",
                }
            )

            st.dataframe(display_reminders, use_container_width=True, hide_index=True)
        else:
            st.success("✅ No pending tasks found.")

        st.divider()

        st.subheader("⚠️ Critical Low Stock Warnings")
        if not low_stock_df.empty:
            st.warning(
                f"Attention: {low_stock_count} item(s) are at or below safety threshold based on effective stock!"
            )

            low_stock_display = low_stock_df[
                [
                    "item_name",
                    "category",
                    "current_stock",
                    "reserved_stock",
                    "effective_stock",
                    "unit",
                    "min_threshold",
                ]
            ].rename(
                columns={
                    "item_name": "Item Description",
                    "category": "Category",
                    "current_stock": "Total Stock",
                    "reserved_stock": "Reserved",
                    "effective_stock": "Available",
                    "unit": "Unit",
                    "min_threshold": "Limit",
                }
            )
            st.dataframe(
                low_stock_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Total Stock": st.column_config.NumberColumn(format="%.2f"),
                    "Reserved": st.column_config.NumberColumn(format="%.2f"),
                    "Available": st.column_config.NumberColumn(format="%.2f"),
                    "Limit": st.column_config.NumberColumn(format="%.2f"),
                },
            )
        else:
            st.success("✅ All stock items are currently above safety thresholds.")

    st.divider()

    # 3. Category Overview
    st.subheader("📋 Current Stock Levels Overview")

    if not df.empty:
        col_filter1, col_filter2 = st.columns([1, 2])
        with col_filter1:
            cat_filter = st.selectbox(
                "Filter Category",
                ["All Categories"] + categories,
                key="dash_cat_filter",
            )
        with col_filter2:
            dash_search = st.text_input(
                "🔍 Quick Search Item",
                placeholder="Type item name to filter...",
                key="dash_search",
            )

        filtered_df = df.copy()

        if cat_filter != "All Categories":
            filtered_df = filtered_df[filtered_df["category"] == cat_filter]

        if dash_search.strip():
            filtered_df = filtered_df[
                filtered_df["item_name"].str.contains(
                    dash_search.strip(), case=False, na=False
                )
            ]

        if not filtered_df.empty:
            grouped_categories = filtered_df["category"].unique()

            for cat in sorted(grouped_categories):
                cat_items = filtered_df[filtered_df["category"] == cat]
                st.markdown(f"### **📁 {cat}** `({len(cat_items)} items)`")

                display_df = cat_items[
                    [
                        "id",
                        "item_name",
                        "unit",
                        "current_stock",
                        "reserved_stock",
                        "effective_stock",
                        "min_threshold",
                    ]
                ].rename(
                    columns={
                        "id": "ID",
                        "item_name": "Item Description",
                        "unit": "Unit",
                        "current_stock": "Physical Stock",
                        "reserved_stock": "Reserved Stock",
                        "effective_stock": "Effective Available",
                        "min_threshold": "Safety Limit",
                    }
                )

                st.dataframe(
                    display_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Physical Stock": st.column_config.NumberColumn(
                            "Physical Stock", format="%.2f"
                        ),
                        "Reserved Stock": st.column_config.NumberColumn(
                            "Reserved Stock", format="%.2f"
                        ),
                        "Effective Available": st.column_config.NumberColumn(
                            "Effective Available", format="%.2f"
                        ),
                        "Safety Limit": st.column_config.NumberColumn(
                            "Safety Limit", format="%.2f"
                        ),
                    },
                )
        else:
            st.info("No matching stock items found.")
    else:
        st.info("ℹ️ No inventory items found in database.")
