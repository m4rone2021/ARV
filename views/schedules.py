# views/schedules.py
import sqlite3
from datetime import datetime, date
import pandas as pd
import streamlit as st
from database import get_db, init_db

def calculate_days_left(due_date_str):
    """Calculate days remaining from today until the delivery due date."""
    if not due_date_str:
        return 9999, "No Due Date"
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

def ensure_schedule_columns():
    """Ensure Stock Out fields exist on the deliveries table."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(deliveries)")
            existing_cols = [col[1] for col in cursor.fetchall()]

            new_cols = {
                "requested_by": "TEXT",
                "destination": "TEXT",
                "project": "TEXT",
                "is_priority": "INTEGER DEFAULT 0"
            }

            for col_name, col_type in new_cols.items():
                if col_name not in existing_cols:
                    cursor.execute(f"ALTER TABLE deliveries ADD COLUMN {col_name} {col_type}")

            conn.commit()
    except Exception as e:
        st.error(f"Error initializing delivery schema: {e}")

def render_schedules(user_name, user_role):
    st.title("🚚 Stock Out Delivery Schedules")
    st.caption("Schedule outbound material dispatches, reserve shop stock, and track project deliveries.")

    init_db()
    ensure_schedule_columns()

    tab_overview, tab_add = st.tabs([
        "📅 Dispatch Overview", 
        "➕ Schedule Stock Out Delivery"
    ])

    # -------------------------------------------------------------
    # TAB 1: OVERVIEW & STATUS MANAGEMENT
    # -------------------------------------------------------------
    with tab_overview:
        st.subheader("Upcoming & Active Dispatches")
        try:
            with get_db() as conn:
                query = """
                    SELECT id, item_name, 
                           COALESCE(requested_by, '') AS requested_by,
                           COALESCE(destination, supplier, '') AS destination,
                           COALESCE(project, '') AS project,
                           expected_quantity AS quantity, unit, 
                           expected_date AS scheduled_date, status, notes,
                           COALESCE(is_priority, 0) AS is_priority
                    FROM deliveries 
                """
                df = pd.read_sql_query(query, conn)

            if not df.empty:
                # Calculate Days Remaining & Overdue status
                days_left_results = df["scheduled_date"].apply(calculate_days_left)
                df["days_diff"] = [res[0] for res in days_left_results]
                df["time_status"] = [res[1] for res in days_left_results]

                # Priority Sorting: 
                # 1. Active Pending/In Transit Overdue items first
                # 2. High priority
                # 3. Closest due dates
                df = df.sort_values(
                    by=["days_diff", "is_priority"], 
                    ascending=[True, False]
                )

                col_status, col_prio, col_search = st.columns([1, 1, 2])
                with col_status:
                    status_filter = st.selectbox("Filter Status", ["All Active", "Pending", "In Transit", "Completed", "Cancelled"])
                with col_prio:
                    prio_filter = st.selectbox("Priority / Timeline Filter", ["All", "High Priority Only", "Overdue Dispatches Only", "Normal Only"])
                with col_search:
                    search_query = st.text_input("🔍 Search Item / Requested By / Destination / Project", placeholder="e.g., Cement, Main Site, Engr. Alex...")

                filtered_df = df.copy()
                if status_filter == "All Active":
                    filtered_df = filtered_df[filtered_df["status"].isin(["Pending", "In Transit"])]
                elif status_filter != "All":
                    filtered_df = filtered_df[filtered_df["status"] == status_filter]
                
                if prio_filter == "High Priority Only":
                    filtered_df = filtered_df[filtered_df["is_priority"] == 1]
                elif prio_filter == "Overdue Dispatches Only":
                    filtered_df = filtered_df[(filtered_df["days_diff"] < 0) & (filtered_df["status"].isin(["Pending", "In Transit"]))]
                elif prio_filter == "Normal Only":
                    filtered_df = filtered_df[filtered_df["is_priority"] == 0]

                if search_query.strip():
                    q = search_query.strip().lower()
                    filtered_df = filtered_df[
                        filtered_df["item_name"].str.lower().str.contains(q, na=False) |
                        filtered_df["requested_by"].str.lower().str.contains(q, na=False) |
                        filtered_df["destination"].str.lower().str.contains(q, na=False) |
                        filtered_df["project"].str.lower().str.contains(q, na=False)
                    ]

                st.divider()

                for idx, row in filtered_df.iterrows():
                    prio_badge = "🔥 HIGH PRIORITY | " if row['is_priority'] == 1 else ""
                    project_info = f" ({row['project']})" if row['project'] else ""
                    time_badge = f" | {row['time_status']}" if row['status'] in ["Pending", "In Transit"] else ""

                    header_label = f"{prio_badge}📦 {row['item_name']} - Due: {row['scheduled_date']}{time_badge} [{row['status']}] -> {row['destination']}{project_info}"
                    
                    with st.expander(header_label):
                        c1, c2, c3 = st.columns(3)
                        c1.markdown(f"**Requested By:** {row['requested_by'] if row['requested_by'] else 'N/A'}")
                        c1.markdown(f"**Destination:** {row['destination']}")
                        
                        c2.markdown(f"**Project:** {row['project'] if row['project'] else 'N/A'}")
                        c2.markdown(f"**Quantity:** {row['quantity']} {row['unit']}")
                        
                        c3.markdown(f"**Due Date:** `{row['scheduled_date']}`")
                        c3.markdown(f"**Timeline Status:** {row['time_status']}")
                        c3.markdown(f"**Priority:** {'🔴 **HIGH**' if row['is_priority'] == 1 else '🟢 Normal'}")

                        if row["notes"]:
                            st.caption(f"**Notes:** {row['notes']}")

                        status_options = ["Pending", "In Transit", "Completed", "Cancelled"]
                        current_idx = status_options.index(row["status"]) if row["status"] in status_options else 0

                        col_sel, col_btn = st.columns([2, 1])
                        with col_sel:
                            new_status = st.selectbox(
                                "Update Status", 
                                status_options, 
                                index=current_idx,
                                key=f"status_select_{row['id']}"
                            )

                        if new_status != row["status"]:
                            with col_btn:
                                st.write("") # Alignment spacing
                                if st.button("Save Status", key=f"btn_status_{row['id']}"):
                                    try:
                                        with get_db() as conn_update:
                                            cursor = conn_update.cursor()
                                            old_status = row["status"]
                                            qty = float(row["quantity"])
                                            item_name = row["item_name"]

                                            # Update Delivery Record Status
                                            cursor.execute("UPDATE deliveries SET status = ? WHERE id = ?", (new_status, row['id']))

                                            # Adjust Stock based on Status Transitions
                                            if old_status in ["Pending", "In Transit"]:
                                                if new_status == "Completed":
                                                    # Deduct physical stock and release reservation
                                                    cursor.execute("""
                                                        UPDATE master_items 
                                                        SET current_stock = current_stock - ?,
                                                            reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?)
                                                        WHERE item_name = ?
                                                    """, (qty, qty, item_name))

                                                elif new_status == "Cancelled":
                                                    # Release reservation back to available stock
                                                    cursor.execute("""
                                                        UPDATE master_items 
                                                        SET reserved_stock = MAX(0, COALESCE(reserved_stock, 0) - ?)
                                                        WHERE item_name = ?
                                                    """, (qty, item_name))

                                            conn_update.commit()
                                            st.success(f"Status updated to {new_status} and inventory adjusted accordingly!")
                                            st.rerun()
                                    except Exception as e:
                                        st.error(f"Error updating delivery status: {e}")
            else:
                st.info("No delivery dispatches scheduled yet.")
        except Exception as e:
            st.error(f"Error loading delivery dispatches: {e}")

    # -------------------------------------------------------------
    # TAB 2: SCHEDULE NEW STOCK OUT DELIVERY (RESERVE STOCK)
    # -------------------------------------------------------------
    with tab_add:
        st.subheader("Schedule New Stock Out Delivery")

        try:
            with get_db() as conn_items:
                df_master = pd.read_sql_query("""
                    SELECT item_name, unit, current_stock, 
                           COALESCE(reserved_stock, 0) AS reserved_stock,
                           (current_stock - COALESCE(reserved_stock, 0)) AS available_stock
                    FROM master_items 
                    ORDER BY item_name ASC
                """, conn_items)

            if not df_master.empty:
                selected_item_name = st.selectbox("Select Item to Dispatch*", df_master["item_name"].tolist())
                item_info = df_master[df_master["item_name"] == selected_item_name].iloc[0]

                stock_in_shop = float(item_info["current_stock"])
                stock_reserved = float(item_info["reserved_stock"])
                stock_available = float(item_info["available_stock"])
                unit_name = str(item_info["unit"])

                # Metric visualizer
                m1, m2, m3 = st.columns(3)
                m1.metric("Stock In Shop (Total)", f"{stock_in_shop:,.2f} {unit_name}")
                m2.metric("Reserved Stock", f"{stock_reserved:,.2f} {unit_name}")
                m3.metric("Available Stock", f"{stock_available:,.2f} {unit_name}")

                st.divider()

                with st.form("add_delivery_form", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    with col1:
                        requested_by = st.text_input("Requested By*", placeholder="e.g., Engr. John Doe").strip()
                        destination = st.text_input("Destination / Site Location*", placeholder="e.g., Block 4 Site").strip()
                        project = st.text_input("Project Name / Code*", placeholder="e.g., Bridge Construction Phase 1").strip()
                    
                    with col2:
                        quantity = st.number_input(f"Quantity to Reserve ({unit_name})*", min_value=0.01, value=None, placeholder="0.0")
                        scheduled_date = st.date_input("Scheduled Delivery Date")
                        status = st.selectbox("Initial Status", ["Pending", "In Transit"])

                    is_priority = st.checkbox("🔥 Mark as High Priority Delivery", help="High priority stock out deliveries appear prominently at the top of dispatches.")
                    notes = st.text_input("Notes / Delivery Instructions", placeholder="e.g., Deliver via 10-wheeler truck; contact site engineer upon arrival")
                    
                    submit_btn = st.form_submit_button("📅 Schedule Stock Out & Reserve Inventory", use_container_width=True)

                    if submit_btn:
                        if not requested_by or not destination or not project or quantity is None:
                            st.error("⚠️ Requested By, Destination, Project, and Quantity are required fields.")
                        elif quantity > stock_available:
                            st.error(f"❌ Cannot reserve stock! Requested Quantity ({quantity} {unit_name}) exceeds Available Stock ({stock_available} {unit_name}).")
                        else:
                            try:
                                with get_db() as conn_add:
                                    cursor = conn_add.cursor()
                                    
                                    priority_val = 1 if is_priority else 0

                                    # 1. Save Stock Out Delivery Record
                                    cursor.execute("""
                                        INSERT INTO deliveries (
                                            item_name, supplier, requested_by, destination, project, 
                                            expected_quantity, unit, expected_date, status, notes, is_priority
                                        )
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """, (
                                        selected_item_name, destination, requested_by, destination, project,
                                        quantity, unit_name, str(scheduled_date), status, notes.strip(), priority_val
                                    ))

                                    # 2. Increase Reserved Stock on Master Item
                                    cursor.execute("""
                                        UPDATE master_items
                                        SET reserved_stock = COALESCE(reserved_stock, 0) + ?
                                        WHERE item_name = ?
                                    """, (quantity, selected_item_name))

                                    conn_add.commit()
                                    st.success(f"✅ Stock Out for **{selected_item_name}** scheduled to **{destination}** ({project}) and {quantity} {unit_name} reserved!")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Failed to create schedule: {e}")
            else:
                st.warning("⚠️ No master items found. Please add items to the Master Catalog first.")

        except Exception as e:
            st.error(f"Error fetching catalog items: {e}")
