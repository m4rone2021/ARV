# -------------------------------------------------------------
    # TAB 2: SCHEDULE NEW STOCK OUT DELIVERY (RESERVE STOCK)
    # -------------------------------------------------------------
    with tab_add:
        st.subheader("Schedule New Single Dispatch Batch")

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
                has_active_batch = bool(st.session_state.delivery_cart)
                header_data = st.session_state.current_dispatch_header or {}

                # --- 1. SELECTION & STOCK PREVIEW ---
                selected_item_name = st.selectbox(
                    "Select Item to Add to Dispatch*", 
                    df_master["item_name"].tolist(),
                    key="dispatch_item_selector" # Assigned explicit key
                )
                
                item_info = df_master[df_master["item_name"] == selected_item_name].iloc[0]

                stock_in_shop = float(item_info["current_stock"])
                stock_reserved = float(item_info["reserved_stock"])
                
                # Account for items already staged in this current dispatch batch
                staged_qty = sum(
                    item["quantity"] for item in st.session_state.delivery_cart 
                    if item["item_name"] == selected_item_name
                )
                stock_available = float(item_info["available_stock"]) - staged_qty
                unit_name = str(item_info["unit"])

                # Metric visualizer
                m1, m2, m3 = st.columns(3)
                m1.metric("Stock In Shop (Total)", f"{stock_in_shop:,.2f} {unit_name}")
                m2.metric("Reserved Stock", f"{stock_reserved:,.2f} {unit_name}")
                m3.metric("Available Stock", f"{stock_available:,.2f} {unit_name}")

                st.divider()

                # --- 2. ADD ITEM FORM ---
                with st.form("add_dispatch_item_form", clear_on_submit=True):
                    if has_active_batch:
                        st.info(f"🔒 **Dispatch Order Locked:** Adding additional items to batch for **{header_data.get('requested_by')}** ➡️ **{header_data.get('destination')}** ({header_data.get('project')})")
                    else:
                        st.markdown("##### 📄 1. Dispatch Order Details")
                        col1, col2 = st.columns(2)
                        with col1:
                            input_requested_by = st.text_input("Requested By*", placeholder="e.g., Engr. John Doe")
                            input_destination = st.text_input("Destination / Site Location*", placeholder="e.g., Block 4 Site")
                            input_project = st.text_input("Project Name / Code*", placeholder="e.g., Bridge Construction Phase 1")
                        
                        with col2:
                            input_scheduled_date = st.date_input("Scheduled Delivery Date", value=datetime.today())
                            input_status = st.selectbox("Initial Status", ["Pending", "In Transit"])

                        input_driver = st.text_input("Assigned Driver Name (Optional)", placeholder="e.g., John Doe")
                        input_priority = st.checkbox("🔥 Mark as High Priority Delivery")
                        st.divider()

                    st.markdown(f"##### 📦 2. Item Entry: {selected_item_name}")
                    quantity = st.number_input(f"Quantity to Reserve ({unit_name})*", min_value=0.01, value=None, placeholder="0.0")
                    item_notes = st.text_input("Item Specific Notes / Instructions", placeholder="e.g., Handle with care, stack 5 layers max")
                    
                    add_to_cart_btn = st.form_submit_button("🛒 Add Item to Batch Queue", use_container_width=True)

                    if add_to_cart_btn:
                        if not has_active_batch:
                            req_val = input_requested_by.strip()
                            dest_val = input_destination.strip()
                            proj_val = input_project.strip()
                            sched_val = input_scheduled_date
                            stat_val = input_status
                            driver_val = input_driver.strip()
                            prio_val = input_priority
                        else:
                            req_val = header_data.get("requested_by")
                            dest_val = header_data.get("destination")
                            proj_val = header_data.get("project")
                            sched_val = header_data.get("scheduled_date")
                            stat_val = header_data.get("status")
                            driver_val = header_data.get("driver_name")
                            prio_val = header_data.get("is_priority")

                        if not req_val or not dest_val or not proj_val or quantity is None:
                            st.error("⚠️ Requested By, Destination, Project, and Quantity are required fields.")
                        elif quantity > stock_available:
                            st.error(f"❌ Cannot reserve stock! Requested Quantity ({quantity} {unit_name}) exceeds Available Stock ({stock_available} {unit_name}).")
                        else:
                            if not has_active_batch:
                                st.session_state.current_dispatch_header = {
                                    "requested_by": req_val,
                                    "destination": dest_val,
                                    "project": proj_val,
                                    "scheduled_date": sched_val,
                                    "status": stat_val,
                                    "driver_name": driver_val,
                                    "is_priority": prio_val
                                }

                            st.session_state.delivery_cart.append({
                                "item_name": selected_item_name,
                                "unit": unit_name,
                                "quantity": float(quantity),
                                "notes": item_notes.strip()
                            })
                            st.success(f"Added **{selected_item_name}** ({quantity} {unit_name}) to this dispatch batch!")
                            st.rerun()

                # --- 3. STAGING QUEUE & FINAL CONFIRMATION SECTION ---
                if st.session_state.delivery_cart:
                    st.divider()
                    st.markdown(f"### 📋 Dispatch Order Summary ({len(st.session_state.delivery_cart)} items queued)")
                    st.caption("All items below belong to one single dispatch request. Confirm details before finalizing.")

                    cart_df = pd.DataFrame(st.session_state.delivery_cart)
                    
                    # Editable confirmation table
                    edited_cart_df = st.data_editor(
                        cart_df,
                        column_config={
                            "item_name": st.column_config.TextColumn("Item Name", disabled=True),
                            "unit": st.column_config.TextColumn("Unit", disabled=True),
                            "quantity": st.column_config.NumberColumn("Quantity", min_value=0.01, format="%.2f"),
                            "notes": st.column_config.TextColumn("Item Notes")
                        },
                        use_container_width=True,
                        num_rows="dynamic",
                        key="cart_editor"
                    )

                    col_confirm, col_clear = st.columns([3, 1])

                    with col_clear:
                        if st.button("🗑️ Cancel & Reset Batch", use_container_width=True):
                            st.session_state.delivery_cart = []
                            st.session_state.current_dispatch_header = None
                            st.rerun()

                    with col_confirm:
                        if st.button("📅 Confirm & Schedule Dispatch Batch", type="primary", use_container_width=True):
                            try:
                                updated_cart = edited_cart_df.to_dict("records")
                                if not updated_cart:
                                    st.warning("⚠️ No items remaining in the dispatch queue.")
                                else:
                                    dispatch_code = f"DISP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
                                    h = st.session_state.current_dispatch_header

                                    with get_db() as conn_add:
                                        cursor = conn_add.cursor()
                                        
                                        for row in updated_cart:
                                            # 1. Insert Delivery Schedule
                                            cursor.execute("""
                                                INSERT INTO deliveries (
                                                    dispatch_id, item_name, supplier, requested_by, destination, project, 
                                                    expected_quantity, unit, expected_date, status, notes, is_priority, driver_name
                                                )
                                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                            """, (
                                                dispatch_code, row["item_name"], h["destination"], h["requested_by"], 
                                                h["destination"], h["project"], row["quantity"], 
                                                row["unit"], str(h["scheduled_date"]), h["status"], 
                                                row["notes"], 1 if h["is_priority"] else 0, h["driver_name"]
                                            ))

                                            # 2. Reserve inventory on master catalog
                                            cursor.execute("""
                                                UPDATE master_items
                                                SET reserved_stock = COALESCE(reserved_stock, 0) + ?
                                                WHERE item_name = ?
                                            """, (row["quantity"], row["item_name"]))

                                        conn_add.commit()

                                    st.session_state.delivery_cart = []
                                    st.session_state.current_dispatch_header = None
                                    st.success(f"✅ Dispatch **{dispatch_code}** successfully scheduled with {len(updated_cart)} item(s) and inventory reserved!")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Failed to submit dispatch batch: {e}")
            else:
                st.warning("⚠️ No master items found. Please add items to the Master Catalog first.")

        except Exception as e:
            st.error(f"Error fetching catalog items: {e}")
