"""Water system Stock OUT — batch issue, scoped to warehouse='watersystem'."""
import pandas as pd
from datetime import date

import streamlit as st

from database import NetworkError, issue_stock_batch, sb
from watersystem import config as cfg


PLACEHOLDER = "-- Select an item --"


def _fmt_qty(x):
    return f"{x:,.2f}".rstrip("0").rstrip(".") if x % 1 else f"{int(x):,}"


def _reset_cart():
    st.session_state.wso_cart = []


def _reset_all():
    _reset_cart()
    for k in (
        "wso_req_by_input", "wso_dest_input", "wso_proj_input", "wso_tx_date_input",
        "wso_add_item_version", "wso_add_version",
    ):
        st.session_state.pop(k, None)


def _bump_add_versions():
    st.session_state["wso_add_version"] = st.session_state.get("wso_add_version", 0) + 1
    st.session_state["wso_add_item_version"] = st.session_state.get("wso_add_item_version", 0) + 1


def render(user_name: str, is_admin: bool):
    st.title("📤 Water System — Stock OUT")
    st.caption("Record outgoing water system materials and validate real-time stock.")

    if "wso_cart" not in st.session_state:
        st.session_state.wso_cart = []

    flash = st.session_state.pop("ws_flash", None)
    if flash == "success":
        st.success("Operation completed.")

    tab_record, tab_history = st.tabs(
        ["Issue Stock / Requisition", "Outgoing Stock History"]
    )

    with tab_record:
        st.subheader("New Water Stock Requisition")

        try:
            res = (
                sb().table("master_items")
                .select(
                    "item_name, category, unit, current_stock, reserved_stock, min_threshold, size, "
                    "image_url, cost_php, shipping_php, total_cost_php, selling_price_php"
                )
                .eq("warehouse", cfg.WAREHOUSE)
                .order("item_name").execute()
            )
            items_df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error loading water items: {e}")
            return

        if items_df.empty:
            st.info("No water items found. Add items first before issuing stock.")
            return

        items_df["current_stock"] = items_df["current_stock"].fillna(0)
        items_df["reserved_stock"] = items_df["reserved_stock"].fillna(0)
        items_df["available"] = items_df["current_stock"] - items_df["reserved_stock"]

        with st.container(border=True):
            st.markdown("##### Requisition Details")
            c1, c2 = st.columns(2)
            with c1:
                input_requested_by = st.text_input(
                    "Requested By (Engineer / Officer)*",
                    placeholder="e.g., Engr. John Doe",
                    key="wso_req_by_input",
                )
            with c2:
                input_destination = st.text_input(
                    "Destination / Location*",
                    placeholder="e.g., Purok 4 Waterline",
                    key="wso_dest_input",
                )
            input_project = st.text_input(
                "Project Name / Code*",
                placeholder="e.g., WS-2026-A",
                key="wso_proj_input",
            )
            input_tx_date = st.date_input(
                "Transaction Date*", value=date.today(),
                key="wso_tx_date_input",
                help="Date the transaction actually occurred. Backdating is allowed.",
            )
            st.caption("Requisition IDs will be generated per project.")

        header_ok = bool(
            input_requested_by.strip()
            and input_destination.strip()
            and input_project.strip()
        )
        st.divider()

        with st.container(border=True):
            st.markdown("##### Add Item to Requisition")
            v_item = st.session_state.get("wso_add_item_version", 0)
            names = sorted(items_df["item_name"].unique().tolist())
            selected_name = st.selectbox(
                "Select Item*", [PLACEHOLDER] + names, key=f"wso_add_item_v{v_item}",
            )
            has_item = selected_name != PLACEHOLDER

            if not has_item:
                st.info("Pick an item from the list to continue.")
            else:
                subset = items_df[items_df["item_name"] == selected_name]
                size_options = subset["size"].fillna("").tolist()
                if len(size_options) == 1:
                    picked_size = size_options[0]
                    if picked_size:
                        st.caption(f"Size: {picked_size}")
                else:
                    picked_size = st.radio(
                        "Size", size_options, horizontal=True,
                        key=f"wso_add_size_v{v_item}",
                    )
                item_row = subset[subset["size"].fillna("") == picked_size].iloc[0]
                unit = str(item_row["unit"])
                available_now = float(item_row["available"])

                staged_qty_for_item = sum(
                    float(l["quantity"]) for l in st.session_state.wso_cart
                    if l["item_name"] == item_row["item_name"]
                )
                effective_available = available_now - staged_qty_for_item

                st.info(
                    f"**Available:** {_fmt_qty(effective_available)} {unit}  "
                    f"(on-hand {_fmt_qty(available_now)}, staged {_fmt_qty(staged_qty_for_item)})"
                )

                _raw_url = item_row.get("image_url") if "image_url" in item_row else None
                _photo_url = None
                if _raw_url:
                    _photo_url = _raw_url
                    if "/file/d/" in _raw_url:
                        try:
                            _fid = _raw_url.split("/file/d/")[1].split("/")[0]
                            _photo_url = f"https://lh3.googleusercontent.com/d/{_fid}"
                        except Exception:
                            pass

                _total_cost = float(item_row.get("total_cost_php") or 0)
                _sell_price = float(item_row.get("selling_price_php") or 0)

                _c_photo, _c_info = st.columns([1, 3])
                with _c_photo:
                    if _photo_url:
                        try:
                            st.image(_photo_url, width=140)
                        except Exception:
                            st.caption("(image unavailable)")
                    else:
                        st.caption("No photo on file.")
                with _c_info:
                    st.caption("Confirm this is the correct item before adding to the requisition.")
                    _p1, _p2 = st.columns(2)
                    _p1.metric("Unit Cost (PHP)", f"{_total_cost:,.2f}")
                    _p2.metric("Selling Price (PHP)", f"{_sell_price:,.2f}")

                v_add = st.session_state.get("wso_add_version", 0)
                c1, c2 = st.columns([1, 2])
                with c1:
                    qty_text = st.text_input(
                        f"Quantity ({unit})*",
                        placeholder="Enter quantity...",
                        key=f"wso_add_qty_v{v_add}",
                    )
                with c2:
                    notes_text = st.text_input(
                        "Item Notes (optional)",
                        placeholder="e.g., deliver to Purok 4",
                        key=f"wso_add_notes_v{v_add}",
                    )

                qty_val = None
                qty_err = None
                if qty_text.strip():
                    try:
                        qty_val = float(qty_text.strip())
                        if qty_val <= 0:
                            qty_err = "Quantity must be greater than zero."
                    except ValueError:
                        qty_err = "Quantity must be a number."

                if qty_err:
                    st.error(qty_err)
                elif qty_val is not None:
                    remaining_after = effective_available - qty_val
                    if remaining_after < 0:
                        st.error(
                            f"Not enough stock. Requested {_fmt_qty(qty_val)} {unit}, "
                            f"but only {_fmt_qty(effective_available)} {unit} is available."
                        )
                    else:
                        st.caption(f"Remaining after this addition: {_fmt_qty(remaining_after)} {unit}")

                can_add = (
                    qty_val is not None and qty_err is None and qty_val > 0
                    and effective_available - qty_val >= 0 and header_ok
                )

                if st.button(
                    "Add Item to Requisition", width="stretch",
                    type="primary", disabled=not can_add,
                ):
                    st.session_state.wso_cart.append({
                        "item_name": selected_raw,
                        "unit": unit,
                        "quantity": float(qty_val),
                        "notes": (notes_text or "").strip(),
                    })
                    _bump_add_versions()
                    st.toast(f"Added {selected_raw} to requisition")
                    st.rerun()

                if not header_ok:
                    st.caption("Fill in **Requested By**, **Destination**, and **Project** first.")

        if st.session_state.wso_cart:
            st.divider()
            st.markdown(f"### Staged Items ({len(st.session_state.wso_cart)})")
            st.caption(
                f"**Requested By:** {input_requested_by.strip() or '-'} | "
                f"**Destination:** {input_destination.strip() or '-'} | "
                f"**Project:** {input_project.strip() or '-'}"
            )

            cart_df = pd.DataFrame(st.session_state.wso_cart).rename(columns={
                "item_name": "Item", "unit": "Unit",
                "quantity": "Quantity", "notes": "Notes",
            })
            st.dataframe(
                cart_df, width="stretch", hide_index=True,
                column_config={"Quantity": st.column_config.NumberColumn(format="%.2f")},
            )

            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Clear Cart Only", width="stretch"):
                    _reset_cart()
                    st.rerun()
            with c2:
                if st.button("Reset Header + Cart", width="stretch"):
                    _reset_all()
                    st.rerun()

            st.divider()
            if st.button("Submit Requisition", type="primary", width="stretch"):
                if not header_ok:
                    st.error(
                        "Requisition header incomplete. Fill in Requested By, "
                        "Destination, and Project."
                    )
                else:
                    try:
                        with st.spinner("Issuing requisition..."):
                            result = issue_stock_batch(
                                requested_by=input_requested_by.strip(),
                                destination=input_destination.strip(),
                                project=input_project.strip(),
                                handled_by=user_name,
                                items=st.session_state.wso_cart,
                                transaction_date=input_tx_date,
                                warehouse=cfg.WAREHOUSE,
                            )
                        req_id = result.get("req_id", "?")
                        lines = result.get("line_count", 0)
                        total_qty = sum(float(l["quantity"]) for l in st.session_state.wso_cart)
                        _reset_cart()
                        _bump_add_versions()
                        st.session_state["ws_flash"] = "success"
                        st.toast(
                            f"Requisition {req_id} issued ({lines} line(s), "
                            f"{_fmt_qty(total_qty)} total units)."
                        )
                        st.rerun()
                    except ValueError as e:
                        st.error(f"{e}")
                    except NetworkError as e:
                        st.error(f"{e}")
                    except Exception as e:
                        print(f"[water submit requisition] Unexpected: {e}")
                        st.error("Unexpected error while issuing requisition.")

    with tab_history:
        st.subheader("Outgoing Water Stock Logs")
        try:
            res = (
                sb().table("transactions")
                .select("id, timestamp, created_at, item_name, quantity, unit, handled_by, notes, project_name")
                .eq("type", "OUT")
                .eq("warehouse", cfg.WAREHOUSE)
                .order("created_at", desc=True).order("timestamp", desc=True)
                .limit(100).execute()
            )
            history_df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error loading history: {e}")
            return

        if history_df.empty:
            st.info("No outgoing water stock transactions yet.")
            return

        st.dataframe(
            history_df.rename(columns={
                "id": "Log ID", "timestamp": "Transaction Date", "created_at": "Logged At",
                "item_name": "Item Name", "quantity": "Quantity Issued", "unit": "Unit",
                "handled_by": "Handled By", "project_name": "Project",
                "notes": "Requisition / Requested By / Purpose",
            }),
            width="stretch", hide_index=True,
            column_config={"Quantity Issued": st.column_config.NumberColumn(format="%.2f")},
        )