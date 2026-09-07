import sqlite3
import uuid
from datetime import datetime, date
import pandas as pd
import streamlit as st
from database import get_db, init_db, backup_db_to_gdrive
from dispatch_card import render_dispatch_card


def ensure_schedule_columns():
    """Ensure Stock Out fields exist on the deliveries table within a single connection."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(deliveries)")
            existing_cols = [col[1] for col in cursor.fetchall()]

            new_cols = {
                "dispatch_id": "TEXT",
                "requested_by": "TEXT",
                "destination": "TEXT",
                "project": "TEXT",
                "is_priority": "INTEGER DEFAULT 0",
                "driver_name": "TEXT",
            }

            for col_name, col_type in new_cols.items():
                if col_name not in existing_cols:
                    cursor.execute(
                        f"ALTER TABLE deliveries ADD COLUMN {col_name} {col_type}"
                    )

            conn.commit()
    except Exception as e:
        st.error(f"Error initializing delivery schema: {e}")


def get_due_status_label(scheduled_date_str):
    """Calculate remaining days, today status, or overdue status."""
    if not scheduled_date_str:
        return "No Date Set"

    try:
        if isinstance(scheduled_date_str, (datetime, date)):
            target_date = (
                scheduled_date_str.date()
                if isinstance(scheduled_date_str, datetime)
                else scheduled_date_str
            )
        else:
            target_date = datetime.strptime(
                str(scheduled_date_str).split()[0], "%Y-%m-%d"
            ).date()

        today = date.today()
        days_left = (target_date - today).days

        if days_left == 0:
            return "📅 Due Today"
        elif days_left < 0:
            return f"⚠️ Overdue ({abs(days_left)} days)"
        else:
            return f"⏳ In {days_left} days"
    except Exception:
        return f"📅 {scheduled_date_str}"


def add_item_to_dispatch(
    dispatch_id, item_name, unit, quantity, notes, first_row
):
    """Helper function to insert a new item into an existing dispatch batch and reserve stock."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO deliveries (
                    dispatch_id, item_name, unit, expected_quantity,
                    expected_date, supplier, destination, requested_by,
                    project, status, is_priority, driver_name, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    dispatch_id,
                    item_name,
                    unit,
                    quantity,
                    first_row["scheduled_date"],
                    first_row["destination"],
                    first_row["destination"],
                    first_row["requested_by"],
                    first_row["project"],
                    first_row["status"],
                    first_row["is_priority"],
                    first_row["driver_name"],
                    notes,
                ),
            )

            # Update reserved stock in master inventory
            cursor.execute(
                """
                UPDATE master_items
                SET reserved_stock = COALESCE(reserved_stock, 0) + ?
                WHERE item_name = ?
            """,
                (quantity, item_name),
            )
            conn.commit()

        backup_db_to_gdrive()
        st.toast(f"Added {item_name} to dispatch batch!", icon="✅")
        st.rerun()
    except Exception as e:
        st.error(f"Error adding item to dispatch: {e}")


