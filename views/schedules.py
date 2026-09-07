import uuid
from datetime import date, datetime
import pandas as pd
import streamlit as st

from components.dispatch_card import (
    add_item_to_dispatch,
    ensure_schedule_columns,
    get_due_status_label,
    render_dispatch_card,
)
from database import backup_db_to_gdrive, get_db, init_db, save_dispatch_batch


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
                # Optimized controls layout: collapse filters into an expander for clean mobile viewing
                with st.expander("🔍 Filter & Search Options", expanded=False):
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
                    prio_filter = st.selectbox(
                        "Priority Filter",
                        [
                            "All",
                            "High Priority Only",
                            "Normal Only",
                        ],
                    )
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

                # Use mobile-friendly sub-tabs instead of cramped side-by-side columns
                tab_active, tab_history = st.tabs(
                    [
                        f"🚚 Active ({len(active_df.groupby('dispatch_id', sort=False))})",
                        f"✅ History ({len(completed_df.groupby('dispatch_id', sort=False))})",
                    ]
                )

                with tab_active:
                    st.caption("Pending or In Transit Dispatches")
                    active_dispatches = active_df.groupby(
                        "dispatch_id", sort=False
                    )

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

                with tab_history:
                    st.caption("Finished or Cancelled Dispatches")
                    completed_dispatches = completed_df.groupby(
                        "dispatch_id", sort=False
                    )

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

                # Metrics render naturally stacked on small screens
                m1, m2, m3 = st.columns([1, 1, 1])
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
                        # Single column vertical flow for mobile readability
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
                        input_scheduled_date = st.date_input(
                            "Scheduled Delivery Date*",
                            value=date.today(),
                        )
                        input_is_priority = st.checkbox(
                            "🔥 Mark as High Priority Dispatch"
                        )

                    st.markdown("##### 📦 2. Item Details")
                    input_quantity = st.number_input(
                        f"Dispatch Quantity ({unit_name})*",
                        min_value=0.01,
                        value=1.0,
                        step=1.0,
                    )
                    input_notes = st.text_input(
                        "Item Notes / Handling Instructions",
                        placeholder="Optional site notes, batch specs...",
                    )

                    btn_add_to_cart = st.form_submit_button(
                        "➕ Add Item to Dispatch Batch",
                        type="primary",
                        use_container_width=True,
                    )

                if btn_add_to_cart:
                    if input_quantity > stock_available:
                        st.error(
                            f"Cannot stage {input_quantity:.2f} {unit_name}. Only {stock_available:.2f} {unit_name} is available."
                        )
                    else:
                        if not has_active_batch:
                            if not input_requested_by.strip() or not input_destination.strip():
                                st.error(
                                    "Please fill in all required fields marked with *."
                                )
                                st.stop()

                            st.session_state.current_dispatch_header = {
                                "dispatch_id": f"DISP-{uuid.uuid4().hex[:6].upper()}",
                                "requested_by": input_requested_by.strip(),
                                "destination": input_destination.strip(),
                                "project": input_project.strip() or "N/A",
                                "scheduled_date": str(input_scheduled_date),
                                "created_by": user_name,
                                "is_priority": 1 if input_is_priority else 0,
                            }

                        st.session_state.delivery_cart.append(
                            {
                                "item_name": selected_item_name,
                                "unit": unit_name,
                                "quantity": input_quantity,
                                "notes": input_notes.strip(),
                            }
                        )
                        st.toast(
                            f"Added {selected_item_name} to staging batch!",
                            icon="🛒",
                        )
                        st.rerun()

                # Staging area display & save block
                if st.session_state.delivery_cart:
                    st.divider()
                    st.markdown("### 🛒 Staged Dispatch Batch")

                    hdr = st.session_state.current_dispatch_header
                    st.caption(
                        f"**Batch ID:** `{hdr['dispatch_id']}` | **Requester:** {hdr['requested_by']} | **Destination:** {hdr['destination']} | **Date:** {hdr['scheduled_date']}"
                    )

                    cart_df = pd.DataFrame(st.session_state.delivery_cart)
                    st.dataframe(cart_df, use_container_width=True)

                    # Full width stacked buttons for primary touchscreen actions
                    if st.button(
                        "💾 Confirm & Create Dispatch Order",
                        type="primary",
                        use_container_width=True,
                    ):
                        try:
                            # Call the database helper function with created_by
                            save_dispatch_batch(
                                st.session_state.current_dispatch_header,
                                st.session_state.delivery_cart,
                                created_by=user_name,
                            )

                            # Sync database backup
                            backup_db_to_gdrive()

                            # Reset session state variables
                            st.session_state.delivery_cart = []
                            st.session_state.current_dispatch_header = None

                            st.success(
                                f"Successfully created dispatch order `{hdr['dispatch_id']}`!"
                            )
                            st.rerun()

                        except Exception as e:
                            st.error(f"Error creating dispatch order: {e}")

                    if st.button(
                        "🗑️ Clear Batch Staging",
                        use_container_width=True,
                    ):
                        st.session_state.delivery_cart = []
                        st.session_state.current_dispatch_header = None
                        st.rerun()

            else:
                st.info(
                    "No items available in Master Inventory to schedule dispatches."
                )
        except Exception as e:
            st.error(f"Error loading master items form: {e}")
