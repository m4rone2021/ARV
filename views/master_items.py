# views/manage_items.py
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db

def ensure_master_items_schema():
    """Ensures the master_items table exists and contains all expected columns."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS master_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                unit TEXT NOT NULL,
                current_stock REAL DEFAULT 0,
                min_threshold REAL DEFAULT 10
            )
        """)
        
        cursor.execute("PRAGMA table_info(master_items)")
        existing_cols = [row[1] for row in cursor.fetchall()]

        required_cols = {
            "category": "TEXT DEFAULT 'General'",
            "unit": "TEXT DEFAULT 'pcs'",
            "current_stock": "REAL DEFAULT 0",
            "min_threshold": "REAL DEFAULT 10"
        }

        for col_name, col_type in required_cols.items():
            if col_name not in existing_cols:
                try:
                    cursor.execute(f"ALTER TABLE master_items ADD COLUMN {col_name} {col_type}")
                except sqlite3.OperationalError:
                    pass
        conn.commit()

def render_manage_items(user_name, user_role):
    # Ensure database table structure is ready
    ensure_master_items_schema()

    st.title("📦 Manage Master Items")
    st.caption("Add new materials, update item details/thresholds, or delete inactive inventory items.")

    # Create tabs for Add, Edit, and Remove actions
    tab_add, tab_edit, tab_delete = st.tabs([
        "➕ Add New Item", 
        "✏️ Edit Item Details", 
        "🗑️ Remove / Delete Item"
    ])

    # -------------------------------------------------------------
    # TAB 1: ADD NEW ITEM
    # -------------------------------------------------------------
    with tab_add:
        st.subheader("➕ Add a New Master Inventory Item")
        with st.form("add_item_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                new_item_name = st.text_input("Item Name *", placeholder="e.g., Portland Cement Type 1")
                new_category = st.selectbox("Category", ["Construction Materials", "Electrical", "Plumbing", "Tools & Equipment", "General"])
                new_unit = st.text_input("Unit of Measure *", placeholder="e.g., bags, pcs, meters, kg")
            
            with col2:
                initial_stock = st.number_input("Initial Stock Quantity", min_value=0.0, step=1.0, value=0.0)
                min_threshold = st.number_input("Low Stock Warning Threshold", min_value=0.0, step=1.0, value=10.0)

            submit_add = st.form_submit_button("➕ Add Item to Master List")

            if submit_add:
                if not new_item_name.strip() or not new_unit.strip():
                    st.error("Item Name and Unit of Measure are required fields.")
                else:
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO master_items (item_name, category, unit, current_stock, min_threshold)
                                VALUES (?, ?, ?, ?, ?)
                            """, (new_item_name.strip(), new_category, new_unit.strip(), initial_stock, min_threshold))
                            conn.commit()
                        st.toast(f"✅ Item '{new_item_name.strip()}' added successfully!", icon="📦")
                        st.success(f"Added **{new_item_name.strip()}** to inventory.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error(f"❌ Item '{new_item_name.strip()}' already exists in the system!")

    # -------------------------------------------------------------
    # FETCH ALL ITEMS FOR EDIT / DELETE / DISPLAY
    # -------------------------------------------------------------
    with get_db() as conn:
        df_items = pd.read_sql_query("""
            SELECT id, item_name, category, unit, current_stock, min_threshold 
            FROM master_items 
            ORDER BY item_name ASC
        """, conn)

    # -------------------------------------------------------------
    # TAB 2: EDIT EXISTING ITEM
    # -------------------------------------------------------------
    with tab_edit:
        st.subheader("✏️ Edit Existing Master Item")
        if df_items.empty:
            st.info("No items available to edit. Add an item first.")
        else:
            item_list = df_items["item_name"].tolist()
            selected_edit_item = st.selectbox("Select Item to Modify", item_list, key="select_edit")

            # Extract selected item's current details
            item_data = df_items[df_items["item_name"] == selected_edit_item].iloc[0]

            with st.form("edit_item_form"):
                col1, col2 = st.columns(2)
                with col1:
                    updated_name = st.text_input("Item Name", value=str(item_data["item_name"]))
                    
                    categories = ["Construction Materials", "Electrical", "Plumbing", "Tools & Equipment", "General"]
                    current_cat_idx = categories.index(item_data["category"]) if item_data["category"] in categories else 4
                    updated_category = st.selectbox("Category", categories, index=current_cat_idx)
                    
                    updated_unit = st.text_input("Unit of Measure", value=str(item_data["unit"]))

                with col2:
                    updated_stock = st.number_input("Current Stock (Manual Override)", min_value=0.0, value=float(item_data["current_stock"]))
                    updated_threshold = st.number_input("Low Stock Threshold", min_value=0.0, value=float(item_data["min_threshold"]))

                submit_edit = st.form_submit_button("💾 Save Updated Changes")

                if submit_edit:
                    if not updated_name.strip() or not updated_unit.strip():
                        st.error("Item Name and Unit cannot be empty.")
                    else:
                        try:
                            with get_db() as conn:
                                cursor = conn.cursor()
                                cursor.execute("""
                                    UPDATE master_items 
                                    SET item_name = ?, category = ?, unit = ?, current_stock = ?, min_threshold = ?
                                    WHERE id = ?
                                """, (updated_name.strip(), updated_category, updated_unit.strip(), updated_stock, updated_threshold, int(item_data["id"])))
                                conn.commit()
                            st.toast("✅ Master item updated successfully!", icon="✏️")
                            st.success(f"Updated details for **{updated_name.strip()}**.")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error(f"❌ Another item named '{updated_name.strip()}' already exists.")

    # -------------------------------------------------------------
    # TAB 3: REMOVE / DELETE ITEM
    # -------------------------------------------------------------
    with tab_delete:
        st.subheader("🗑️ Delete an Item from Master Inventory")
        if df_items.empty:
            st.info("No items available to remove.")
        else:
            item_list_del = df_items["item_name"].tolist()
            selected_del_item = st.selectbox("Select Item to Permanently Delete", item_list_del, key="select_del")
            
            item_del_data = df_items[df_items["item_name"] == selected_del_item].iloc[0]
            st.warning(f"⚠️ Warning: Deleting **{selected_del_item}** (ID: {item_del_data['id']}) cannot be undone!")

            confirm_check = st.checkbox(f"I confirm that I want to delete '{selected_del_item}'")
            
            if st.button("🗑️ Permanently Delete Item", type="primary", disabled=not confirm_check):
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM master_items WHERE id = ?", (int(item_del_data["id"]),))
                    conn.commit()
                st.toast(f"🗑️ Deleted {selected_del_item} from master inventory.", icon="🗑️")
                st.success(f"Item **{selected_del_item}** has been removed.")
                st.rerun()

    # -------------------------------------------------------------
    # BOTTOM SECTION: OVERVIEW MASTER DATA TABLE
    # -------------------------------------------------------------
    st.divider()
    st.subheader("📋 Current Master Inventory Catalog")
    
    if not df_items.empty:
        df_display = df_items.rename(columns={
            "id": "Item ID",
            "item_name": "Item Name",
            "category": "Category",
            "unit": "Unit",
            "current_stock": "Current Balance",
            "min_threshold": "Min Threshold"
        })
        st.dataframe(df_display, use_container_width=True, hide_index=True)
    else:
        st.info("Master catalog is currently empty. Add your first item using the 'Add New Item' tab above.")
