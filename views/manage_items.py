import pandas as pd
import streamlit as st

from database import sb

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


def get_all_categories():
    """Fetch distinct categories from Supabase + merge with defaults."""
    categories = list(DEFAULT_CATEGORIES)
    try:
        res = sb().table("master_items").select("category").execute()
        existing = {row["category"] for row in (res.data or []) if row.get("category")}
        for cat in existing:
            if cat and cat not in categories:
                categories.append(cat)
    except Exception:
        pass
    return sorted(set(categories))


def render_manage_items(user_name, user_role):
    st.title("📦 Master Item Catalog")
    st.caption("View and maintain site inventory, reserved allocations, and available stock.")

    is_admin = user_role == "Admin"

    if is_admin:
        tab_view, tab_add, tab_edit, tab_delete = st.tabs(
            ["📋 Catalog", "➕ Add Item", "✏️ Edit Item", "🗑️ Delete"]
        )
    else:
        (tab_view,) = st.tabs(["📋 Catalog"])
        st.info("ℹ️ Read-Only Mode: Only Administrators can create, edit, or delete master items.")

    available_categories = get_all_categories()

    # ================================================================
    # VIEW CATALOG
    # ================================================================
    with tab_view:
        st.subheader("Inventory & Stock Levels")

        search_query = st.text_input("🔍 Search Item Name", placeholder="Type item name...")
        selected_cat = st.selectbox("📂 Filter Category", ["All"] + available_categories)

        try:
            query = (
                sb()
                .table("master_items")
                .select("id, item_name, category, unit, current_stock, reserved_stock, min_threshold, remarks")
            )

            if search_query.strip():
                query = query.ilike("item_name", f"%{search_query.strip()}%")
            if selected_cat != "All":
                query = query.eq("category", selected_cat)

            res = query.order("item_name").execute()
            df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error loading master items: {e}")
            return

        if df.empty:
            st.info("No master items found matching your filters.")
            return

        df["available_stock"] = df["current_stock"].fillna(0) - df["reserved_stock"].fillna(0)

        df_display = df.rename(columns={
            "id": "ID",
            "item_name": "Item Name",
            "category": "Category",
            "unit": "Unit",
            "current_stock": "Stock In Shop (Total)",
            "reserved_stock": "Reserved Stock",
            "available_stock": "Available Stock",
            "min_threshold": "Min Threshold",
            "remarks": "Remarks",
        })

        view_mode = st.radio(
            "Display Mode",
            ["Cards (Mobile)", "Full Table"],
            horizontal=True,
            label_visibility="collapsed",
        )

        if view_mode == "Cards (Mobile)":
            for _, item in df_display.iterrows():
                is_low = item["Available Stock"] <= item["Min Threshold"]
                badge = "🔴 LOW" if is_low else "🟢 OK"
                with st.expander(f"{badge} {item['Item Name']} ({item['Category']})"):
                    st.markdown(f"**Available:** `{item['Available Stock']:.2f} {item['Unit']}`")
                    st.markdown(f"**Total In Shop:** `{item['Stock In Shop (Total)']:.2f} {item['Unit']}`")
                    st.markdown(f"**Reserved:** `{item['Reserved Stock']:.2f}` | **Min Threshold:** `{item['Min Threshold']:.2f}`")
                    if item["Remarks"]:
                        st.caption(f"Remarks: {item['Remarks']}")
        else:
            st.dataframe(
                df_display,
                width='stretch',
                hide_index=True,
                column_config={
                    "Stock In Shop (Total)": st.column_config.NumberColumn(format="%.2f"),
                    "Reserved Stock": st.column_config.NumberColumn(format="%.2f"),
                    "Available Stock": st.column_config.NumberColumn(format="%.2f"),
                    "Min Threshold": st.column_config.NumberColumn(format="%.2f"),
                },
            )

    # ================================================================
    # ADMIN: ADD ITEM
    # ================================================================
    if is_admin:
        with tab_add:
            st.subheader("Add Master Item")
            with st.form("add_item_form", clear_on_submit=True):
                item_name = st.text_input("Item Name*")
                category = st.selectbox("Select Existing Category*", options=available_categories)
                new_category = st.text_input("Or Add New Category (Optional)")
                unit = st.selectbox("Unit of Measure*", options=UNIT_OPTIONS)
                initial_stock = st.number_input("Initial Stock Quantity*", min_value=0.0, step=1.0, value=0.0, format="%.2f")
                min_threshold = st.number_input("Low Stock Threshold Alert*", min_value=0.0, step=1.0, value=0.0, format="%.2f")
                remarks = st.text_input("Remarks / Notes (Optional)")

                submit_add = st.form_submit_button("💾 Save Item to Catalog", width='stretch')

                if submit_add:
                    final_category = new_category.strip() if new_category.strip() else category.strip()
                    clean_name = item_name.strip()
                    clean_unit = unit.strip()

                    if not clean_name or not final_category or not clean_unit:
                        st.error("⚠️ All required fields (*) must be filled.")
                    else:
                        try:
                            sb().table("master_items").insert({
                                "item_name": clean_name,
                                "category": final_category,
                                "unit": clean_unit,
                                "current_stock": float(initial_stock),
                                "reserved_stock": 0.0,
                                "min_threshold": float(min_threshold),
                                "remarks": remarks.strip() or None,
                            }).execute()
                            st.success(f"Master item **{clean_name}** added successfully!")
                            st.rerun()
                        except Exception as e:
                            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                                st.error(f"⚠️ An item named **{clean_name}** already exists.")
                            else:
                                st.error(f"Failed to save item: {e}")

        # ============================================================
        # ADMIN: EDIT ITEM
        # ============================================================
        with tab_edit:
            st.subheader("Modify Catalog Item")
            try:
                res = (
                    sb()
                    .table("master_items")
                    .select("id, item_name, category, unit, current_stock, reserved_stock, min_threshold, remarks")
                    .order("item_name")
                    .execute()
                )
                df_all = pd.DataFrame(res.data or [])
            except Exception as e:
                st.error(f"Error fetching item details: {e}")
                df_all = pd.DataFrame()

            if df_all.empty:
                st.info("No items available to edit.")
            else:
                selected_item_name = st.selectbox(
                    "Select Item to Edit", df_all["item_name"].tolist(), key="edit_item_selector"
                )
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
                    edit_category = st.selectbox("Select Category*", options=edit_cat_options, index=default_cat_index)
                    edit_new_category = st.text_input("Or Change to New Category (Optional)")
                    edit_unit = st.selectbox("Unit*", options=edit_unit_options, index=default_unit_index)
                    edit_stock = st.number_input(
                        "Stock In Shop (Total)*",
                        min_value=0.0,
                        value=float(selected_row["current_stock"]),
                        step=1.0,
                        format="%.2f",
                    )
                    edit_reserved = st.number_input(
                        "Reserved Stock*",
                        min_value=0.0,
                        value=float(selected_row["reserved_stock"] or 0),
                        step=1.0,
                        format="%.2f",
                    )
                    edit_threshold = st.number_input(
                        "Min Threshold Alert*",
                        min_value=0.0,
                        value=float(selected_row["min_threshold"] or 0),
                        step=1.0,
                        format="%.2f",
                    )
                    edit_remarks = st.text_input("Remarks", value=selected_row["remarks"] or "")

                    submit_edit = st.form_submit_button("🔄 Update Master Item", width='stretch')

                    if submit_edit:
                        final_edit_cat = edit_new_category.strip() if edit_new_category.strip() else edit_category.strip()

                        if not final_edit_cat:
                            st.error("⚠️ Category cannot be empty.")
                        elif edit_stock < edit_reserved:
                            st.error(f"❌ Stock in Shop ({edit_stock:.2f}) cannot be less than Reserved Stock ({edit_reserved:.2f}).")
                        else:
                            try:
                                sb().table("master_items").update({
                                    "category": final_edit_cat,
                                    "unit": edit_unit.strip(),
                                    "current_stock": float(edit_stock),
                                    "reserved_stock": float(edit_reserved),
                                    "min_threshold": float(edit_threshold),
                                    "remarks": edit_remarks.strip() or None,
                                }).eq("item_name", selected_item_name).execute()
                                st.success(f"Item **{selected_item_name}** updated successfully.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to update item: {e}")

        # ============================================================
        # ADMIN: DELETE ITEM
        # ============================================================
        with tab_delete:
            st.subheader("Remove Catalog Item")
            st.warning("⚠️ Deleting an item removes it permanently from the Master Catalog.")

            try:
                res = (
                    sb()
                    .table("master_items")
                    .select("id, item_name, reserved_stock")
                    .order("item_name")
                    .execute()
                )
                df_del = pd.DataFrame(res.data or [])
            except Exception as e:
                st.error(f"Error loading items for deletion: {e}")
                df_del = pd.DataFrame()

            if df_del.empty:
                st.info("No catalog items available to delete.")
            else:
                with st.form("delete_item_form"):
                    target_item = st.selectbox("Select Item to Delete", df_del["item_name"].tolist())
                    submit_delete = st.form_submit_button("🗑️ Permanently Delete Item", width='stretch')

                    if submit_delete:
                        target_row = df_del[df_del["item_name"] == target_item].iloc[0]
                        if float(target_row["reserved_stock"] or 0) > 0:
                            st.error(f"Cannot delete **{target_item}** because it has active site reservations.")
                        else:
                            try:
                                sb().table("master_items").delete().eq("item_name", target_item).execute()
                                st.success(f"Item **{target_item}** removed from Master Catalog.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to delete item: {e}")
