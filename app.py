# [CONTINUATION FROM: elif selected_menu == "- Stock Out":]

        st.subheader("Log Stock Issuance (Usage & Dispatch)")
        items_data = cursor.execute("SELECT item_name, current_stock, unit FROM master_items").fetchall()
        if items_data:
            item_names = [row[0] for row in items_data]
            
            col_a, col_b = st.columns(2)
            with col_a:
                item_selected = st.selectbox("Select Item to Issue", item_names, key="out_item")
                
                # Fetch stock balance for selected item
                current_bal, unit_label = cursor.execute(
                    "SELECT current_stock, unit FROM master_items WHERE item_name = ?", (item_selected,)
                ).fetchone()
                
                st.caption(f"Current Stock Available: **{current_bal:,.2f} {unit_label}**")
                
                qty_out = st.number_input("Quantity Issued", min_value=0.1, step=1.0, key="out_qty")
                issued_to = st.text_input("Issued To (Recipient / Subcontractor)", placeholder="e.g. Foreman Cruz / Steel Works Team", key="out_recipient")
                
            with col_b:
                project_name = st.text_input("Project Name / Phase", placeholder="e.g. Tower 2 - 5th Floor Slab", key="out_proj")
                purpose = st.text_input("Purpose / Equipment Ref", placeholder="e.g. Beam reinforcement / Backhoe #3 maintenance", key="out_purpose")
                driver_info = st.text_input("Driver / Transport Vehicle (If applicable)", placeholder="e.g. Pickup Truck WXY-888", key="out_driver")

            remarks_out = st.text_area("Additional Remarks", placeholder="e.g. Emergency issuance requested by site manager", key="out_rem", height=68)

            st.markdown("### 📷 Requisition / Releaser Photo Proof")
            photo_mode = st.radio("Choose Photo Upload Method:", ["Camera Capture", "Upload File"], horizontal=True, key="out_photo_mode")
            
            image_bytes = None
            if photo_mode == "Camera Capture":
                camera_photo = st.camera_input("Take a picture of the requisition slip / released items", key="out_camera")
                if camera_photo:
                    image_bytes = camera_photo.getvalue()
            else:
                uploaded_file = st.file_uploader("Upload Requisition Slip / Photo", type=["jpg", "jpeg", "png"], key="out_upload")
                if uploaded_file:
                    image_bytes = uploaded_file.getvalue()

            if st.button("Submit Stock Out", use_container_width=True):
                if qty_out > current_bal:
                    st.error(f"Cannot issue {qty_out} {unit_label}. Only {current_bal} {unit_label} available in stock!")
                else:
                    saved_photo_path = None
                    if image_bytes:
                        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                        file_filename = f"uploads/issuance_{timestamp_str}.jpg"
                        with open(file_filename, "wb") as f:
                            f.write(image_bytes)
                        saved_photo_path = file_filename

                    # Deduct from inventory
                    cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", (qty_out, item_selected))
                    
                    # Log issuance transaction
                    cursor.execute("""
                        INSERT INTO transactions (
                            timestamp, item_name, type, quantity, user_role, 
                            driver_details, issued_to, project_name, purpose, remarks, photo_path
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item_selected, "OUT", qty_out, user_name,
                        driver_info, issued_to, project_name, purpose, remarks_out, saved_photo_path
                    ))
                    conn.commit()

                    # Trigger low stock notification check
                    new_bal, min_thresh = cursor.execute("SELECT current_stock, min_threshold FROM master_items WHERE item_name = ?", (item_selected,)).fetchone()
                    if new_bal <= min_thresh:
                        create_notification(
                            f"⚠️ Low Stock Alert: `{item_selected}` has fallen to {new_bal} {unit_label} (Threshold: {min_thresh}).",
                            target_role="Head Office"
                        )

                    st.success(f"Successfully recorded issuance of {qty_out} {unit_label} of {item_selected}!")
                    st.rerun()
        else:
            st.warning("Please add items to Master Inventory first.")

    # --- MENU 5: MY LOG & REQUEST EDITS (SUPERVISOR ONLY) ---
    elif selected_menu == "📜 My Log & Request Edits":
        st.subheader("📜 My Recorded Log Entries & Edit Requests")

        df_my_tx = pd.read_sql_query("""
            SELECT id, timestamp, item_name, type, quantity, issued_to, driver_details, project_name, purpose, remarks, edit_status, photo_path
            FROM transactions 
            WHERE user_role = ? 
            ORDER BY id DESC
        """, conn, params=(user_name,))

        if not df_my_tx.empty:
            st.dataframe(
                df_my_tx.drop(columns=['photo_path']),
                column_config={
                    "id": st.column_config.NumberColumn("TX ID", width="small"),
                    "timestamp": "Timestamp",
                    "item_name": "Item Name",
                    "type": "Type",
                    "quantity": st.column_config.NumberColumn("Qty", format="%.2f"),
                    "issued_to": "Issued To",
                    "driver_details": "Driver/Vehicle",
                    "project_name": "Project",
                    "purpose": "Purpose",
                    "remarks": "Remarks",
                    "edit_status": "Status"
                },
                hide_index=True,
                use_container_width=True
            )

            st.markdown("---")
            st.markdown("### ✏️ Request Transaction Correction / Adjustment")

            normal_tx_ids = df_my_tx[df_my_tx['edit_status'] == 'NORMAL']['id'].tolist()
            if normal_tx_ids:
                selected_tx_id = st.selectbox("Select Transaction ID to Edit:", normal_tx_ids)
                
                tx_row = df_my_tx[df_my_tx['id'] == selected_tx_id].iloc[0]
                
                st.info(f"Editing Transaction ID #{selected_tx_id} — **{tx_row['item_name']}** ({tx_row['type']})")

                with st.form(key="request_edit_form"):
                    col_e1, col_e2 = st.columns(2)
                    with col_e1:
                        prop_qty = st.number_input("Corrected Quantity", value=float(tx_row['quantity']), min_value=0.1, step=1.0)
                        prop_issued_to = st.text_input("Corrected Issued To", value=str(tx_row['issued_to'] or ''))
                        prop_driver = st.text_input("Corrected Driver / Transport", value=str(tx_row['driver_details'] or ''))
                    with col_e2:
                        prop_project = st.text_input("Corrected Project Name", value=str(tx_row['project_name'] or ''))
                        prop_purpose = st.text_input("Corrected Purpose", value=str(tx_row['purpose'] or ''))
                        prop_remarks = st.text_input("Corrected Remarks", value=str(tx_row['remarks'] or ''))

                    edit_reason = st.text_area("Reason for Edit Request (Required)", placeholder="e.g. Wrong quantity entered due to typings error on receipt")

                    submit_edit_req = st.form_submit_button("Submit Edit Request to Head Office")

                if submit_edit_req:
                    if not edit_reason.strip():
                        st.error("Please provide a reason for requesting this edit.")
                    else:
                        original_data_json = json.dumps({
                            "quantity": tx_row['quantity'],
                            "issued_to": tx_row['issued_to'],
                            "driver_details": tx_row['driver_details'],
                            "project_name": tx_row['project_name'],
                            "purpose": tx_row['purpose'],
                            "remarks": tx_row['remarks']
                        })

                        proposed_data_json = json.dumps({
                            "quantity": prop_qty,
                            "issued_to": prop_issued_to,
                            "driver_details": prop_driver,
                            "project_name": prop_project,
                            "purpose": prop_purpose,
                            "remarks": prop_remarks
                        })

                        cursor.execute("""
                            INSERT INTO edit_requests (transaction_id, requested_by, reason, original_data, proposed_data, timestamp)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (selected_tx_id, user_name, edit_reason, original_data_json, proposed_data_json, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

                        cursor.execute("UPDATE transactions SET edit_status = 'PENDING_EDIT' WHERE id = ?", (selected_tx_id,))
                        conn.commit()

                        create_notification(
                            f"📝 New edit request submitted by `{user_name}` for TX ID #{selected_tx_id}.",
                            target_role="Head Office"
                        )

                        st.success("Edit request submitted successfully! Pending approval from Head Office.")
                        st.rerun()
            else:
                st.caption("All your eligible transactions already have active or processed edit requests.")
        else:
            st.info("You haven't logged any transactions yet.")

    # --- MENU 6: DAILY REPORT EXCEL EXPORT (SUPERVISOR / HEAD OFFICE) ---
    elif selected_menu == "📅 Daily Report (Excel)":
        st.subheader("📅 Export Automated Multi-Sheet Daily Report")
        
        selected_report_date = st.date_input("Select Date for Report Export:", datetime.now())
        date_str = selected_report_date.strftime("%Y-%m-%d")

        df_daily_tx = pd.read_sql_query("""
            SELECT * FROM transactions 
            WHERE timestamp LIKE ?
            ORDER BY id ASC
        """, conn, params=(f"{date_str}%",))

        df_current_stock = pd.read_sql_query("""
            SELECT category, item_name, current_stock, min_threshold, unit 
            FROM master_items 
            ORDER BY category ASC, item_name ASC
        """, conn)

        st.markdown(f"**Found {len(df_daily_tx)} transaction(s) logged on {date_str}.**")

        excel_file = generate_excel_report(user_name, date_str, df_daily_tx, df_current_stock)

        st.download_button(
            label="📥 Download Daily Report (.xlsx)",
            data=excel_file,
            file_name=f"Site_Inventory_Report_{date_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    # --- MENU 7: EDIT REQUESTS APPROVAL (HEAD OFFICE ONLY) ---
    elif selected_menu.startswith("✏️ Edit Requests"):
        st.subheader("✏️ Review Pending Transaction Edit Requests")

        pending_requests = cursor.execute("""
            SELECT er.id, er.transaction_id, er.requested_by, er.reason, er.original_data, er.proposed_data, er.timestamp, t.item_name, t.type
            FROM edit_requests er
            JOIN transactions t ON er.transaction_id = t.id
            WHERE er.status = 'PENDING'
            ORDER BY er.id ASC
        """).fetchall()

        if pending_requests:
            for req_id, tx_id, req_by, reason, orig_json, prop_json, req_ts, item_name, tx_type in pending_requests:
                orig = json.loads(orig_json)
                prop = json.loads(prop_json)

                with st.expander(f"📌 Request #{req_id} — TX #{tx_id} ({item_name} [{tx_type}]) by {req_by} on {req_ts}", expanded=True):
                    st.markdown(f"**Reason for request:** _{reason}_")
                    
                    c_orig, c_prop = st.columns(2)
                    with c_orig:
                        st.markdown("#### 🔴 Original Data")
                        st.json(orig)
                    with c_prop:
                        st.markdown("#### 🟢 Proposed Data")
                        st.json(prop)

                    review_notes = st.text_input("Reviewer Remarks / Notes", key=f"notes_{req_id}")

                    col_approve, col_reject = st.columns(2)
                    with col_approve:
                        if st.button("✅ Approve Request", key=f"app_{req_id}", use_container_width=True):
                            # Adjust inventory stock balance if quantity changed
                            old_qty = float(orig.get('quantity', 0))
                            new_qty = float(prop.get('quantity', 0))
                            qty_diff = new_qty - old_qty

                            if qty_diff != 0:
                                if tx_type == "IN":
                                    cursor.execute("UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?", (qty_diff, item_name))
                                else: # OUT
                                    cursor.execute("UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", (qty_diff, item_name))

                            # Update transaction values
                            cursor.execute("""
                                UPDATE transactions SET 
                                    quantity = ?, 
                                    issued_to = ?, 
                                    driver_details = ?, 
                                    project_name = ?, 
                                    purpose = ?, 
                                    remarks = ?,
                                    edit_status = 'EDITED'
                                WHERE id = ?
                            """, (
                                prop.get('quantity'), prop.get('issued_to'), prop.get('driver_details'),
                                prop.get('project_name'), prop.get('purpose'), prop.get('remarks'),
                                tx_id
                            ))

                            # Update request record status
                            cursor.execute("""
                                UPDATE edit_requests SET status = 'APPROVED', review_remarks = ? WHERE id = ?
                            """, (review_notes, req_id))
                            conn.commit()

                            create_notification(
                                f"✅ Your edit request for TX ID #{tx_id} was APPROVED by `{user_name}`.",
                                target_user=req_by
                            )

                            st.success(f"Request #{req_id} approved and inventory updated!")
                            st.rerun()

                    with col_reject:
                        if st.button("❌ Reject Request", key=f"rej_{req_id}", use_container_width=True):
                            cursor.execute("UPDATE edit_requests SET status = 'REJECTED', review_remarks = ? WHERE id = ?", (review_notes, req_id))
                            cursor.execute("UPDATE transactions SET edit_status = 'NORMAL' WHERE id = ?", (tx_id,))
                            conn.commit()

                            create_notification(
                                f"❌ Your edit request for TX ID #{tx_id} was REJECTED by `{user_name}`.",
                                target_user=req_by
                            )

                            st.warning(f"Request #{req_id} rejected.")
                            st.rerun()
        else:
            st.info("No pending edit requests to review.")

    # --- MENU 8: MANAGE MASTER ITEMS (HEAD OFFICE ONLY) ---
    elif selected_menu == "➕ Manage Master Items":
        st.subheader("➕ Master Inventory Item Management")

        tab_add, tab_edit = st.tabs(["Add New Item", "Edit / Delete Existing Items"])

        with tab_add:
            with st.form("add_item_form"):
                new_name = st.text_input("Item Name (Must be Unique)")
                new_cat = st.selectbox("Category", [
                    "1. Fuel & Oils", "2. Construction Materials", "3. Steel / Rebar", 
                    "4A. Nails & Fasteners", "4B. Cutting & Grinding Consumables", 
                    "4C. Welding Supplies & PPE", "4D. General Site Supplies", "5. Tools & Machinery"
                ])
                new_unit = st.text_input("Unit of Measure", placeholder="e.g. Kilos, Bags, Liters, Pcs")
                init_stock = st.number_input("Initial Stock Level", min_value=0.0, step=1.0)
                min_thresh = st.number_input("Minimum Alert Threshold", min_value=0.0, step=1.0)

                submit_new_item = st.form_submit_button("Add Item to Master Catalog")

            if submit_new_item:
                if not new_name.strip() or not new_unit.strip():
                    st.error("Please fill in item name and unit of measure.")
                else:
                    try:
                        cursor.execute("""
                            INSERT INTO master_items (item_name, category, unit, current_stock, min_threshold)
                            VALUES (?, ?, ?, ?, ?)
                        """, (new_name.strip(), new_cat, new_unit.strip(), init_stock, min_thresh))
                        conn.commit()
                        st.success(f"Successfully added '{new_name}' to Master Catalog!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error(f"Item '{new_name}' already exists in the catalog!")

        with tab_edit:
            all_items = [r[0] for r in cursor.execute("SELECT item_name FROM master_items ORDER BY item_name ASC").fetchall()]
            if all_items:
                selected_edit_item = st.selectbox("Select Item to Update / Remove:", all_items)
                
                item_row = cursor.execute("SELECT id, item_name, category, unit, current_stock, min_threshold FROM master_items WHERE item_name = ?", (selected_edit_item,)).fetchone()
                
                if item_row:
                    i_id, i_name, i_cat, i_unit, i_stock, i_thresh = item_row

                    with st.form("update_item_form"):
                        up_name = st.text_input("Item Name", value=i_name)
                        up_unit = st.text_input("Unit", value=i_unit)
                        up_stock = st.number_input("Current Stock", value=float(i_stock), min_value=0.0)
                        up_thresh = st.number_input("Minimum Threshold Alert", value=float(i_thresh), min_value=0.0)

                        col_u1, col_u2 = st.columns(2)
                        with col_u1:
                            submit_update = st.form_submit_button("Update Item Details")
                        with col_u2:
                            submit_delete = st.form_submit_button("🗑️ Delete Item")

                    if submit_update:
                        cursor.execute("""
                            UPDATE master_items SET item_name = ?, unit = ?, current_stock = ?, min_threshold = ?
                            WHERE id = ?
                        """, (up_name.strip(), up_unit.strip(), up_stock, up_thresh, i_id))
                        conn.commit()
                        st.success(f"Updated '{up_name}' details!")
                        st.rerun()

                    if submit_delete:
                        cursor.execute("DELETE FROM master_items WHERE id = ?", (i_id,))
                        conn.commit()
                        st.warning(f"Deleted '{i_name}' from Master Catalog.")
                        st.rerun()
            else:
                st.info("No items available in Master Catalog.")

    # --- MENU 9: MASTER AUDIT LOG (HEAD OFFICE ONLY) ---
    elif selected_menu == "📜 Master Audit Log":
        st.subheader("📜 System Master Audit Log")

        df_all_logs = pd.read_sql_query("""
            SELECT id, timestamp, item_name, type, quantity, user_role, issued_to, driver_details, project_name, purpose, remarks, edit_status
            FROM transactions 
            ORDER BY id DESC
        """, conn)

        if not df_all_logs.empty:
            st.dataframe(
                df_all_logs,
                column_config={
                    "id": st.column_config.NumberColumn("ID", width="small"),
                    "timestamp": "Timestamp",
                    "item_name": "Item Name",
                    "type": "Type",
                    "quantity": st.column_config.NumberColumn("Qty", format="%.2f"),
                    "user_role": "Logged By",
                    "issued_to": "Issued To",
                    "driver_details": "Driver/Vehicle",
                    "project_name": "Project",
                    "purpose": "Purpose",
                    "remarks": "Remarks",
                    "edit_status": "Status"
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("No logs present in database.")

    # --- MENU 10: MANAGE USERS (HEAD OFFICE ONLY) ---
    elif selected_menu == "👤 Manage Users":
        st.subheader("👤 User Account Management")

        tab_u_add, tab_u_view = st.tabs(["Create New User", "Existing Accounts"])

        with tab_u_add:
            with st.form("add_user_form"):
                u_username = st.text_input("New Username")
                u_password = st.text_input("New Password", type="password")
                u_role = st.selectbox("Assign Role", ["Materials Supervisor", "Head Office"])

                submit_user = st.form_submit_button("Create Account")

            if submit_user:
                if not u_username.strip() or not u_password.strip():
                    st.error("Please enter both username and password.")
                else:
                    try:
                        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                                       (u_username.strip(), u_password.strip(), u_role))
                        conn.commit()
                        st.success(f"User account '{u_username}' created successfully!")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error(f"Username '{u_username}' is already taken!")

        with tab_u_view:
            df_users = pd.read_sql_query("SELECT id, username, role FROM users", conn)
            st.dataframe(df_users, hide_index=True, use_container_width=True)

    # --- MENU 11: REMINDERS (NEW) ---
    elif selected_menu == "⏰ Reminders":
        st.subheader("⏰ Site Reminders & Task Tracker")

        col_rem1, col_rem2 = st.columns([0.4, 0.6])

        with col_rem1:
            st.markdown("### ➕ Create New Reminder")
            with st.form("add_reminder_form"):
                rem_title = st.text_input("Reminder Title / Task", placeholder="e.g. Call Diesel Supplier for Restock")
                rem_due = st.date_input("Due Date", datetime.now() + timedelta(days=1))
                rem_prio = st.selectbox("Priority Level", ["🔴 High", "🟡 Medium", "🔵 Low"])

                submit_rem = st.form_submit_button("Set Reminder", use_container_width=True)

            if submit_rem:
                if not rem_title.strip():
                    st.error("Please enter a title for the reminder.")
                else:
                    cursor.execute("""
                        INSERT INTO reminders (user_name, title, due_date, priority, status, timestamp)
                        VALUES (?, ?, ?, ?, 'PENDING', ?)
                    """, (user_name, rem_title.strip(), rem_due.strftime("%Y-%m-%d"), rem_prio, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    st.success("Reminder created!")
                    st.rerun()

        with col_rem2:
            st.markdown("### 📋 Active Reminders")
            
            rems = cursor.execute("""
                SELECT id, title, due_date, priority, status FROM reminders
                WHERE user_name = ? AND status = 'PENDING'
                ORDER BY due_date ASC
            """, (user_name,)).fetchall()

            if rems:
                for r_id, r_title, r_due, r_prio, r_status in rems:
                    with st.container(border=True):
                        rc1, rc2 = st.columns([0.75, 0.25])
                        with rc1:
                            st.markdown(f"**{r_title}**")
                            st.caption(f"Priority: {r_prio} | Due: `{r_due}`")
                        with rc2:
                            if st.button("Mark Done", key=f"done_rem_{r_id}"):
                                cursor.execute("UPDATE reminders SET status = 'COMPLETED' WHERE id = ?", (r_id,))
                                conn.commit()
                                st.rerun()
            else:
                st.info("No active reminders. Great job staying on top of things!")

            st.markdown("---")
            with st.expander("Completed Reminders History"):
                done_rems = pd.read_sql_query("""
                    SELECT title, due_date, priority, timestamp as created_at FROM reminders
                    WHERE user_name = ? AND status = 'COMPLETED'
                    ORDER BY id DESC LIMIT 10
                """, conn, params=(user_name,))
                if not done_rems.empty:
                    st.dataframe(done_rems, hide_index=True, use_container_width=True)
                else:
                    st.caption("No completed reminders yet.")

    # --- MENU 12: SCHEDULE (NEW) ---
    elif selected_menu == "📅 Schedule":
        st.subheader("📅 Site Events & Delivery Schedule")

        sch_tab1, sch_tab2 = st.tabs(["➕ Schedule New Event", "📆 Upcoming Schedule View"])

        with sch_tab1:
            with st.form("add_schedule_form"):
                sch_title = st.text_input("Event / Delivery Title", placeholder="e.g. Cement Delivery (15 Bags Tonner)")
                sch_date = st.date_input("Event Date", datetime.now())
                
                sc_t1, sc_t2 = st.columns(2)
                with sc_t1:
                    sch_start = st.time_input("Start Time", time(8, 0))
                with sc_t2:
                    sch_end = st.time_input("End Time", time(9, 0))

                sch_loc = st.text_input("Location / Gate Details", placeholder="e.g. Gate 2 - South Unloading Area")
                sch_notes = st.text_area("Notes / Contact Person", placeholder="e.g. Contact Driver Mark at 0917-XXX-XXXX")

                submit_sch = st.form_submit_button("Add Event to Schedule")

            if submit_sch:
                if not sch_title.strip():
                    st.error("Please enter an event title.")
                else:
                    cursor.execute("""
                        INSERT INTO schedules (user_name, title, event_date, start_time, end_time, location_details, notes, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_name, sch_title.strip(), sch_date.strftime("%Y-%m-%d"), 
                        sch_start.strftime("%H:%M"), sch_end.strftime("%H:%M"), 
                        sch_loc, sch_notes, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ))
                    conn.commit()
                    st.success("Event scheduled successfully!")
                    st.rerun()

        with sch_tab2:
            events = cursor.execute("""
                SELECT id, title, event_date, start_time, end_time, location_details, notes 
                FROM schedules 
                WHERE event_date >= DATE('now')
                ORDER BY event_date ASC, start_time ASC
            """, ).fetchall()

            if events:
                for e_id, e_title, e_date, e_start, e_end, e_loc, e_notes in events:
                    with st.container(border=True):
                        st.markdown(f"#### 📅 {e_date} | {e_start} - {e_end}")
                        st.markdown(f"**{e_title}**")
                        if e_loc:
                            st.markdown(f"📍 **Location:** {e_loc}")
                        if e_notes:
                            st.markdown(f"📝 **Notes:** _{e_notes}_")
            else:
                st.info("No upcoming scheduled events.")
