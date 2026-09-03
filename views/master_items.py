# views/master_items.py
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db

def render_master_items():
    st.title("➕ Manage Master Items")
    st.caption("Configure master inventory items, set category classifications, unit types, and reorder thresholds.")

    tab_add, tab_edit, tab_list = st.tabs(["➕ Add New Item", "✏️ Edit Existing Item", "📑 Master Catalog"])

    # TAB 1: ADD NEW ITEM
    with tab_add:
        st.subheader("Add New Master Item")
        with st.form("add_item_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                item_name = st.text_input("Item / Material Name", placeholder="e.g., Cement Bags (40kg)")
                category = st.text_input("Category", placeholder="e.g., Concrete & Masonry")
            
            with col2:
                unit = st.text_input("Unit of Measurement", placeholder="e.g., bags, pcs, bd.ft, kgs")
                min_threshold = st.number_input("Minimum Alert Threshold", min_value=0.0, step=1.0, value=10.0)

            initial_stock = st.number_input("Initial Opening Stock Balance", min_value=0.0, step=1.0, value=0.0)
            submit_add = st.form_submit_button("💾 Save Item to Master Catalog")

            if submit_add:
                if not item_name.strip() or not category.strip() or not unit.strip():
                    st.error("Please fill out all required fields (Item Name, Category, and Unit).")
                else:
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                INSERT INTO master_items (item_name, category, unit, current_stock, min_threshold)
                                VALUES (?, ?, ?, ?, ?)
                            """, (item_name.strip(), category.strip(), unit.strip(), initial_stock, min_threshold))
                            conn.commit()
                            
                            st.toast(f"✅ Added {item_name.strip()} to Master Catalog!", icon="📦")
                            st.success(f"Item **{item_name.strip()}** successfully added.")
                            st.rerun()
                    except sqlite3.IntegrityError:
                        st.error(f"❌ An item named '{item_name.strip()}' already exists in the database.")
                    except sqlite3.OperationalError:
                        st.error("Database is busy. Please try again.")

    # TAB 2: EDIT EXISTING ITEM
    with tab_edit:
        st.subheader("Edit Master Item Settings")
        with get_db() as conn:
            df_items = pd.read_sql_query("SELECT * FROM master_items ORDER BY item_name ASC", conn)

        if df_items.empty:
            st.info("No master items configured yet.")
        else:
            item_list = df_items['item_name'].tolist()
            selected_item = st.selectbox("Select Item to Modify:", item_list)
            
            item_row = df_items[df_items['item_name'] == selected_item].iloc[0]

            with st.form("edit_item_form"):
                col1, col2 = st.columns(2)
                with col1:
                    edit_name = st.text_input("Item Name", value=item_row['item_name'])
                    edit_cat = st.text_input("Category", value=item_row['category'])
                with col2:
                    edit_unit = st.text_input("Unit", value=item_row['unit'])
                    edit_thresh = st.number_input("Min Threshold", min_value=0.0, value=float(item_row['min_threshold']))

                submit_edit_item = st.form_submit_button("💾 Update Master Settings")

                if submit_edit_item:
                    try:
                        with get_db() as conn:
                            cursor = conn.cursor()
                            cursor.execute("""
                                UPDATE master_items 
                                SET item_name = ?, category = ?, unit = ?, min_threshold = ?
                                WHERE id = ?
                            """, (edit_name.strip(), edit_cat.strip(), edit_unit.strip(), edit_thresh, item_row['id']))
                            conn.commit()
                            
                            st.toast(f"✅ Updated {edit_name.strip()} settings!", icon="✏️")
                            st.success("Master item updated successfully.")
                            st.rerun()
                    except sqlite3.IntegrityError:
                        st.error(f"❌ Item name '{edit_name.strip()}' is already taken.")

    # TAB 3: MASTER CATALOG LIST
    with tab_list:
        st.subheader("📋 Complete Master Item Catalog")
        with get_db() as conn:
            df_catalog = pd.read_sql_query("SELECT id, item_name, category, unit, current_stock, min_threshold FROM master_items ORDER BY category ASC, item_name ASC", conn)
        
        if df_catalog.empty:
            st.info("No items in catalog.")
        else:
            display_cat = df_catalog.rename(columns={
                "id": "ID",
                "item_name": "Item Name",
                "category": "Category",
                "unit": "Unit",
                "current_stock": "Current Stock Balance",
                "min_threshold": "Min Threshold"
            })
            st.dataframe(display_cat, use_container_width=True, hide_index=True)
