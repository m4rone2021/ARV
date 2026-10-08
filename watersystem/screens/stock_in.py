"""Water system Stock IN — batch receive, scoped to warehouse='watersystem'."""
import pandas as pd
from datetime import date

import streamlit as st

from database import NetworkError, receive_stock_batch, sb
from watersystem import config as cfg


PLACEHOLDER = "-- Select an item --"


def _fmt_qty(x):
    return f"{x:,.2f}".rstrip("0").rstrip(".") if x % 1 else f"{int(x):,}"


def _reset_cart():
    st.session_state.wsi_cart = []


def _reset_all():
    _reset_cart()
    for k in (
        "wsi_supplier_input", "wsi_dr_input", "wsi_notes_input", "wsi_tx_date_input",
        "wsi_add_item_version", "wsi_add_version",
    ):
        st.session_state.pop(k, None)


def _bump_add_versions():
    st.session_state["wsi_add_version"] = st.session_state.get("wsi_add_version", 0) + 1
    st.session_state["wsi_add_item_version"] = st.session_state.get("wsi_add_item_version", 0) + 1


def render(user_name: str, is_admin: bool):
    st.title("📥 Water System — Stock IN")
    st.caption("Record water system material receipts, deliveries, and stock replenishment.")

    if "wsi_cart" not in st.session_state:
        st.session_state.wsi_cart = []

    flash = st.session_state.pop("ws_flash", None)
    if flash == "success":
        st.success("Operation completed.")

    tab_receive, tab_history = st.tabs(["Receive Stock", "Recent Stock IN History"])

    with tab_receive:
        st.subheader("New Stock Receipt")

        try:
            res = (
                sb().table("master_items")
                .select("item_name, category, unit, current_stock")
                .eq("warehouse", cfg.WAREHOUSE)
                .order("item_name").execute()
            )
            items_df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error loading water items: {e}")
            return

        if items_df.empty:
            st.info("No water items found. Add items first before receiving stock.")
            return

        items_df["current_stock"] = items_df["current_stock"].fillna(0)

        with st.container(border=True):
            st.markdown("##### Receipt Details")
            c1, c2 = st.columns(2)
            with c1:
                input_supplier = st.text_input(
                    "Supplier / Source / DR No.*",
                    placeholder="e.g., ABC Hardware",
                    key="wsi_supplier_input",
                )
            with c2:
                input_dr = st.text_input(
                    "DR Number (optional)",
                    placeholder="e.g., DR-12345",
                    key="wsi_dr_input",
                )
            input_notes = st.text_input(
                "General Notes (optional)",
                placeholder="e.g., delivered to warehouse bay A3",
                key="wsi_notes_input",
            )
            input_tx_date = st.date_input(
                "Transaction Date*",
                value=date.today(),
                key="wsi_tx_date_input",
                help="Date the transaction actually occurred. Backdating is allowed.",
            )
            st.caption("Receipt IDs will be generated per supplier.")

        header_ok = bool(input_supplier.strip())
        st.divider()

        with st.container(border=True):
            st.markdown("##### Add Item to Receipt")
            v_item = st.session_state.get("wsi_add_item_version", 0)
            item_options = [PLACEHOLDER] + items_df["item_name"].tolist()
            selected_raw = st.selectbox(
                "Select Item*", item_options, key=f"wsi_add_item_v{v_item}",
            )
            has_item = selected_raw != PLACEHOLDER

            if not has_item:
                st.info("Pick an item from the list to continue.")
            else:
                item_row = items_df[items_df["item_name"] == selected_raw].iloc[0]
                unit = str(item_row["unit"])
                current_on_hand = float(item_row["current_stock"])
                st.info(f"**Current on-hand:** {_fmt_qty(current_on_hand)} {unit}")

                v_add = st.session_state.get("wsi_add_version", 0)
                c1, c2 = st.columns([1, 2])
                with c1:
                    qty_text = st.text_input(
                        f"Quantity received ({unit})*",
                        placeholder="Enter quantity...",
                        key=f"wsi_add_qty_v{v_add}",
                    )
                with c2:
                    notes_text = st.text_input(
                        "Line Notes (optional)",
                        placeholder="e.g., batch A, storage bay 3",
                        key=f"wsi_add_notes_v{v_add}",
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
                    new_total = current_on_hand + qty_val
                    st.caption(f"New on-hand after receipt: {_fmt_qty(new_total)} {unit}")

                can_add = (
                    qty_val is not None and qty_err is None and qty_val > 0 and header_ok
                )

                if st.button(
                    "Add Item to Receipt", width="stretch",
                    type="primary", disabled=not can_add,
                ):
                    st.session_state.wsi_cart.append({
                        "item_name": selected_raw,
                        "unit": unit,
                        "quantity": float(qty_val),
                        "notes": (notes_text or "").strip(),
                    })
                    _bump_add_versions()
                    st.toast(f"Added {selected_raw} to receipt")
                    st.rerun()

                if not header_ok:
                    st.caption("Fill in **Supplier / Source** in the header before adding items.")

        if st.session_state.wsi_cart:
            st.divider()
            st.markdown(f"### Staged Receipt ({len(st.session_state.wsi_cart)})")
            st.caption(
                f"**Supplier:** {input_supplier.strip() or '-'} | "
                f"**DR No.:** {input_dr.strip() or '-'}"
            )

            cart_df = pd.DataFrame(st.session_state.wsi_cart).rename(columns={
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
                if st.button("Clear Receipt Only", width="stretch"):
                    _reset_cart()
                    st.rerun()
            with c2:
                if st.button("Reset Header + Receipt", width="stretch"):
                    _reset_all()
                    st.rerun()

            st.divider()
            if st.button("Submit Receipt", type="primary", width="stretch"):
                if not header_ok:
                    st.error("Supplier / Source is required.")
                else:
                    try:
                        with st.spinner("Recording receipt..."):
                            result = receive_stock_batch(
                                supplier=input_supplier.strip(),
                                dr_number=input_dr.strip(),
                                handled_by=user_name,
                                general_notes=input_notes.strip(),
                                items=st.session_state.wsi_cart,
                                transaction_date=input_tx_date,
                                warehouse=cfg.WAREHOUSE,
                            )
                        rcv_id = result.get("rcv_id", "?")
                        lines = result.get("line_count", 0)
                        total_qty = sum(float(l["quantity"]) for l in st.session_state.wsi_cart)
                        _reset_cart()
                        _bump_add_versions()
                        st.session_state["ws_flash"] = "success"
                        st.toast(
                            f"Receipt {rcv_id} recorded ({lines} line(s), "
                            f"{_fmt_qty(total_qty)} total units)."
                        )
                        st.rerun()
                    except ValueError as e:
                        st.error(f"{e}")
                    except NetworkError as e:
                        st.error(f"{e}")
                    except Exception as e:
                        print(f"[water submit receipt] Unexpected: {e}")
                        st.error("Unexpected error while recording receipt.")

    with tab_history:
        st.subheader("Recent Water Stock IN Entries")
        try:
            res = (
                sb().table("transactions")
                .select("id, timestamp, created_at, item_name, quantity, unit, handled_by, notes")
                .eq("type", "IN")
                .eq("warehouse", cfg.WAREHOUSE)
                .order("created_at", desc=True).order("timestamp", desc=True)
                .limit(50).execute()
            )
            history_df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error loading history: {e}")
            return

        if history_df.empty:
            st.info("No recent water Stock IN transactions yet.")
            return

        st.dataframe(
            history_df.rename(columns={
                "id": "ID", "timestamp": "Transaction Date", "created_at": "Logged At",
                "item_name": "Item Name", "quantity": "Quantity", "unit": "Unit",
                "handled_by": "Received By", "notes": "Receipt / Supplier / Notes",
            }),
            width="stretch", hide_index=True,
            column_config={"Quantity": st.column_config.NumberColumn(format="%.2f")},
        )