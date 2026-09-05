import sqlite3
import pandas as pd
import streamlit as st
from database import get_db, backup_db_to_gdrive

DEFAULT_CATEGORIES = [
    "Fuel & Oils",
    "Construction Materials",
    "Steel / Rebar",
    "Nails & Fasteners",
    "Cutting & Grinding Consumables",
    "Welding Supplies & PPE",
    "General Site Supplies",
]

UNIT_OPTIONS = ["liters", "bags", "packs", "pcs", "sheets", "rolls"]


def trigger_gdrive_sync():
    """Triggers background sync to Google Drive without interrupting UI execution."""
    try:
        backup_db_to_gdrive()
        st.toast("☁️ Synced to Google Drive!", icon="✅")
    except Exception as e:
        st.warning(f"⚠️ Saved locally, but Drive backup failed: {e}")


def get_all_categories():
    """Fetches categories from DB and merges them with default options."""
    categories = list(DEFAULT_CATEGORIES)
    try:
        with get_db() as conn:
            df = pd.read_sql_query("SELECT DISTINCT category FROM master_items", conn)
            existing_cats = df["category"].dropna().str.strip().tolist()
            for cat in existing_cats:
                if cat and cat not in categories:
                    categories.append(cat)
    except Exception:
        pass
    return sorted(list(set(categories)))


