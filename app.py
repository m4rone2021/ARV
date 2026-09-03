import sqlite3
import json
import os
from datetime import datetime, time
import pandas as pd
import streamlit as st

# Initialize Streamlit Page Config
st.set_page_config(page_title="Inventory Management", layout="wide")

# Database connection setup
conn = sqlite3.connect("inventory.db", check_same_thread=False)
cursor = conn.cursor()

# Dummy session state initializations if not set
if "user_name" not in st.session_state:
    st.session_state["user_name"] = "Supervisor Admin"
if "selected_menu" not in st.session_state:
    st.session_state["selected_menu"] = "📤 Stock Out"

user_name = st.session_state["user_name"]
selected_menu = st.session_state["selected_menu"]
item_selected = "Sample Item"
qty_out = 1.0
issued_to = "Site Team"

def create_notification(message, target_role=None, target_user=None):
    """Helper function to log system notifications."""
    pass

def generate_excel_report(user_name, date_str, df_tx, df_stock):
    """Helper function stub for Excel export."""
    return b""

# --- MAIN CONTROLLER / ROUTING ---
if selected_menu == "📤 Stock Out":
    driver_out = st.text_input("Driver / Transport Vehicle", placeholder="e.g. Driver Bob (Dump Truck #02)", key="out_driver")
    project_name = st.text_input("Project Name / Phase", placeholder="e.g. Bridge Abutment - Sector A", key="out_project")
    purpose = st.text_input("Purpose / Equipment Usage", placeholder="e.g. Concrete formwork framing", key="out_purpose")

    st.markdown("### 📷 Withdrawal Slip / Issue Proof Photo")
    photo_mode = st.radio("Choose Photo Upload Method:", ["Camera Capture", "Upload File"], horizontal=True, key="out_photo_mode")

    image_bytes = None
    if photo_mode == "Camera Capture":
        camera_photo = st.camera_input("Take a picture of signed withdrawal slip", key="out_camera")
        if camera_photo:
            image_bytes = camera_photo.getvalue()
    else:
        uploaded_file = st.file_uploader("Upload Withdrawal Slip / Photo Proof", type=["jpg", "jpeg", "png"], key="out_upload")
        if uploaded_file:
            image_bytes = uploaded_file.getvalue()

    if st.button("Submit Stock Out", use_container_width=True):
        res = cursor.execute("SELECT current_stock FROM master_items WHERE item_name = ?", (item_selected,)).fetchone()
        current_stock = res[0] if res else 0.0

        if qty_out > current_stock:
            st.error(f"Insufficient stock! Available balance: {current_stock:,.2f}")
        else:
            saved_photo_path = None
            if image_bytes:
                os.makedirs("uploads", exist_ok=True)
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_filename = f"uploads/issuance_{timestamp_str}.jpg"
                with open(file_filename, "wb") as f:
                    f.write(image_bytes)
                saved_photo_path = file_filename

            new_stock = current_stock - qty_out
            cursor.execute("UPDATE master_items SET current_stock = ? WHERE item_name = ?", (new_stock, item_selected))
            cursor.execute("""
                INSERT INTO transactions (timestamp, item_name, type, quantity, user_role, driver_details, issued_to, project_name, purpose, photo_path) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item_selected, "OUT", qty_out, user_name, driver_out, issued_to, project_name, purpose, saved_photo_path))
            conn.commit()

            res_thresh = cursor.execute("SELECT min_threshold FROM master_items WHERE item_name = ?", (item_selected,)).fetchone()
            min_thresh = res_thresh[0] if res_thresh else 0.0
            
            if new_stock <= min_thresh:
                create_notification(
                    f"⚠️ Low Stock Alert: {item_selected} dropped to {new_stock:,.2f} (Threshold: {min_thresh:,.2f})",
                    target_role="Head Office"
                )

            st.success(f"Successfully issued {qty_out} of {item_selected}!")
            st.rerun()

elif selected_menu == "📜 My Log & Request Edits":
    st.subheader("📜 My Logged Transactions & Edit Requests")

    df_my_tx = pd.read_sql_query(
        "SELECT * FROM transactions WHERE user_role = ? ORDER BY id DESC", 
        conn, params=(user_name,)
    )

    if not df_my_tx.empty:
        st.dataframe(df_my_tx, use_container_width=True, hide_index=True)
        st.markdown("---")
        st.markdown("### ✏️ Request Transaction Edit")
        
        tx_ids = df_my_tx['id'].tolist()
        selected_tx_id = st.selectbox("Select Transaction ID to Edit", tx_ids)
        
        tx_row = df_my_tx[df_my_tx['id'] == selected_tx_id].iloc[0]
        st.info(f"Editing Transaction ID #{selected_tx_id} — Current Item: **{tx_row['item_name']}** ({tx_row['type']})")

        with st.form("edit_request_form"):
            new_qty = st.number_input("Proposed Quantity", value=float(tx_row['quantity']), min_value=0.1)
            new_issued_to = st.text_input("Proposed Recipient / Issued To", value=str(tx_row['issued_to'] or ''))
            new_driver = st.text_input("Proposed Driver / Delivery Details", value=str(tx_row['driver_details'] or ''))
            new_project = st.text_input("Proposed Project Name", value=str(tx_row['project_name'] or ''))
            new_purpose = st.text_input("Proposed Purpose", value=str(tx_row['purpose'] or ''))
            reason = st.text_area("Reason for Edit Request (Required)", placeholder="Explain why this entry needs modification...")

            submit_edit = st.form_submit_button("Submit Edit Request to Head Office")
            
            if submit_edit:
                if not reason.strip():
                    st.error("Please provide a valid reason for the edit request.")
                else:
                    original_data = json.dumps(tx_row.to_dict())
                    proposed_data = json.dumps({
                        "quantity": new_qty,
                        "issued_to": new_issued_to,
                        "driver_details": new_driver,
                        "project_name": new_project,
                        "purpose": new_purpose
                    })
                    
                    cursor.execute("""
                        INSERT INTO edit_requests (transaction_id, requested_by, reason, original_data, proposed_data, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (selected_tx_id, user_name, reason, original_data, proposed_data, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    
                    cursor.execute("UPDATE transactions SET edit_status = 'PENDING_EDIT' WHERE id = ?", (selected_tx_id,))
                    conn.commit()

                    create_notification(
                        f"✏️ New Edit Request submitted by {user_name} for Transaction #{selected_tx_id}.",
                        target_role="Head Office"
                    )
                    st.success("Edit request submitted successfully! Awaiting Head Office approval.")
                    st.rerun()
    else:
        st.info("You haven't logged any transactions yet.")

elif "✏️ Edit Requests" in selected_menu:
    st.subheader("✏️ Review Supervisor Edit Requests")

    requests = cursor.execute("""
        SELECT id, transaction_id, requested_by, reason, original_data, proposed_data, status, timestamp 
        FROM edit_requests ORDER BY id DESC
    """).fetchall()

    if requests:
        for req_id, tx_id, req_by, reason, orig_json, prop_json, status, ts in requests:
            with st.expander(f"Request #{req_id} - Tx #{tx_id} by {req_by} [{status}] ({ts})", expanded=(status == 'PENDING')):
                orig = json.loads(orig_json)
                prop = json.loads(prop_json)

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Original Record:**")
                    st.json(orig)
                with col2:
                    st.markdown("**Proposed Changes:**")
                    st.json(prop)

                st.markdown(f"**Reason:** {reason}")

                if status == 'PENDING':
                    admin_remarks = st.text_input("Review Remarks (Optional)", key=f"rem_{req_id}")
                    btn_col1, btn_col2 = st.columns(2)
                    
                    if btn_col1.button("✅ Approve Request", key=f"app_{req_id}", use_container_width=True):
                        old_qty = float(orig['quantity'])
                        new_qty = float(prop['quantity'])
                        item_name = orig['item_name']
                        tx_type = orig['type']
                        diff = new_qty - old_qty

                        if diff != 0:
                            if tx_type == 'IN':
                                cursor.execute("UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?", (diff, item_name))
                            else:
                                cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", (diff, item_name))

                        cursor.execute("""
                            UPDATE transactions SET 
                                quantity = ?, issued_to = ?, driver_details = ?, project_name = ?, purpose = ?, edit_status = 'EDITED'
                            WHERE id = ?
                        """, (new_qty, prop['issued_to'], prop['driver_details'], prop['project_name'], prop['purpose'], tx_id))

                        cursor.execute("""
                            UPDATE edit_requests SET status = 'APPROVED', review_remarks = ? WHERE id = ?
                        """, (admin_remarks, req_id))
                        
                        conn.commit()

                        create_notification(
                            f"✅ Your edit request for Transaction #{tx_id} was APPROVED by {user_name}.",
                            target_user=req_by
                        )
                        st.success(f"Request #{req_id} approved!")
                        st.rerun()

                    if btn_col2.button("❌ Reject Request", key=f"rej_{req_id}", use_container_width=True):
                        cursor.execute("UPDATE edit_requests SET status = 'REJECTED', review_remarks = ? WHERE id = ?", (admin_remarks, req_id))
                        cursor.execute("UPDATE transactions SET edit_status = 'NORMAL' WHERE id = ?", (tx_id,))
                        conn.commit()

                        create_notification(
                            f"❌ Your edit request for Transaction #{tx_id} was REJECTED by {user_name}.",
                            target_user=req_by
                        )
                        st.error(f"Request #{req_id} rejected.")
                        st.rerun()
    else:
        st.info("No edit requests found.")

elif selected_menu == "📅 Daily Report (Excel)":
    st.subheader("📅 Export Multi-Sheet Daily Site Inventory Report")

    report_date = st.date_input("Select Report Date", datetime.now().date())
    str_date = report_date.strftime("%Y-%m-%d")

    df_daily_tx = pd.read_sql_query(
        "SELECT * FROM transactions WHERE timestamp LIKE ? ORDER BY timestamp ASC",
        conn, params=(f"{str_date}%",)
    )

    df_current_stock = pd.read_sql_query(
        "SELECT category, item_name, current_stock, min_threshold, unit FROM master_items ORDER BY category ASC, item_name ASC",
        conn
    )

    st.write(f"Found **{len(df_daily_tx)}** movement entries for `{str_date}`.")

    excel_data = generate_excel_report(user_name, str_date, df_daily_tx, df_current_stock)
    
    st.download_button(
        label="📥 Download Structured Excel Report",
        data=excel_data,
        file_name=f"Inventory_Report_{str_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

elif selected_menu == "➕ Manage Master Items":
    st.subheader("➕ Master Inventory Items Management")

    tab_add, tab_edit, tab_delete = st.tabs(["Add New Item", "Update Existing Item", "Delete Item"])

    with tab_add:
        with st.form("add_item_form"):
            item_name = st.text_input("Item Name")
            category = st.text_input("Category", placeholder="e.g. 1. Fuel & Oils")
            unit = st.text_input("Unit of Measure", placeholder="e.g. Bags, Liters, Pcs")
            stock = st.number_input("Initial Stock Level", min_value=0.0, step=1.0)
            min_thresh = st.number_input("Minimum Threshold Alert", min_value=0.0, step=1.0)

            if st.form_submit_button("Add Master Item"):
                if item_name.strip():
                    try:
                        cursor.execute("""
                            INSERT INTO master_items (item_name, category, unit, current_stock, min_threshold)
                            VALUES (?, ?, ?, ?, ?)
                        """, (item_name.strip(), category.strip(), unit.strip(), stock, min_thresh))
                        conn.commit()
                        st.success(f"Item '{item_name}' successfully added!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error(f"Item name '{item_name}' already exists.")
                else:
                    st.error("Item Name cannot be empty.")

    with tab_edit:
        items_df = pd.read_sql_query("SELECT * FROM master_items ORDER BY item_name ASC", conn)
        if not items_df.empty:
            selected_item = st.selectbox("Select Item to Modify", items_df['item_name'].tolist())
            item_data = items_df[items_df['item_name'] == selected_item].iloc[0]

            with st.form("edit_item_form"):
                e_category = st.text_input("Category", value=item_data['category'])
                e_unit = st.text_input("Unit", value=item_data['unit'])
                e_stock = st.number_input("Current Stock", value=float(item_data['current_stock']), min_value=0.0)
                e_thresh = st.number_input("Min. Threshold", value=float(item_data['min_threshold']), min_value=0.0)

                if st.form_submit_button("Update Item"):
                    cursor.execute("""
                        UPDATE master_items SET category = ?, unit = ?, current_stock = ?, min_threshold = ?
                        WHERE item_name = ?
                    """, (e_category, e_unit, e_stock, e_thresh, selected_item))
                    conn.commit()
                    st.success(f"Updated '{selected_item}' successfully!")
                    st.rerun()

    with tab_delete:
        items_list = [r[0] for r in cursor.execute("SELECT item_name FROM master_items").fetchall()]
        if items_list:
            item_to_del = st.selectbox("Select Item to Permanently Remove", items_list, key="del_item_sel")
            if st.button("🔴 Confirm Permanent Delete", use_container_width=True):
                cursor.execute("DELETE FROM master_items WHERE item_name = ?", (item_to_del,))
                conn.commit()
                st.warning(f"Deleted '{item_to_del}' from database.")
                st.rerun()

elif selected_menu == "📜 Master Audit Log":
    st.subheader("📜 Complete System Audit Trail")

    df_all_tx = pd.read_sql_query("SELECT * FROM transactions ORDER BY id DESC", conn)
    
    if not df_all_tx.empty:
        search_query = st.text_input("🔍 Search Audit Log (Item, User, Project, Remarks, etc.)")
        if search_query:
            mask = df_all_tx.astype(str).apply(lambda row: row.str.contains(search_query, case=False).any(), axis=1)
            df_all_tx = df_all_tx[mask]

        st.dataframe(df_all_tx, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.markdown("### 📷 View Attached Receipt / Withdrawal Proof")
        tx_with_photos = df_all_tx[df_all_tx['photo_path'].notnull() & (df_all_tx['photo_path'] != '')]
        
        if not tx_with_photos.empty:
            selected_photo_tx = st.selectbox("Select Transaction ID to view proof photo", tx_with_photos['id'].tolist())
            photo_path = tx_with_photos[tx_with_photos['id'] == selected_photo_tx]['photo_path'].values[0]
            
            if os.path.exists(photo_path):
                st.image(photo_path, caption=f"Proof Photo for Tx #{selected_photo_tx}", use_column_width=True)
            else:
                st.error("Photo file not found on disk server.")
        else:
            st.caption("No proof photo attachments available in the current log selection.")
    else:
        st.info("No transaction logs available.")

elif selected_menu == "👤 Manage Users":
    st.subheader("👤 User Account Management")

    tab_u_list, tab_u_add = st.tabs(["Active Users", "Create User"])

    with tab_u_list:
        df_users = pd.read_sql_query("SELECT id, username, role FROM users", conn)
        st.dataframe(df_users, use_container_width=True, hide_index=True)

    with tab_u_add:
        with st.form("create_user_form"):
            new_u = st.text_input("Username")
            new_p = st.text_input("Password", type="password")
            new_r = st.selectbox("Assigned Role", ["Materials Supervisor", "Head Office"])

            if st.form_submit_button("Create User"):
                if new_u.strip() and new_p.strip():
                    try:
                        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                                       (new_u.strip(), new_p.strip(), new_r))
                        conn.commit()
                        st.success(f"User '{new_u}' successfully created as {new_r}!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error(f"Username '{new_u}' already exists.")
                else:
                    st.error("Username and Password are required.")

elif selected_menu == "⏰ Reminders":
    st.subheader("⏰ Site Reminders & Tasks")

    col1, col2 = st.columns([0.4, 0.6])

    with col1:
        st.markdown("#### ➕ Add New Reminder")
        with st.form("add_reminder_form"):
            rem_title = st.text_input("Reminder Title / Task")
            rem_due = st.date_input("Due Date", datetime.now().date())
            rem_prio = st.selectbox("Priority Level", ["Normal", "High", "Critical"])
            
            if st.form_submit_button("Set Reminder"):
                if rem_title.strip():
                    cursor.execute("""
                        INSERT INTO reminders (user_name, title, due_date, priority, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                    """, (user_name, rem_title.strip(), rem_due.strftime("%Y-%m-%d"), rem_prio, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    st.success("Reminder created!")
                    st.rerun()
                else:
                    st.error("Please enter a title.")

    with col2:
        st.markdown("#### 📌 Pending Reminders")
        df_reminders = pd.read_sql_query(
            "SELECT id, title, due_date, priority, status FROM reminders WHERE user_name = ? AND status = 'PENDING' ORDER BY due_date ASC",
            conn, params=(user_name,)
        )

        if not df_reminders.empty:
            for _, r in df_reminders.iterrows():
                prio_color = "🔴" if r['priority'] == 'Critical' else ("🟡" if r['priority'] == 'High' else "🔵")
                with st.container(border=True):
                    c_a, c_b = st.columns([0.8, 0.2])
                    c_a.markdown(f"{prio_color} **{r['title']}**\n\n🗓️ Due: `{r['due_date']}` | Priority: **{r['priority']}**")
                    if c_b.button("Done", key=f"done_rem_{r['id']}"):
                        cursor.execute("UPDATE reminders SET status = 'COMPLETED' WHERE id = ?", (r['id'],))
                        conn.commit()
                        st.rerun()
        else:
            st.info("No pending reminders.")

elif selected_menu == "📅 Schedule":
    st.subheader("📅 Site Operations & Delivery Schedule")

    sch_col1, sch_col2 = st.columns([0.4, 0.6])

    with sch_col1:
        st.markdown("#### ➕ Schedule Event / Delivery")
        with st.form("add_schedule_form"):
            ev_title = st.text_input("Event / Delivery Title", placeholder="e.g. Bulk Cement Arrival")
            ev_date = st.date_input("Event Date", datetime.now().date())
            ev_s_time = st.time_input("Start Time", time(8, 0))
            ev_e_time = st.time_input("End Time", time(10, 0))
            ev_location = st.text_input("Location / Unloading Zone", placeholder="e.g. Bay 3 / North Storage")
            ev_notes = st.text_area("Notes / Instructions", placeholder="e.g. Prepare forklift and 3 laborers")

            if st.form_submit_button("Add Event to Schedule"):
                if ev_title.strip():
                    cursor.execute("""
                        INSERT INTO schedules (user_name, title, event_date, start_time, end_time, location_details, notes, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_name, ev_title.strip(), ev_date.strftime("%Y-%m-%d"),
                        ev_s_time.strftime("%H:%M"), ev_e_time.strftime("%H:%M"),
                        ev_location.strip(), ev_notes.strip(), datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ))
                    conn.commit()
                    st.success("Event scheduled!")
                    st.rerun()
                else:
                    st.error("Please provide an Event Title.")

    with sch_col2:
        st.markdown("#### 🗓️ Upcoming Events")
        df_schedules = pd.read_sql_query(
            "SELECT * FROM schedules WHERE event_date >= ? ORDER BY event_date ASC, start_time ASC",
            conn, params=(datetime.now().strftime("%Y-%m-%d"),)
        )

        if not df_schedules.empty:
            for _, s in df_schedules.iterrows():
                with st.container(border=True):
                    st.markdown(f"### 📍 {s['title']}")
                    st.markdown(f"🗓️ **Date:** `{s['event_date']}` | ⏰ **Time:** `{s['start_time']} - {s['end_time']}`")
                    if s['location_details']:
                        st.markdown(f"🏗️ **Location:** {s['location_details']}")
                    if s['notes']:
                        st.caption(f"📝 Notes: {s['notes']}")
                    st.caption(f"Logged by: `{s['user_name']}`")
        else:
            st.info("No upcoming events scheduled.")