def render_schedules(user_name, user_role):
    st.title("🚚 Stock Out Delivery Schedules")
    st.caption(
        "Schedule outbound material dispatches, reserve shop stock, and track project deliveries."
    )

    init_db()
    ensure_schedule_columns()

    if "delivery_cart" not in st.session_state:
        st.session_state.delivery_cart = []

    if "current_dispatch_header" not in st.session_state:
        st.session_state.current_dispatch_header = None

    tab_overview, tab_add = st.tabs(
        [
            "📅 Dispatch Overview",
            "➕ Schedule Stock Out Delivery",
        ]
    )

    # -------------------------------------------------------------
    # TAB 1: OVERVIEW & STATUS MANAGEMENT
    # -------------------------------------------------------------
    with tab_overview:
        st.subheader("Dispatches Overview")
        try:
            with get_db() as conn:
                query = """
                    SELECT id, 
                           COALESCE(dispatch_id, 'LEGACY-' || id) AS dispatch_id,
                           item_name, 
                           COALESCE(requested_by, '') AS requested_by,
                           COALESCE(destination, supplier, '') AS destination,
                           COALESCE(project, '') AS project,
                           expected_quantity AS quantity, unit, 
                           expected_date AS scheduled_date, status, notes,
                           COALESCE(is_priority, 0) AS is_priority,
                           COALESCE(driver_name, '') AS driver_name
                    FROM deliveries 
                    ORDER BY is_priority DESC, expected_date ASC
                """
                df = pd.read_sql_query(query, conn)

            if not df.empty:
                col_status, col_prio, col_search = st.columns(
                    [1, 1, 2]
                )
                with col_status:
                    status_filter = st.selectbox(
                        "Filter Status",
                        [
                            "All",
                            "Pending",
                            "In Transit",
                            "Completed",
                            "Cancelled",
                        ],
                    )
                with col_prio:
                    prio_filter = st.selectbox(
                        "Priority Filter",
                        [
                            "All",
                            "High Priority Only",
                            "Normal Only",
                        ],
                    )
                with col_search:
                    search_query = st.text_input(
                        "🔍 Search Item / Requester / Destination / Driver",
                        placeholder="e.g., DISP-1002, Cement, Main Site...",
                    )

                filtered_df = df.copy()
                if status_filter != "All":
                    filtered_df = filtered_df[
                        filtered_df["status"] == status_filter
                    ]

                if prio_filter == "High Priority Only":
                    filtered_df = filtered_df[
                        filtered_df["is_priority"] == 1
                    ]
                elif prio_filter == "Normal Only":
                    filtered_df = filtered_df[
                        filtered_df["is_priority"] == 0
                    ]

                if search_query.strip():
                    q = search_query.strip().lower()
                    filtered_df = filtered_df[
                        filtered_df["dispatch_id"]
                        .str.lower()
                        .str.contains(q, na=False)
                        | filtered_df["item_name"]
                        .str.lower()
                        .str.contains(q, na=False)
                        | filtered_df["requested_by"]
                        .str.lower()
                        .str.contains(q, na=False)
                        | filtered_df["destination"]
                        .str.lower()
                        .str.contains(q, na=False)
                        | filtered_df["project"]
                        .str.lower()
                        .str.contains(q, na=False)
                        | filtered_df["driver_name"]
                        .str.lower()
                        .str.contains(q, na=False)
                    ]

                st.divider()

                active_df = filtered_df[
                    filtered_df["status"].isin(["Pending", "In Transit"])
                ]
                completed_df = filtered_df[
                    filtered_df["status"].isin(
                        ["Completed", "Cancelled"]
                    )
                ]

                col_active, col_completed = st.columns(2)

                with col_active:
                    active_dispatches = active_df.groupby(
                        "dispatch_id", sort=False
                    )
                    st.markdown(
                        f"### 🚚 Active Dispatches ({len(active_dispatches)})"
                    )
                    st.caption("Pending or In Transit Dispatches")
                    st.divider()

                    if not active_df.empty:
                        for disp_id, group in active_dispatches:
                            render_dispatch_card(
                                disp_id,
                                group,
                                get_due_status_label,
                                add_item_to_dispatch,
                            )
                    else:
                        st.info("No active dispatches found.")

                with col_completed:
                    completed_dispatches = completed_df.groupby(
                        "dispatch_id", sort=False
                    )
                    st.markdown(
                        f"### ✅ Completed & History ({len(completed_dispatches)})"
                    )
                    st.caption("Finished or Cancelled Dispatches")
                    st.divider()

                    if not completed_df.empty:
                        for disp_id, group in completed_dispatches:
                            render_dispatch_card(
                                disp_id,
                                group,
                                get_due_status_label,
                                add_item_to_dispatch,
                            )
                    else:
                        st.info(
                            "No completed or cancelled dispatches found."
                        )

            else:
                st.info("No delivery dispatches scheduled yet.")
        except Exception as e:
            st.error(f"Error loading delivery dispatches: {e}")

    # -------------------------------------------------------------
    # TAB 2: SCHEDULE NEW STOCK OUT DELIVERY (RESERVE STOCK)
    # -------------------------------------------------------------
    with tab_add:
        st.subheader("Schedule New Single Dispatch Batch")

        try:
            with get_db() as conn_items:
                df_master = pd.read_sql_query(
                    """
                    SELECT item_name, unit, current_stock, 
                           COALESCE(reserved_stock, 0) AS reserved_stock,
                           (current_stock - COALESCE(reserved_stock, 0)) AS available_stock
                    FROM master_items 
                    ORDER BY item_name ASC
                """,
                    conn_items,
                )

            if not df_master.empty:
                has_active_batch = bool(st.session_state.delivery_cart)
                header_data = (
                    st.session_state.current_dispatch_header or {}
                )

                selected_item_name = st.selectbox(
                    "Select Item to Add to Dispatch*",
                    df_master["item_name"].tolist(),
                )
                item_info = df_master[
                    df_master["item_name"] == selected_item_name
                ].iloc[0]

                stock_in_shop = float(item_info["current_stock"])
                stock_reserved = float(item_info["reserved_stock"])

                staged_qty = sum(
                    item["quantity"]
                    for item in st.session_state.delivery_cart
                    if item["item_name"] == selected_item_name
                )
                stock_available = (
                    float(item_info["available_stock"]) - staged_qty
                )
                unit_name = str(item_info["unit"])

                m1, m2, m3 = st.columns(3)
                m1.metric(
                    "Stock In Shop (Total)",
                    f"{stock_in_shop:,.2f} {unit_name}",
                )
                m2.metric(
                    "Reserved Stock",
                    f"{stock_reserved:,.2f} {unit_name}",
                )
                m3.metric(
                    "Available Stock",
                    f"{stock_available:,.2f} {unit_name}",
                )

                st.divider()

                with st.form(
                    "add_dispatch_item_form", clear_on_submit=True
                ):
                    if has_active_batch:
                        st.info(
                            f"🔒 **Dispatch Order Locked:** Adding additional items to batch for **{header_data.get('requested_by')}** ➡️ **{header_data.get('destination')}** ({header_data.get('project')})"
                        )
                    else:
                        st.markdown("##### 📄 1. Dispatch Order Details")
                        col1, col2 = st.columns(2)
                        with col1:
                            input_requested_by = st.text_input(
                                "Requested By*",
                                placeholder="e.g., Engr. John Doe",
                            )
                            input_destination = st.text_input(
                                "Destination / Site Location*",
                                placeholder="e.g., Block 4 Site",
                            )
                            input_project = st.text_input(
                                "Project Name / Code*",
                                placeholder="e.g., PRJ-2026-A",
                            )

                    # Form items continue here...
            else:
                st.info(
                    "No items available in Master Inventory to schedule dispatches."
                )
        except Exception as e:
            st.error(f"Error loading master items form: {e}")