def render_manage_items(user_name, user_role):
    st.title("📦 Master Item Catalog")
    st.caption("View and maintain master site inventory, reserved allocations, and available stock levels.")

    is_admin = user_role == "Admin"

    if is_admin:
        tab_view, tab_add, tab_edit, tab_delete = st.tabs([
            "📋 View Catalog",
            "➕ Add New Item",
            "✏️ Edit Item / Thresholds",
            "🗑️ Delete Item",
        ])
    else:
        (tab_view,) = st.tabs(["📋 View Catalog"])
        st.info("ℹ️ Read-Only Mode: Only Administrators can create, edit, or delete master items.")

    available_categories = get_all_categories()

    # VIEW CATALOG TAB
    with tab_view:
        st.subheader("Inventory Items & Stock Breakdown")
        col_search, col_cat = st.columns([2, 1])

        with col_search:
            search_query = st.text_input("Search Item Name", placeholder="Type item name...")
        with col_cat:
            selected_cat = st.selectbox("Filter Category", ["All"] + available_categories)

        try:
            query = """
                SELECT 
                    id, item_name, category, unit, 
                    current_stock AS stock_in_shop,
                    COALESCE(reserved_stock, 0) AS reserved_stock,
                    (current_stock - COALESCE(reserved_stock, 0)) AS available_stock,
                    min_threshold, remarks 
                FROM master_items WHERE 1=1
            """
            params = []

            if search_query.strip():
                query += " AND item_name LIKE ?"
                params.append(f"%{search_query.strip()}%")

            if selected_cat != "All":
                query += " AND category = ?"
                params.append(selected_cat)

            query += " ORDER BY item_name ASC"

            with get_db() as conn:
                df = pd.read_sql_query(query, conn, params=params)

            if not df.empty:
                df_display = df.rename(columns={
                    "id": "ID",
                    "item_name": "Item Name",
                    "category": "Category",
                    "unit": "Unit",
                    "stock_in_shop": "Stock In Shop (Total)",
                    "reserved_stock": "Reserved Stock",
                    "available_stock": "Available Stock",
                    "min_threshold": "Min Threshold",
                    "remarks": "Remarks",
                })
                st.dataframe(
                    df_display,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Stock In Shop (Total)": st.column_config.NumberColumn(format="%.2f"),
                        "Reserved Stock": st.column_config.NumberColumn(format="%.2f"),
                        "Available Stock": st.column_config.NumberColumn(format="%.2f"),
                        "Min Threshold": st.column_config.NumberColumn(format="%.2f"),
                    },
                )
            else:
                st.info("No master items found matching your filters.")

        except Exception as e:
            st.error(f"Error loading master items: {e}")

    # ADMIN TABS
    if is_admin:
        # ADD ITEM TAB
        with tab_add:
            st.subheader("Add Master Item")
            with st.form("add_item_form", clear_on_submit=True):
                col1, col2 = st.columns(2)

                with col1:
                    item_name = st.text_input("Item Name*")
                    category = st.selectbox("Select Existing Category*", options=available_categories)
                    new_category = st.text_input("Or Add New Category (Optional)", placeholder="Type new category...")
                    unit = st.selectbox("Unit of Measure*", options=UNIT_OPTIONS)

                with col2:
                    initial_stock = st.number_input("Initial Stock Quantity*", min_value=0.0, step=1.0, value=0.0, format="%.2f")
                    min_threshold = st.number_input("Low Stock Threshold Alert*", min_value=0.0, step=1.0, value=0.0, format="%.2f")
                    remarks = st.text_input("Remarks / Notes (Optional)")

                submit_add = st.form_submit_button("💾 Save Item to Catalog", use_container_width=True)

                if submit_add:
                    final_category = new_category.strip() if new_category.strip() else category.strip()
                    clean_name = item_name.strip()
                    clean_unit = unit.strip()

                    if not clean_name or not final_category or not clean_unit:
                        st.error("⚠️ All required fields (*) must be filled.")
                    else:
                        try:
                            with get_db() as conn:
                                cursor = conn.cursor()
                                cursor.execute("""
                                    INSERT INTO master_items (item_name, category, unit, current_stock, reserved_stock, min_threshold, remarks)
                                    VALUES (?, ?, ?, ?, 0.0, ?, ?)
                                """, (clean_name, final_category, clean_unit, initial_stock, min_threshold, remarks.strip()))
                                conn.commit()

                                trigger_gdrive_sync()
                                st.success(f"Master item **{clean_name}** added successfully!")
                                st.rerun()
                        except sqlite3.IntegrityError:
                            st.error(f"⚠️ An item named **{clean_name}** already exists.")
                        except sqlite3.OperationalError as e:
                            st.error(f"Failed to save item: {e}")

        # EDIT ITEM TAB
        with tab_edit:
            st.subheader("Modify Catalog Item")
            try:
                with get_db() as conn:
                    df_all = pd.read_sql_query("""
                        SELECT id, item_name, category, unit, current_stock, 
                               COALESCE(reserved_stock, 0) AS reserved_stock, min_threshold, remarks 
                        FROM master_items ORDER BY item_name ASC
                    """, conn)

                if not df_all.empty:
                    selected_item_name = st.selectbox("Select Item to Edit", df_all["item_name"].tolist(), key="edit_item_selector")
                    selected_row = df_all[df_all["item_name"] == selected_item_name].iloc[0]

                    current_cat = str(selected_row["category"]).strip()
                    edit_cat_options = list(available_categories)
                    if current_cat and current_cat not in edit_cat_options:
                        edit_cat_options.append(current_cat)
                        edit_cat_options.sort()
                    default_cat_index = edit_cat_options.index(current_cat) if current_cat in edit_cat_options else 0

                    current_unit = str(selected_row["unit"]).strip()
                    edit_unit_options = list(UNIT_OPTIONS)
                    if current_unit and current_unit not in edit_unit_options:
                        edit_unit_options.append(current_unit)
                        edit_unit_options.sort()
                    default_unit_index = edit_unit_options.index(current_unit) if current_unit in edit_unit_options else 0

                    with st.form(f"edit_item_form_{selected_item_name}"):
                        col1, col2 = st.columns(2)

                        with col1:
                            edit_category = st.selectbox("Select Category*", options=edit_cat_options, index=default_cat_index)
                            edit_new_category = st.text_input("Or Change to New Category (Optional)")
                            edit_unit = st.selectbox("Unit*", options=edit_unit_options, index=default_unit_index)
                            edit_stock = st.number_input("Stock In Shop (Total)*", min_value=0.0, value=float(selected_row["current_stock"]), step=1.0, format="%.2f")

                        with col2:
                            st.text_input("Reserved Stock (Read-Only)", value=f"{selected_row['reserved_stock']} {selected_row['unit']}", disabled=True)
                            edit_threshold = st.number_input("Min Threshold Alert*", min_value=0.0, value=float(selected_row["min_threshold"]), step=1.0, format="%.2f")
                            edit_remarks = st.text_input("Remarks", value=selected_row["remarks"] if selected_row["remarks"] else "")

                        submit_edit = st.form_submit_button("🔄 Update Master Item", use_container_width=True)

                        if submit_edit:
                            final_edit_cat = edit_new_category.strip() if edit_new_category.strip() else edit_category.strip()

                            if not final_edit_cat:
                                st.error("⚠️ Category cannot be empty.")
                            elif edit_stock < float(selected_row["reserved_stock"]):
                                st.error(f"❌ Stock in Shop cannot be less than Reserved Stock ({selected_row['reserved_stock']} {selected_row['unit']}).")
                            else:
                                try:
                                    with get_db() as conn:
                                        cursor = conn.cursor()
                                        cursor.execute("""
                                            UPDATE master_items
                                            SET category = ?, unit = ?, current_stock = ?, min_threshold = ?, remarks = ?
                                            WHERE item_name = ?
                                        """, (final_edit_cat, edit_unit.strip(), edit_stock, edit_threshold, edit_remarks.strip(), selected_item_name))
                                        conn.commit()

                                        trigger_gdrive_sync()
                                        st.success(f"Item **{selected_item_name}** updated successfully.")
                                        st.rerun()
                                except sqlite3.OperationalError as e:
                                    st.error(f"Failed to update item: {e}")
                else:
                    st.info("No items available to edit.")

            except Exception as e:
                st.error(f"Error fetching item details: {e}")

        # DELETE ITEM TAB
        with tab_delete:
            st.subheader("Remove Catalog Item")
            st.warning("⚠️ Deleting an item removes it permanently from the Master Catalog.")

            try:
                with get_db() as conn:
                    df_del = pd.read_sql_query("SELECT id, item_name, COALESCE(reserved_stock, 0) AS reserved_stock FROM master_items ORDER BY item_name ASC", conn)

                if not df_del.empty:
                    with st.form("delete_item_form"):
                        target_item = st.selectbox("Select Item to Delete", df_del["item_name"].tolist())
                        submit_delete = st.form_submit_button("🗑️ Permanently Delete Item", use_container_width=True)

                        if submit_delete:
                            target_row = df_del[df_del["item_name"] == target_item].iloc[0]
                            if float(target_row["reserved_stock"]) > 0:
                                st.error(f"Cannot delete **{target_item}** because it has active site reservations.")
                            else:
                                try:
                                    with get_db() as conn:
                                        cursor = conn.cursor()
                                        cursor.execute("DELETE FROM master_items WHERE item_name = ?", (target_item,))
                                        conn.commit()

                                        trigger_gdrive_sync()
                                        st.success(f"Item **{target_item}** removed from Master Catalog.")
                                        st.rerun()
                                except sqlite3.OperationalError as e:
                                    st.error(f"Failed to delete item: {e}")
                else:
                    st.info("No catalog items available to delete.")

            except Exception as e:
                st.error(f"Error loading items for deletion: {e}")
