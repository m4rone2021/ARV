# views/manage_items.py
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db

def render_manage_items(user_name, user_role):
    st.title("📦 Manage Master Items")
    st.caption("Add, view, and manage stock items and safety threshold limits across site categories.")

    # Retrieve categories from app session state, or fallback to default site categories
    categories = st.session_state.get("categories", [
        "Fuel & Oils",
        "Construction Materials",
        "Steel / Rebar",
        "Nails & Fasteners",
        "Cutting & Grinding Consumables",
        "Welding Supplies & PPE",
        "General Site Supplies"
    ])

    # Standard units of measurement
    units_list = ["Pcs", "Bags", "Kg", "Tons", "Liters", "Gallons", "Boxes", "Bundles", "Rolls", "Pairs", "Sets", "Meters"]

    tab_add, tab_view = st.tabs(["➕ Add New Item", "📋 Master Items Catalog"])

    # -------------------------------------------------------------
    # TAB 1: ADD NEW ITEM FORM
    # -------------------------------------------------------------
    with tab_add:
        st.subheader("Add Master Item")
        with st.form("add_item_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                item_name = st.text_input("Item Name / Description*", placeholder="e.g., Diesel Fuel, Portland Cement, Rebar 12mm")
                category = st.selectbox("Site Category*", categories)
                unit = st.selectbox("Unit of Measure*", units_list)

            with col2:
                initial_stock = st.number_input("Initial Opening Stock", min_value=0.0, value=0.0, step=1.0)
                min_threshold = st.number_input("Low Stock Threshold Warning Limit", min_value=0.0, value=10.0, step=1.0)
                remarks = st.text_input("Remarks / Notes", placeholder="e.g., Supplier specs, storage bay location")

            submit_btn = st.form_submit_button("💾 Save Item to Master Catalog", use_container_width=True)

            if submit_btn:
                if not item_name.strip():
                    st.error("⚠️ Item Name is required.")
                else:
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            # Check for duplicates
                            cursor.execute("SELECT id FROM master_items WHERE LOWER(item_name) = LOWER(?)", (item_name.strip(),))
                            if cursor.fetchone():
                                st.error(f"❌ An item named '{item_name.strip()}' already exists in the master list.")
                            else:
                                cursor.execute("""
                                    INSERT INTO master_items (item_name, category, unit, current_stock, min_threshold, remarks)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                """, (item_name.strip(), category, unit, initial_stock, min_threshold, remarks.strip()))
                                conn.commit()
                                st.success(f"✅ Successfully added '{item_name.strip()}' under '{category}'.")
                                st.rerun()
                    except Exception as e:
                        st.error(f"An error occurred while saving the item: {e}")

    # -------------------------------------------------------------
    # TAB 2: MASTER ITEMS CATALOG & MANAGEMENT
    # -------------------------------------------------------------
    with tab_view:
        st.subheader("Master Inventory Catalog")

        # Filtering Controls
        col_f1, col_f2 = st.columns([1, 2])
        with col_f1:
            filter_cat = st.selectbox("Filter by Category", ["All Categories"] + categories)
        with col_f2:
            search_query = st.text_input("🔍 Search Item Name", placeholder="Type item name to filter...")

        # Build SQL Query dynamically based on filters
        query = "SELECT id, item_name, category, unit, current_stock, min_threshold, remarks FROM master_items WHERE 1=1"
        params = []

        if filter_cat != "All Categories":
            query += " AND category = ?"
            params.append(filter_cat)

        if search_query.strip():
            query += " AND item_name LIKE ?"
            params.append(f"%{search_query.strip()}%")

        query += " ORDER BY category ASC, item_name ASC"

        with get_db() as conn:
            df_items = pd.read_sql_query(query, conn, params=params)

        if not df_items.empty:
            df_display = df_items.rename(columns={
                "id": "ID",
                "item_name": "Item Name / Description",
                "category": "Category",
                "unit": "Unit",
                "current_stock": "Current Stock",
                "min_threshold": "Low Stock Limit",
                "remarks": "Remarks"
            })
            st.dataframe(df_display, use_container_width=True, hide_index=True)

            # ADMIN ONLY: Delete / Remove Item Feature
            if user_role.lower() == "admin":
                st.divider()
                st.subheader("🗑️ Delete Master Item (Admin Only)")
                with st.expander("Warning: Deleting an item removes it permanently"):
                    item_to_delete = st.selectbox(
                        "Select item to delete",
                        df_items["item_name"].tolist(),
                        key="delete_item_select"
                    )
                    confirm_delete = st.button("🔴 Confirm Delete Item", use_container_width=True)

                    if confirm_delete:
                        try:
                            with get_db() as conn:
                                cursor = conn.cursor()
                                cursor.execute("DELETE FROM master_items WHERE item_name = ?", (item_to_delete,))
                                conn.commit()
                                st.success(f"Deleted '{item_to_delete}' from database.")
                                st.rerun()
                        except Exception as e:
                            st.error(f"Failed to delete item: {e}")
        else:
            st.info("No items found matching the selected filters.")
