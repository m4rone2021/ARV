# views/dashboard.py
import sqlite3
from datetime import datetime, date
import pandas as pd
import streamlit as st
import plotly.express as px
from database import get_db, init_db

def calculate_days_left(due_date_str):
    """Calculate days remaining from today until the due date."""
    if not due_date_str:
        return 9999, "No Date"
    try:
        due_dt = datetime.strptime(str(due_date_str).strip(), "%Y-%m-%d").date()
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
    st.caption("Real-time summary of current stock levels, reserved stock, item distributions, and task reminders.")

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

    # Fetch master items and reminders from database
    try:
        with get_db() as conn:
            # 1. Fetch master inventory items (including reserved_stock)
            df = pd.read_sql_query("""
                SELECT id, item_name, category, unit, 
                       COALESCE(current_stock, 0.0) AS current_stock, 
                       COALESCE(reserved_stock, 0.0) AS reserved_stock, 
                       min_threshold 
                FROM master_items 
                ORDER BY category ASC, item_name ASC
            """, conn)
            
            # Calculate Effective Available Stock
            if not df.empty:
                df["effective_stock"] = df["current_stock"] - df["reserved_stock"]
            else:
                df["effective_stock"] = 0.0

            # 2. Fetch active reminders/tasks (Role Filtered)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(reminders)")
            rem_cols = [col[1] for col in cursor.fetchall()]

            if rem_cols:
                task_col = "task" if "task" in rem_cols else ("description" if "description" in rem_cols else "reminder")
                has_priority = "priority" in rem_cols
                
                if is_admin:
                    query_rem = f"""
                        SELECT id, due_date, {task_col} AS task, assigned_to, status
                        {', priority' if has_priority else ''}
                        FROM reminders
                        WHERE status IN ('OPEN', 'PENDING')
                    """
                    params_rem = []
                else:
                    query_rem = f"""
                        SELECT id, due_date, {task_col} AS task, assigned_to, status
                        {', priority' if has_priority else ''}
                        FROM reminders
                        WHERE status IN ('OPEN', 'PENDING') AND LOWER(assigned_to) = LOWER(?)
                    """
                    params_rem = [user_name.strip()]

                reminders_df = pd.read_sql_query(query_rem, conn, params=params_rem)
                if not has_priority:
                    reminders_df["priority"] = "NORMAL"
            else:
                reminders_df = pd.DataFrame()

    except Exception as e:
        st.error(f"Error loading dashboard metrics: {e}")
        return

    # Calculate Inventory Metrics
    total_items = len(df)
    low_stock_df = df[df["effective_stock"] <= df["min_threshold"]] if not df.empty else pd.DataFrame()
    low_stock_count = len(low_stock_df)
    total_units_stocked = df["current_stock"].sum() if not df.empty else 0.0
    total_units_reserved = df["reserved_stock"].sum() if not df.empty else 0.0

    # Calculate Reminder Metrics
    open_tasks_count = len(reminders_df)
    high_priority_count = len(reminders_df[reminders_df["priority"] == "HIGH"]) if not reminders_df.empty else 0

    # -------------------------------------------------------------
    # 1. TOP METRICS CARDS
    # -------------------------------------------------------------
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(label="📦 Unique Items", value=f"{total_items:,}")

    with col2:
        st.metric(label="📊 Total Physical Stock", value=f"{total_units_stocked:,.1f}")

    with col3:
        st.metric(label="🔒 Reserved Stock", value=f"{total_units_reserved:,.1f}")

    with col4:
        st.metric(
            label="⚠️ Low Stock Warnings", 
            value=f"{low_stock_count}", 
            delta=f"-{low_stock_count}" if low_stock_count > 0 else "Optimal",
            delta_color="inverse" if low_stock_count > 0 else "normal"
        )

    with col5:
        st.metric(
            label="📝 Open Tasks" if not is_admin else "📝 Total Tasks", 
            value=f"{open_tasks_count}",
            delta=f"🚨 {high_priority_count} High" if high_priority_count > 0 else "All Normal",
            delta_color="inverse" if high_priority_count > 0 else "normal"
        )

    st.divider()

    # -------------------------------------------------------------
    # 2. PER-ITEM STOCK BREAKDOWN CHART & OPEN TASKS / REMINDERS
    # -------------------------------------------------------------
    chart_col, alert_col = st.columns([3, 2])

    with chart_col:
        st.subheader("📦 Stock Breakdown per Item")
        if not df.empty:
            # Dropdown filter specifically for the item chart
            chart_cat_filter = st.selectbox(
                "Filter Chart Category", 
                ["All Categories"] + categories, 
                key="item_chart_cat_filter"
            )

            chart_source = df.copy()
            if chart_cat_filter != "All Categories":
                chart_source = chart_source[chart_source["category"] == chart_cat_filter]

            if not chart_source.empty:
                chart_source["Available Stock"] = chart_source["current_stock"] - chart_source["reserved_stock"]
                
                # Melt for stacked bar chart visualization per item
                chart_df = pd.melt(
                    chart_source, 
                    id_vars=["item_name", "category"], 
                    value_vars=["Available Stock", "reserved_stock"],
                    var_name="Stock Type", 
                    value_name="Quantity"
                )
                chart_df["Stock Type"] = chart_df["Stock Type"].replace({"reserved_stock": "Reserved Stock"})

                fig = px.bar(
                    chart_df, 
                    x="item_name", 
                    y="Quantity", 
                    color="Stock Type",
                    hover_data=["category"],
                    labels={"item_name": "Item Description", "Quantity": "Units"},
                    text_auto=".1f",
                    color_discrete_map={"Available Stock": "#00CC96", "Reserved Stock": "#EF553B"}
                )
                fig.update_layout(
                    barmode="stack", 
                    xaxis_tickangle=-45, 
                    height=380, 
                    margin=dict(l=20, r=20, t=20, b=60),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No items found for the selected category filter.")
        else:
            st.info("ℹ️ No items currently registered in the Master Catalog.")

    with alert_col:
        st.subheader("📌 Action Items & Reminders" if is_admin else f"📌 My Tasks ({user_name})")
        if not reminders_df.empty:
            days_left_data = reminders_df["due_date"].apply(calculate_days_left)
            reminders_df["days_left_num"] = [d[0] for d in days_left_data]
            reminders_df["days_left_str"] = [d[1] for d in days_left_data]

            reminders_df = reminders_df.sort_values(
                by=["days_left_num", "priority"],
                ascending=[True, False]
            )

            reminders_df["Priority"] = reminders_df["priority"].apply(lambda x: "🚨 HIGH" if x == "HIGH" else "NORMAL")

            display_reminders = reminders_df[["due_date", "days_left_str", "Priority", "task", "assigned_to"]].rename(columns={
                "due_date": "Due Date",
                "days_left_str": "Days Left",
                "task": "Task Description",
                "assigned_to": "Assigned"
            })

            st.dataframe(display_reminders, use_container_width=True, hide_index=True)
        else:
            st.success("✅ No pending tasks found.")

        st.divider()

        # Low Stock Section
        st.subheader("⚠️ Critical Low Stock Warnings")
        if not low_stock_df.empty:
            st.warning(f"Attention: {low_stock_count} item(s) are at or below safety threshold based on effective stock!")
            
            low_stock_display = low_stock_df[["item_name", "category", "current_stock", "reserved_stock", "effective_stock", "unit", "min_threshold"]].rename(columns={
                "item_name": "Item Description",
                "category": "Category",
                "current_stock": "Total Stock",
                "reserved_stock": "Reserved",
                "effective_stock": "Available",
                "unit": "Unit",
                "min_threshold": "Limit"
            })
            st.dataframe(low_stock_display, use_container_width=True, hide_index=True)
        else:
            st.success("✅ All stock items are currently above safety thresholds.")

    st.divider()

    # -------------------------------------------------------------
    # 3. CURRENT STOCKS AVAILABLE BY CATEGORY
    # -------------------------------------------------------------
    st.subheader("📋 Current Stock Levels Overview")

    if not df.empty:
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
            # Group items by Category and render with Bold Headers
            grouped_categories = filtered_df["category"].unique()

            for cat in sorted(grouped_categories):
                cat_items = filtered_df[filtered_df["category"] == cat]
                
                # Bold Category Header with Item Count
                st.markdown(f"### **📁 {cat}** `({len(cat_items)} items)`")

                display_df = cat_items[["id", "item_name", "unit", "current_stock", "reserved_stock", "effective_stock", "min_threshold"]].rename(columns={
                    "id": "ID",
                    "item_name": "Item Description",
                    "unit": "Unit",
                    "current_stock": "Physical Stock",
                    "reserved_stock": "Reserved Stock",
                    "effective_stock": "Effective Available",
                    "min_threshold": "Safety Limit"
                })

                st.dataframe(
                    display_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Physical Stock": st.column_config.NumberColumn("Physical Stock", format="%.2f"),
                        "Reserved Stock": st.column_config.NumberColumn("Reserved Stock", format="%.2f"),
                        "Effective Available": st.column_config.NumberColumn("Effective Available", format="%.2f")
                    }
                )
        else:
            st.info("No matching stock items found.")
    else:
        st.info("ℹ️ No inventory items found in database.")
