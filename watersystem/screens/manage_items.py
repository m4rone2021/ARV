"""Manage water system items: list, add, edit."""
import pandas as pd
import streamlit as st

from database import ARVError, ItemExistsError
from watersystem import config as cfg, lookups, items
from watersystem.screens import drive_upload


def _resolve_option(kind: str, widget_key: str, user_name: str) -> str:
    approved = lookups.list_approved(kind)
    if not approved:
        approved = getattr(cfg, f"DEFAULT_{kind.upper()}S", [])

    label_map = {"category": "Category", "material": "Material", "size": "Size"}
    label = label_map[kind]

    REQUEST_SENTINEL = "➕ Request new…"

    options = list(approved) + [REQUEST_SENTINEL]
    selected = st.selectbox(label, options, key=f"{widget_key}_{kind}_sel")

    if selected == REQUEST_SENTINEL:
        new_val = st.text_input(
            f"New {label}",
            key=f"{widget_key}_{kind}_new",
            placeholder=f"Type a new {label.lower()} — will be queued for approval",
        )
        if new_val.strip():
            try:
                status = lookups.request_new(kind, new_val.strip(), user_name)
                if status == "pending":
                    st.caption("⏳ Queued for admin approval.")
                elif status == "exists":
                    st.caption("✓ Already exists.")
            except Exception as e:
                st.caption(f"⚠️ {e}")
            return new_val.strip()
        return approved[0] if approved else ""

    return selected


def _render_form(existing: dict | None, user_name: str, is_admin: bool):
    is_edit = existing is not None
    prefix = "edit" if is_edit else "add"

    st.markdown(f"### {'✏️ Edit item' if is_edit else '➕ Add new water item'}")

    with st.form(f"{prefix}_item_form", clear_on_submit=not is_edit):
        c1, c2 = st.columns(2)

        with c1:
            item_name = st.text_input(
                "Item name*",
                value=existing["item_name"] if is_edit else "",
            )
            category = _resolve_option("category", f"{prefix}_item", user_name)
            material = _resolve_option("material", f"{prefix}_item", user_name)
            unit_options = cfg.DEFAULT_UNITS
            default_unit = (
                existing["unit"]
                if is_edit and existing["unit"] in unit_options
                else unit_options[0]
            )
            unit = st.selectbox(
                "Unit*", unit_options, index=unit_options.index(default_unit)
            )

        with c2:
            size = _resolve_option("size", f"{prefix}_item", user_name)
            cost = st.number_input(
                "Cost (PHP)", min_value=0.0, step=0.01, format="%.2f",
                value=float(existing["cost_php"] or 0) if is_edit else 0.0,
            )
            shipping = st.number_input(
                "Shipping (PHP)", min_value=0.0, step=0.01, format="%.2f",
                value=float(existing["shipping_php"] or 0) if is_edit else 0.0,
            )
            markup = st.number_input(
                "Markup % (optional)", min_value=0.0, step=0.5, format="%.2f",
                value=float(existing["markup_pct"] or 0) if is_edit else 0.0,
            )
            manual_price = st.number_input(
                "Manual selling price (optional)",
                min_value=0.0, step=0.01, format="%.2f",
                value=float(existing["selling_price_php"] or 0) if is_edit else 0.0,
            )

        c3, c4 = st.columns(2)
        with c3:
            min_threshold = st.number_input(
                "Min threshold", min_value=0.0, step=1.0,
                value=float(existing["min_threshold"] or 0) if is_edit else 0.0,
            )
            if not is_edit:
                initial_stock = st.number_input(
                    "Initial stock", min_value=0.0, step=1.0, value=0.0,
                )
            else:
                initial_stock = 0.0
                st.caption(f"Current stock: {existing['current_stock']}")

        with c4:
            remarks = st.text_area(
                "Remarks",
                value=existing["remarks"] if is_edit and existing["remarks"] else "",
            )

        st.markdown("**Photo**")
        if is_edit and existing.get("image_url"):
            st.caption(f"Current image: [view]({existing['image_url']})")
            try:
                st.image(existing["image_url"], width=200)
            except Exception:
                pass

        uploaded = st.file_uploader(
            "Upload new photo (jpg/png)",
            type=["jpg", "jpeg", "png"],
            key=f"{prefix}_img",
        )

        submitted = st.form_submit_button(
            "💾 Save item", type="primary", width="stretch",
        )

    if not submitted:
        return

    image_url = existing.get("image_url") if is_edit else None
    if uploaded is not None:
        try:
            image_url = drive_upload.upload_image(
                uploaded.getvalue(),
                uploaded.name,
                item_name_hint=item_name,
            )
        except Exception as e:
            st.error(f"⚠️ Image upload failed: {e}")
            st.stop()

    payload = {
        "item_name": item_name,
        "category": category,
        "material": material,
        "size": size,
        "unit": unit,
        "cost_php": cost,
        "shipping_php": shipping,
        "markup_pct": markup if markup > 0 else None,
        "selling_price_php": manual_price if manual_price > 0 else None,
        "min_threshold": min_threshold,
        "initial_stock": initial_stock,
        "remarks": remarks,
        "image_url": image_url,
    }

    try:
        if is_edit:
            items.update_item(existing["id"], payload)
            st.success(f"✅ Updated **{item_name}**.")
        else:
            items.create_item(payload)
            st.success(f"✅ Added **{item_name}**.")
        st.session_state["ws_flash"] = "success"
        st.rerun()
    except ItemExistsError as e:
        st.error(f"⚠️ {e}")
    except ARVError as e:
        st.error(f"⚠️ {e}")
    except ValueError as e:
        st.error(f"⚠️ {e}")
    except Exception as e:
        st.error(f"⚠️ Unexpected error: {e}")


def render(user_name: str, is_admin: bool):
    st.title("📦 Manage Water System Items")
    st.caption("Add, edit, and view water system fittings, valves, meters, and consumables.")

    if st.session_state.pop("ws_flash", None):
        st.success("Operation completed.")

    tabs = st.tabs(["📋 Item list", "➕ Add item", "✏️ Edit item"])

    with tabs[0]:
        try:
            all_items = items.list_items()
        except ARVError as e:
            st.error(f"⚠️ {e}")
            all_items = []

        if not all_items:
            st.info("No water system items yet. Use **Add item** tab to create one.")
        else:
            df = pd.DataFrame(all_items)
            display_cols = [
                "item_name", "category", "material", "size", "unit",
                "current_stock", "reserved_stock", "min_threshold",
                "total_cost_php", "selling_price_php", "image_url",
            ]
            display_cols = [c for c in display_cols if c in df.columns]
            df_disp = df[display_cols].rename(columns={
                "item_name": "Name",
                "category": "Category",
                "material": "Material",
                "size": "Size",
                "unit": "Unit",
                "current_stock": "Stock",
                "reserved_stock": "Reserved",
                "min_threshold": "Min",
                "total_cost_php": "Cost (PHP)",
                "selling_price_php": "Sell (PHP)",
                "image_url": "Photo",
            })
            st.dataframe(df_disp, width="stretch", hide_index=True)
            st.caption(f"{len(df)} water system item(s).")

    with tabs[1]:
        _render_form(None, user_name, is_admin)

    with tabs[2]:
        try:
            all_items = items.list_items()
        except ARVError as e:
            st.error(f"⚠️ {e}")
            all_items = []

        if not all_items:
            st.info("No items to edit yet.")
        else:
            by_name = {it["item_name"]: it for it in all_items}
            picked = st.selectbox("Select item to edit", sorted(by_name.keys()))
            _render_form(by_name[picked], user_name, is_admin)