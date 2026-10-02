from datetime import date, datetime

import pandas as pd
import plotly.express as px  # noqa: F401 (kept for parity)
import streamlit as st

from database import sb


def apply_calm_dashboard_theme():
    """Fluid, responsive CSS optimized for touch + mobile."""
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
            .main .block-container {
                padding-top: 1rem !important;
                padding-bottom: 2rem !important;
                padding-left: 0.5rem !important;
                padding-right: 0.5rem !important;
            }
            div[data-testid="stMetric"] {
                background-color: var(--card-bg);
                border: 1px solid var(--border-color);
                border-left: 4px solid var(--secondary-accent);
                border-radius: 8px;
                padding: 8px 10px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            }
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
            @media (max-width: 640px) {
                div[data-testid="stMetricValue"] { font-size: 1.1rem !important; }
                div[data-testid="stMetricLabel"] { font-size: 0.75rem !important; }
                div[data-testid="stRadio"] > div { flex-direction: column !important; }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def calculate_days_left(due_date_str):
    """Return (days_left_int, display_string)."""
    if not due_date_str:
        return 9999, "Unknown"
    try:
        clean = str(due_date_str).strip().split(" ")[0]
        due_dt = datetime.strptime(clean, "%Y-%m-%d").date()
        today = date.today()
        diff = (due_dt - today).days
        if diff < 0:
            return diff, f"⚠️ Overdue ({abs(diff)}d)"
        elif diff == 0:
            return diff, "⚡ Due Today"
        elif diff == 1:
            return diff, "⏳ 1 day left"
        else:
            return diff, f"⏳ {diff} days left"
    except Exception:
        return 9999, "Unknown"


@st.dialog("📦 Dispatch Detailed Items")
def show_dispatch_modal(dispatch_key, deliveries_df):
    st.write(f"**Reference:** `{dispatch_key}`")
    items = deliveries_df[deliveries_df["dispatch_key"] == dispatch_key][
        ["item_name", "quantity", "requestor", "status"]
    ]
    if not items.empty:
        st.dataframe(items, use_container_width=True, hide_index=True)
    else:
        st.info("No itemized details found for this dispatch.")
    if st.button("Close Details"):
        st.session_state["active_dispatch_modal"] = None
        st.rerun()


def render_dashboard(user_name="Guest", user_role="User"):
    apply_calm_dashboard_theme()
    st.title("📊 Executive Dashboard")

    is_admin = user_role.lower() in ["admin", "manager"] if user_role else False
    st.caption("Real-time inventory, task reminders, and scheduled dispatches.")

    clean_user = str(user_name).strip() if user_name else "Guest"

    deliveries_df = pd.DataFrame()
    reminders_df = pd.DataFrame()

    # ---- 1. Fetch master items ----
    try:
        res = (
            sb()
            .table("master_items")
            .select("id, item_name, category, unit, current_stock, reserved_stock, min_threshold")
            .order("category")
            .order("item_name")
            .execute()
        )
        df = pd.DataFrame(res.data or [])
    except Exception as e:
        st.error(f"Error loading dashboard metrics: {e}")
        return

    if not df.empty:
        df["current_stock"] = df["current_stock"].fillna(0.0)
        df["reserved_stock"] = df["reserved_stock"].fillna(0.0)
        df["min_threshold"] = df["min_threshold"].fillna(0.0)
        df["effective_stock"] = df["current_stock"] - df["reserved_stock"]
    else:
        df = pd.DataFrame(
            columns=["id", "item_name", "category", "unit",
                     "current_stock", "reserved_stock", "min_threshold", "effective_stock"]
        )

    # ---- 2. Pending dispatches ----
    try:
        res = (
            sb()
            .table("deliveries")
            .select("id, dispatch_id, item_name, expected_quantity, unit, expected_date, "
                    "supplier, requested_by, project, created_by, status, notes, is_priority")
            .in_("status", ["Pending", "In Transit"])
            .execute()
        )
        raw_deliveries = res.data or []
    except Exception as e:
        st.warning(f"Could not load dispatches: {e}")
        raw_deliveries = []

    if raw_deliveries:
        deliveries_df = pd.DataFrame(raw_deliveries)
        deliveries_df = deliveries_df.rename(
            columns={
                "expected_quantity": "quantity",
                "expected_date": "due_date",
                "requested_by": "requestor",
                "project": "project_name",
            }
        )
        # Fill missing cols with sensible defaults
        deliveries_df["supplier"] = deliveries_df["supplier"].fillna("Unspecified")
        deliveries_df["project_name"] = deliveries_df["project_name"].fillna("Main Site")
        deliveries_df["requestor"] = deliveries_df["requestor"].fillna("N/A")
        deliveries_df["created_by"] = deliveries_df["created_by"].fillna("System")
        deliveries_df["dispatch_ref"] = deliveries_df["dispatch_id"].fillna("LEGACY")

        # Build a stable grouping key
        deliveries_df["dispatch_key"] = deliveries_df["dispatch_ref"].astype(str)

    # ---- 3. Reminders ----
    try:
        query = (
            sb()
            .table("reminders")
            .select("id, due_date, task, assigned_to, status, priority")
            .in_("status", ["OPEN", "PENDING"])
        )
        if not is_admin:
            query = query.ilike("assigned_to", clean_user)
        res = query.execute()
        reminders_df = pd.DataFrame(res.data or [])
        if not reminders_df.empty and "priority" not in reminders_df.columns:
            reminders_df["priority"] = "NORMAL"
        if reminders_df.empty:
            reminders_df = pd.DataFrame(columns=["id", "due_date", "task", "assigned_to", "status", "priority"])
    except Exception as e:
        st.warning(f"Could not load reminders: {e}")
        reminders_df = pd.DataFrame(columns=["id", "due_date", "task", "assigned_to", "status", "priority"])

    # ---- Metrics ----
    total_items = len(df)
    low_stock_df = df[df["effective_stock"] <= df["min_threshold"]] if not df.empty else pd.DataFrame()
    low_stock_count = len(low_stock_df)
    total_units_stocked = float(df["current_stock"].sum()) if not df.empty else 0.0
    pending_dispatches_count = deliveries_df["dispatch_key"].nunique() if not deliveries_df.empty else 0

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

    # ---- Scheduled Dispatches Log ----
    st.subheader("🚚 Scheduled Dispatches Log")
    use_mobile_cards = st.toggle("📱 Mobile Card View", value=True, key="mobile_card_toggle")

    if not deliveries_df.empty:
        delivery_view_mode = st.radio(
            "Filter View",
            options=["All Dispatches", f"My Dispatches ({clean_user})"],
            index=0,
            key="delivery_filter_radio",
            horizontal=True,
        )

        if delivery_view_mode == f"My Dispatches ({clean_user})":
            filtered = deliveries_df[
                (deliveries_df["requestor"].astype(str).str.lower() == clean_user.lower())
                | (deliveries_df["created_by"].astype(str).str.lower() == clean_user.lower())
            ].copy()
        else:
            filtered = deliveries_df.copy()

        if not filtered.empty:
            grouped = (
                filtered.groupby("dispatch_key")
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
                "dispatch_key", "due_date", "supplier", "project_name",
                "items_summary", "item_count", "total_qty", "requestor", "created_by",
            ]

            parsed = grouped["due_date"].apply(calculate_days_left)
            grouped["days_left_num"] = [d[0] for d in parsed]
            grouped["days_left_str"] = [d[1] for d in parsed]

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
                sort_order = st.radio("Order", ["Asc", "Desc"], key="delivery_sort_order", horizontal=True)

            grouped = grouped.sort_values(by=sort_field, ascending=(sort_order == "Asc"))

            if use_mobile_cards:
                for _, row in grouped.iterrows():
                    st.markdown(
                        f"""
                        <div class="mobile-card">
                            <div class="mobile-card-header">
                                <span class="mobile-card-title">
                                    🚚 {row['supplier']} ({row['project_name']})
                                </span>
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
                display_cols = ["dispatch_key", "due_date", "supplier", "project_name",
                                "items_summary", "item_count", "total_qty", "requestor", "days_left_str"]
                st.dataframe(
                    grouped[display_cols].rename(columns={
                        "dispatch_key": "Dispatch",
                        "due_date": "Due Date",
                        "supplier": "Supplier",
                        "project_name": "Project",
                        "items_summary": "Items",
                        "item_count": "Item Types",
                        "total_qty": "Total Qty",
                        "requestor": "Requestor",
                        "days_left_str": "Days Left",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
        else:
            st.info("No dispatches match the filter.")
    else:
        st.info("No delivery dispatches scheduled yet.")

    st.divider()

    # ---- Active Reminders ----
    st.subheader("📝 Your Active Tasks")
    if not reminders_df.empty:
        rem_view = reminders_df.copy()
        rem_parsed = rem_view["due_date"].apply(calculate_days_left)
        rem_view["days_left_str"] = [d[1] for d in rem_parsed]

        for _, r in rem_view.iterrows():
            p_tag = "🚨" if r.get("priority") == "HIGH" else "🔹"
            st.markdown(
                f"{p_tag} **{r['task']}** — _{r['status']}_ · {r['days_left_str']} · "
                f"assigned to `{r['assigned_to']}`"
            )
    else:
        st.info("No active tasks assigned.")
