import uuid
from datetime import date

import pandas as pd
import streamlit as st

from components.dispatch_card import (
    add_item_to_dispatch,
    get_due_status_label,
    render_dispatch_card,
)
from database import sb


def render_schedules(user_name, user_role):
    st.title("🚚 Stock Out Delivery Schedules")
    st.caption(
        "Schedule outbound material dispatches, reserve shop stock, and track project deliveries."
    )

    if "delivery_cart" not in st.session_state:
        st.session_state.delivery_cart = []
    if "current_dispatch_header" not in st.session_state:
        st.session_state.current_dispatch_header = None

    tab_overview, tab_add = st.tabs(
        ["📅 Dispatch Overview", "➕ Schedule Stock Out Delivery"]
    )

    # ================================================================
    # TAB 1: OVERVIEW
    # ================================================================
    with tab_overview:
        st.subheader("Dispatches Overview")
        try:
            query = (
                sb()
                .table("deliveries")
                .select("id, dispatch_id, item_name, requested_by, destination, project, "
                        "expected_quantity, unit, expected_date, scheduled_date, status, notes, "
                        "is_priority, driver_name, created_by")
            )
            if user_role != "Admin":
                query = query.or_(
                    f"created_by.eq.{user_name},requested_by.eq.{user_name}"
                )
            res = query.execute()
            df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error loading delivery dispatches: {e}")
            return

        if df.empty:
            st.info("No delivery dispatches scheduled yet.")
        else:
            df = df.rename(columns={
                "expected_quantity": "quantity",
                "expected_date": "scheduled_date_tmp",
            })
            # Prefer scheduled_date over expected_date
            df["scheduled_date"] = df["scheduled_date"].fillna(df["scheduled_date_tmp"])
            df["dispatch_id"] = df["dispatch_id"].fillna("LEGACY-" + df["id"].astype(str))
            df["is_priority"] = df["is_priority"].fillna(False)
            df["created_by"] = df["created_by"].fillna("System")
            df["requested_by"] = df["requested_by"].fillna("")
            df["destination"] = df["destination"].fillna("")
            df["project"] = df["project"].fillna("")
            df["driver_name"] = df["driver_name"].fillna("")

            with st.expander("🔍 Filter & Search Options", expanded=False):
                status_filter = st.selectbox(
                    "Filter Status", ["All", "Pending", "In Transit", "Completed", "Cancelled"]
                )
                prio_filter = st.selectbox(
                    "Priority Filter", ["All", "High Priority Only", "Normal Only"]
                )
                search_query = st.text_input(
                    "🔍 Search Item / Requester / Destination / Driver",
                    placeholder="e.g., DISP-1002, Cement, Main Site...",
                )

            filtered_df = df.copy()
            if status_filter != "All":
                filtered_df = filtered_df[filtered_df["status"] == status_filter]
            if prio_filter == "High Priority Only":
                filtered_df = filtered_df[filtered_df["is_priority"] == True]  # noqa: E712
            elif prio_filter == "Normal Only":
                filtered_df = filtered_df[filtered_df["is_priority"] == False]  # noqa: E712
            if search_query.strip():
                q = search_query.strip().lower()
                filtered_df = filtered_df[
                    filtered_df["dispatch_id"].astype(str).str.lower().str.contains(q, na=False)
                    | filtered_df["item_name"].astype(str).str.lower().str.contains(q, na=False)
                    | filtered_df["requested_by"].astype(str).str.lower().str.contains(q, na=False)
                    | filtered_df["destination"].astype(str).str.lower().str.contains(q, na=False)
                    | filtered_df["project"].astype(str).str.lower().str.contains(q, na=False)
                    | filtered_df["driver_name"].astype(str).str.lower().str.contains(q, na=False)
                ]

            st.divider()

            active_df = filtered_df[filtered_df["status"].isin(["Pending", "In Transit"])]
            completed_df = filtered_df[filtered_df["status"].isin(["Completed", "Cancelled"])]

            tab_active, tab_history = st.tabs(
                [
                    f"🚚 Active ({len(active_df.groupby('dispatch_id', sort=False))})",
                    f"✅ History ({len(completed_df.groupby('dispatch_id', sort=False))})",
                ]
            )

            with tab_active:
                st.caption("Pending or In Transit Dispatches")
                if not active_df.empty:
                    for disp_id, group in active_df.groupby("dispatch_id", sort=False):
                        render_dispatch_card(
                            disp_id, group, get_due_status_label, add_item_to_dispatch
                        )
                else:
                    st.info("No active dispatches found.")

            with tab_history:
                st.caption("Finished or Cancelled Dispatches")
                if not completed_df.empty:
                    for disp_id, group in completed_df.groupby("dispatch_id", sort=False):
                        render_dispatch_card(
                            disp_id, group, get_due_status_label, add_item_to_dispatch
                        )
                else:
                    st.info("No completed or cancelled dispatches found.")

    # ================================================================
    # TAB 2: NEW DISPATCH
    # ================================================================
    with tab_add:
        st.subheader("Schedule New Single Dispatch Batch")

        try:
            res = (
                sb()
                .table("master_items")
                .select("item_name, unit, current_stock, reserved_stock")
                .order("item_name")
                .execute()
            )
            df_master = pd.DataFrame(res.data or [])
            if not df_master.empty:
                df_master["reserved_stock"] = df_master["reserved_stock"].fillna(0)
                df_master["current_stock"] = df_master["current_stock"].fillna(0)
                df_master["available_stock"] = df_master["current_stock"] - df_master["reserved_stock"]
        except Exception as e:
            st.error(f"Error loading master items form: {e}")
            return

        if df_master.empty:
            st.info("No items available in Master Inventory to schedule dispatches.")
            return

        has_active_batch = bool(st.session_state.delivery_cart)
        header_data = st.session_state.current_dispatch_header or {}

        selected_item_name = st.selectbox("Select Item to Add to Dispatch*", df_master["item_name"].tolist())
        item_info = df_master[df_master["item_name"] == selected_item_name].iloc[0]

        stock_in_shop = float(item_info["current_stock"])
        stock_reserved = float(item_info["reserved_stock"])
        staged_qty = sum(
            item["quantity"]
            for item in st.session_state.delivery_cart
            if item["item_name"] == selected_item_name
        )
        stock_available = float(item_info["available_stock"]) - staged_qty
        unit_name = str(item_info["unit"])

        m1, m2, m3 = st.columns([1, 1, 1])
        m1.metric("Stock In Shop (Total)", f"{stock_in_shop:,.2f} {unit_name}")
        m2.metric("Reserved Stock", f"{stock_reserved:,.2f} {unit_name}")
        m3.metric("Available Stock", f"{stock_available:,.2f} {unit_name}")

        st.divider()

        with st.form("add_dispatch_item_form", clear_on_submit=True):
            if has_active_batch:
                st.info(
                    f"🔒 **Dispatch Order Locked:** Adding items to batch for "
                    f"**{header_data.get('requested_by')}** ➡️ "
                    f"**{header_data.get('destination')}** ({header_data.get('project')})"
                )
            else:
                st.markdown("##### 📄 1. Dispatch Order Details")
                input_requested_by = st.text_input("Requested By*", placeholder="e.g., Engr. John Doe")
                input_destination = st.text_input("Destination / Site Location*", placeholder="e.g., Block 4 Site")
                input_project = st.text_input("Project Name / Code*", placeholder="e.g., PRJ-2026-A")
                input_scheduled_date = st.date_input("Scheduled Delivery Date*", value=date.today())
                input_is_priority = st.checkbox("🔥 Mark as High Priority Dispatch")

            st.markdown("##### 📦 2. Item Details")
            input_quantity = st.number_input(
                f"Dispatch Quantity ({unit_name})*", min_value=0.01, value=1.0, step=1.0
            )
            input_notes = st.text_input("Item Notes / Handling Instructions", placeholder="Optional")

            btn_add_to_cart = st.form_submit_button(
                "➕ Add Item to Dispatch Batch", type="primary", use_container_width=True
            )

        if btn_add_to_cart:
            if input_quantity > stock_available:
                st.error(
                    f"Cannot stage {input_quantity:.2f} {unit_name}. Only {stock_available:.2f} {unit_name} is available."
                )
            else:
                if not has_active_batch:
                    if not input_requested_by.strip() or not input_destination.strip():
                        st.error("Please fill in all required fields marked with *.")
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

                st.session_state.delivery_cart.append({
                    "item_name": selected_item_name,
                    "unit": unit_name,
                    "quantity": input_quantity,
                    "notes": input_notes.strip(),
                })
                st.toast(f"Added {selected_item_name} to staging batch!", icon="🛒")
                st.rerun()

        if st.session_state.delivery_cart:
            st.divider()
            st.markdown("### 🛒 Staged Dispatch Batch")

            hdr = st.session_state.current_dispatch_header
            st.caption(
                f"**Batch ID:** `{hdr['dispatch_id']}` | **Requester:** {hdr['requested_by']} | "
                f"**Destination:** {hdr['destination']} | **Date:** {hdr['scheduled_date']}"
            )

            cart_df = pd.DataFrame(st.session_state.delivery_cart)
            st.dataframe(cart_df, use_container_width=True)

            if st.button("💾 Confirm & Create Dispatch Order", type="primary", use_container_width=True):
                try:
                    rows = []
                    for item in st.session_state.delivery_cart:
                        rows.append({
                            "dispatch_id": hdr["dispatch_id"],
                            "item_name": item["item_name"],
                            "unit": item["unit"],
                            "expected_quantity": float(item["quantity"]),
                            "expected_date": hdr["scheduled_date"],
                            "scheduled_date": hdr["scheduled_date"],
                            "destination": hdr["destination"],
                            "requested_by": hdr["requested_by"],
                            "project": hdr["project"],
                            "status": "Pending",
                            "is_priority": bool(hdr.get("is_priority", 0)),
                            "notes": item.get("notes", ""),
                            "created_by": user_name,
                        })
                    sb().table("deliveries").insert(rows).execute()

                    # Reserve stock
                    by_item = {}
                    for item in st.session_state.delivery_cart:
                        by_item[item["item_name"]] = (
                            by_item.get(item["item_name"], 0.0) + float(item["quantity"])
                        )
                    for iname, qty in by_item.items():
                        cur = sb().table("master_items").select("reserved_stock").eq("item_name", iname).limit(1).execute()
                        if cur.data:
                            new_reserved = float(cur.data[0].get("reserved_stock") or 0.0) + qty
                            sb().table("master_items").update({"reserved_stock": new_reserved}).eq("item_name", iname).execute()

                    st.session_state.delivery_cart = []
                    st.session_state.current_dispatch_header = None
                    st.success(f"Successfully created dispatch order `{hdr['dispatch_id']}`!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error creating dispatch order: {e}")

            if st.button("🗑️ Clear Batch Staging", use_container_width=True):
                st.session_state.delivery_cart = []
                st.session_state.current_dispatch_header = None
                st.rerun()
