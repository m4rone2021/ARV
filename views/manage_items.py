# views/manage_items.py
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db, init_db

def render_manage_items(user_name, user_role):
    st.title("📦 Manage Master Items")
    st.caption("Add, update, search, and manage site master inventory records.")

    # Ensure database schema exists
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

    units_list = ["Pcs", "Bags", "Kg", "Tons", "Liters", "Gallons", "Boxes", "Bundles", "Rolls", "Pairs", "Sets", "Meters"]

    # Action Tabs
    tab_view, tab_add, tab_edit, tab_delete = st.tabs([
        "📋 Master Catalog", 
        "➕ Add New Item", 
        "✏️ Edit Item Details", 
        "🗑️ Delete Item"
    ])

    # -------------------------------------------------------------
    # TAB 1: MASTER CATALOG VIEW
    # -------------------------------------------------------------
    with tab_view:
        st.subheader("Master Catalog Search & Overview")
        col_f1, col_f2 = st.columns([1, 2])
        with col_f1:
            filter_cat = st.selectbox("Filter by Category", ["All Categories"] + categories, key="view_filter_cat")
        with col_f2:
            search_query = st.text_input("🔍 Search Item Name", placeholder="Type item name...", key="view_search_query")

        query = "SELECT id, item_name, category, unit, current_stock, min_threshold, remarks FROM master_items WHERE 1=1"
        params = []

        if filter_cat != "All Categories":
            query += " AND category = ?"
            params.append(filter_cat)

        if search_query.strip():
            query += " AND item_name LIKE ?"
            params.append(f"%{search_query.strip()}%")

        query += " ORDER BY category ASC, item_name ASC"

        try:
            with get_db() as conn:
                df_items = pd.read_sql_query(query, conn, params=params)

            if not df_items.empty:
                df_display = df_items.rename(columns={
                    "id": "ID",
                    "item_name": "Item Description",
                    "category": "Category",
                    "unit": "Unit",
                    "current_stock": "Current Stock",
                    "min_threshold": "Low Stock Limit",
                    "remarks": "Remarks"
                })
                st.dataframe(df_display, use_container_width=True, hide_index=True)
                st.caption(f"Showing {len(df_display)} item(s).")
            else:
                st.info("No items found in master catalog.")

        except Exception as e:
            st.error(f"Error loading inventory items: {e}")

    # -------------------------------------------------------------
    # TAB 2: ADD NEW ITEM
    # -------------------------------------------------------------
    with tab_add:
        st.subheader("Add Master Inventory Item")
        with st.form("add_item_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                item_name = st.text_input("Item Description*", placeholder="e.g., Deformed Bar 16mm x 6m")
                category = st.selectbox("Site Category*", categories, key="add_cat")
                unit = st.selectbox("Unit of Measure*", units_list, key="add_unit")

            with col2:
                initial_stock = st.number_input("Opening Stock Balance", min_value=0.0, value=0.0, step=1.0)
                min_threshold = st.number_input("Low Stock Warning Threshold", min_value=0.0, value=10.0, step=1.0)
                remarks = st.text_input("Remarks / Storage Location", placeholder="e.g., Stockyard Bay 2")

            submit_add = st.form_submit_button("💾 Save to Master Catalog", use_container_width=True)

            if submit_add:
                if not item_name.strip():
                    st.error("⚠️ Item Description is required.")
                else:
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("SELECT id FROM master_items WHERE LOWER(item_name) = LOWER(?)", (item_name.strip(),))
                            if cursor.fetchone():
                                st.error(f"❌ An item named '{item_name.strip()}' already exists.")
                            else:
                                cursor.execute("""
                                    INSERT INTO master_items (item_name, category, unit, current_stock, min_threshold, remarks)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                """, (item_name.strip(), category, unit, initial_stock, min_threshold, remarks.strip()))
                                conn.commit()
                                st.success(f"✅ Added '{item_name.strip()}' to master inventory.")
                                st.rerun()
                    except Exception as e:
                        st.error(f"Failed to add item: {e}")

    # -------------------------------------------------------------
    # TAB 3: EDIT EXISTING ITEM
    # -------------------------------------------------------------
    with tab_edit:
        st.subheader("Edit Master Item Details")
        try:
            with get_db() as conn:
                df_all = pd.read_sql_query("SELECT * FROM master_items ORDER BY item_name ASC", conn)

            if not df_all.empty:
                selected_edit_item = st.selectbox("Select Item to Update", df_all["item_name"].tolist(), key="select_edit_item")
                item_data = df_all[df_all["item_name"] == selected_edit_item].iloc[0]

                with st.form("edit_item_form"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        new_item_name = st.text_input("Item Description*", value=item_data["item_name"])
                        
                        # Set default index for selectboxes safely
                        cat_idx = categories.index(item_data["category"]) if item_data["category"] in categories else 0
                        new_category = st.selectbox("Site Category*", categories, index=cat_idx, key="edit_cat")
                        
                        unit_idx = units_list.index(item_data["unit"]) if item_data["unit"] in units_list else 0
                        new_unit = st.selectbox("Unit of Measure*", units_list, index=unit_idx, key="edit_unit")

                    with col2:
                        new_stock = st.number_input("Adjust Current Stock", min_value=0.0, value=float(item_data["current_stock"]), step=1.0)
                        new_threshold = st.number_input("Low Stock Threshold", min_value=0.0, value=float(item_data["min_threshold"]), step=1.0)
                        new_remarks = st.text_input("Remarks", value=str(item_data["remarks"] or ""))

                    submit_edit = st.form_submit_button("🔄 Update Master Item", use_container_width=True)

                    if submit_edit:
                        if not new_item_name.strip():
                            st.error("⚠️ Item Description cannot be empty.")
                        else:
                            try:
                                with get_db() as conn:
                                    cursor = conn.cursor()
                                    cursor.execute("""
                                        UPDATE master_items 
                                        SET item_name = ?, category = ?, unit = ?, current_stock = ?, min_threshold = ?, remarks = ?
                                        WHERE id = ?
                                    """, (new_item_name.strip(), new_category, new_unit, new_stock, new_threshold, new_remarks.strip(), int(item_data["id"])))
                                    conn.commit()
                                    st.success(f"✅ Master record for '{new_item_name.strip()}' updated successfully.")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Failed to update item: {e}")
            else:
                st.info("No items available to edit.")
        except Exception as e:
            st.error(f"Error loading item data for edit: {e}")

    # -------------------------------------------------------------
    # TAB 4: DELETE ITEM
    # -------------------------------------------------------------
    with tab_delete:
        st.subheader("Remove Item from Database")
        if user_role.lower() != "admin":
            st.warning("🔒 Item deletion is restricted to Admin users.")
        else:
            try:
                with get_db() as conn:
                    df_del = pd.read_sql_query("SELECT item_name FROM master_items ORDER BY item_name ASC", conn)

                if not df_del.empty:
                    item_to_del = st.selectbox("Select Item to Remove", df_del["item_name"].tolist(), key="select_del_item")
                    st.error(f"⚠️ Warning: Deleting **'{item_to_del}'** permanently removes it from the master list.")
                    
                    if st.button("🔴 Permanently Delete Item", use_container_width=True):
                        try:
                            with get_db() as conn:
                                cursor = conn.cursor()
                                cursor.execute("DELETE FROM master_items WHERE item_name = ?", (item_to_del,))
                                conn.commit()
                                st.success(f"Deleted '{item_to_del}' from master database.")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Failed to delete item: {e}")
                else:
                    st.info("No items available to delete.")
            except Exception as e:
                st.error(f"Error fetching items for deletion: {e}")
