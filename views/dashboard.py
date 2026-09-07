import sqlite3
from datetime import date, datetime
import pandas as pd
import plotly.express as px
import streamlit as st
from database import get_db


def apply_calm_dashboard_theme():
    """Injects custom CSS for a calm, professional dashboard theme with warm accents."""
    st.markdown(
        """
        <style>
            /* Color Variables */
            :root {
                --primary-accent: #E65100;      /* Warm Deep Orange */
                --secondary-accent: #00897B;    /* Calm Teal */
                --alert-bg: #FFF3E0;            /* Soft Orange Tint */
                --card-bg: #FAFAFA;             /* Crisp Neutral Light Card */
                --border-color: #E0E0E0;
            }

            /* Main Page Adjustments */
            .main .block-container {
                padding-top: 1.5rem;
                padding-bottom: 2rem;
            }

            /* Custom KPI Card Styling */
            div[data-testid="stMetric"] {
                background-color: var(--card-bg);
                border: 1px solid var(--border-color);
                border-left: 5px solid var(--secondary-accent);
                border-radius: 8px;
                padding: 12px 16px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.02);
            }

            /* Primary Action / Filter Buttons */
            div.stButton > button,
            div.stFormSubmitButton > button {
                background-color: var(--primary-accent) !important;
                color: #FFFFFF !important;
                border: none !important;
                border-radius: 6px !important;
                font-weight: 600 !important;
                transition: all 0.2s ease-in-out;
            }

            div.stButton > button:hover,
            div.stFormSubmitButton > button:hover {
                background-color: #BF360C !important;
                box-shadow: 0 4px 8px rgba(191, 54, 12, 0.25) !important;
                transform: translateY(-1px);
            }

            /* Selectboxes and Inputs focus borders */
            div[data-baseweb="select"] > div,
            input[type="text"] {
                border-radius: 6px !important;
                border-color: var(--border-color) !important;
            }

            /* Expander Styling */
            div[data-testid="stExpander"] {
                border: 1px solid var(--border-color) !important;
                border-radius: 8px !important;
                background-color: #FFFFFF;
            }

            /* Soften Tables */
            .stDataFrame {
                border-radius: 6px;
                overflow: hidden;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


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
    # Apply Visual Theme
    apply_calm_dashboard_theme()

    st.title("📊 Executive Dashboard")

    is_admin = user_role.lower() in ["admin", "manager"] if user_role else False
    st.caption(
        "Real-time summary of stock levels, reserved stock, item distributions, and task reminders."
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
    low_stock_df = (
        df[df["effective_stock"] <= df["min_threshold"]]
        if not df.empty
        else pd.DataFrame()
    )
    low_stock_count = len(low_stock_df)
    total_units_stocked = df["current_stock"].sum() if not df.empty else 0.0
    total_units_reserved = df["reserved_stock"].sum() if not df.empty else 0.0

    open_tasks_count = len(reminders_df)
    high_priority_count = (
        len(reminders_df[reminders_df["priority"].astype(str).str.upper() == "HIGH"])
        if not reminders_df.empty and "priority" in reminders_df.columns
        else 0
    )

    # 1. Top Metrics Cards Grid
    m_col1, m_col2 = st.columns(2)
    m_col1.metric(label="📦 Unique Items", value=f"{total_items:,}")
    m_col2.metric(label="📊 Physical Stock", value=f"{total_units_stocked:,.1f}")

    m_col3, m_col4 = st.columns(2)
    m_col3.metric(label="🔒 Reserved Stock", value=f"{total_units_reserved:,.1f}")
    m_col4.metric(
        label="⚠️ Low Stock",
        value=f"{low_stock_count}",
        delta=f"-{low_stock_count}" if low_stock_count > 0 else "Optimal",
        delta_color="inverse" if low_stock_count > 0 else "normal",
    )

    st.metric(
        label="📝 Total Tasks" if is_admin else "📝 My Tasks",
        value=f"{open_tasks_count}",
        delta=f"🚨 {high_priority_count} High" if high_priority_count > 0 else "All Normal",
        delta_color="inverse" if high_priority_count > 0 else "normal",
    )

    st.divider()

    # 2. Interactive Action Items Table
    st.subheader(
        "📌 Action Items & Reminders" if is_admin else f"📌 My Tasks ({user_name})"
    )
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

    # 3. Critical Low Stock Warnings
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

    # 4. Enhanced Interactive Plotly Stock Chart
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

            # High-Contrast Soft Palette for visual clarity
            fig = px.bar(
                chart_df,
                x="item_name",
                y="Quantity",
                color="Stock Type",
                hover_data=["category"],
                labels={"item_name": "Item Description", "Quantity": "Units"},
                text_auto=".1f",
                color_discrete_map={
                    "Available Stock": "#00897B",  # Soft Teal
                    "Reserved Stock": "#E65100",   # Warm Orange Accent
                },
            )
            
            # Calm background and clean typography
            fig.update_layout(
                barmode="stack",
                xaxis_tickangle=-45,
                height=360,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="#F9F9F9",
                font=dict(family="sans-serif", size=12, color="#333333"),
                margin=dict(l=10, r=10, t=20, b=60),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                    title_text="",
                ),
            )
            fig.update_yaxes(showgrid=True, gridcolor="#E5E5E5")
            
            st.plotly_chart(fig, use_container_width=True, config={"responsive": True})
        else:
            st.info("No items found for the selected category filter.")
    else:
        st.info("ℹ️ No items currently registered in the Master Catalog.")

    st.divider()

    # 5. Category Overview (Clean Filterable Accordions with Frozen/Pinned Column)
    st.subheader("📋 Current Stock Levels Overview")

    if not df.empty:
        f_col1, f_col2 = st.columns([1, 1])
        with f_col1:
            cat_filter = st.selectbox(
                "Filter Category",
                ["All Categories"] + categories,
                key="dash_cat_filter",
            )
        with f_col2:
            dash_search = st.text_input(
                "🔍 Quick Search Item",
                placeholder="Type item name...",
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

                with st.expander(f"📁 {cat} ({len(cat_items)} items)", expanded=True):
                    # Reordered columns: Effective Available, Reserved, Total Stock, Unit, Safety Limit (ID removed)
                    display_df = cat_items[
                        [
                            "item_name",
                            "effective_stock",
                            "reserved_stock",
                            "current_stock",
                            "unit",
                            "min_threshold",
                        ]
                    ].rename(
                        columns={
                            "item_name": "Item Description",
                            "effective_stock": "Effective Available",
                            "reserved_stock": "Reserved Stock",
                            "current_stock": "Total Stock",
                            "unit": "Unit",
                            "min_threshold": "Safety Limit",
                        }
                    )

                    st.dataframe(
                        display_df,
                        use_container_width=True,
                        hide_index=True,
                        # Pinning Item Description so it remains frozen on horizontal scroll
                        column_order=[
                            "Item Description",
                            "Effective Available",
                            "Reserved Stock",
                            "Total Stock",
                            "Unit",
                            "Safety Limit",
                        ],
                        column_config={
                            "Item Description": st.column_config.TextColumn(
                                "Item Description",
                                pinned=True,  # Freezes Item Description when scrolling right
                            ),
                            "Effective Available": st.column_config.NumberColumn(
                                "Effective Available", format="%.2f"
                            ),
                            "Reserved Stock": st.column_config.NumberColumn(
                                "Reserved Stock", format="%.2f"
                            ),
                            "Total Stock": st.column_config.NumberColumn(
                                "Total Stock", format="%.2f"
                            ),
                            "Unit": st.column_config.TextColumn("Unit"),
                            "Safety Limit": st.column_config.NumberColumn(
                                "Safety Limit", format="%.2f"
                            ),
                        },
                    )
        else:
            st.info("No matching stock items found.")
    else:
        st.info("ℹ️ No inventory items found in database.")
