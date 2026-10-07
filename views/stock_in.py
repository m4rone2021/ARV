import pandas as pd
from datetime import date
import streamlit as st

from database import (
    NetworkError,
    receive_stock_batch,
    sb,
)


PLACEHOLDER = "-- Select an item --"


def _fmt_qty(x):
    return f"{x:,.2f}".rstrip("0").rstrip(".") if x % 1 else f"{int(x):,}"


def _reset_cart():
    st.session_state.si_cart = []


def _reset_all():
    _reset_cart()
    for k in (
        "si_supplier_input", "si_dr_input", "si_notes_input", "si_tx_date_input",
        "si_add_item_version", "si_add_version",
    ):
        st.session_state.pop(k, None)


def _bump_add_versions():
    st.session_state["si_add_version"] = st.session_state.get("si_add_version", 0) + 1
    st.session_state["si_add_item_version"] = st.session_state.get("si_add_item_version", 0) + 1


def render_stock_in(user_name, user_role):
    st.title("Stock IN Receive Log")
    st.caption(
        "Record site material receipts, deliveries, and stock replenishment."
    )

    if "si_cart" not in st.session_state:
        st.session_state.si_cart = []

    flash = st.session_state.pop("flash_msg", None)
    if flash and isinstance(flash, tuple) and len(flash) == 2:
        msg_type, msg_text = flash
        if msg_type == "success":
            st.success(msg_text)
        elif msg_type == "warning":
            st.warning(msg_text)

    tab_receive, tab_history = st.tabs(
        ["Receive Stock", "Recent Stock IN History"]
    )

    with tab_receive:
        st.subheader("New Stock Receipt")

        try:
            res = (
                sb()
                .table("master_items")
                .select("item_name, category, unit, current_stock")
                .order("item_name")
                .execute()
            )
            items_df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error loading items catalog: {e}")
            return

        if items_df.empty:
            st.info("No items found. Add items first before receiving stock.")
            return

        items_df["current_stock"] = items_df["current_stock"].fillna(0)

        with st.container(border=True):
            st.markdown("##### Receipt Details")
            c1, c2 = st.columns(2)
            with c1:
                input_supplier = st.text_input(
                    "Supplier / Source / DR No.*",
                    placeholder="e.g., ABC Hardware",
                    key="si_supplier_input",
                )
            with c2:
                input_dr = st.text_input(
                    "DR Number (optional)",
                    placeholder="e.g., DR-12345",
                    key="si_dr_input",
                )
            input_notes = st.text_input(
                "General Notes (optional)",
                placeholder="e.g., delivered to warehouse bay A3",
                key="si_notes_input",
            )
            input_tx_date = st.date_input(
                "Transaction Date*",
                value=date.today(),
                key="si_tx_date_input",
                help="Date the transaction actually occurred. Backdating is allowed.",
            )
            st.caption(
                "Receipt IDs will be generated per supplier, "
                "e.g. ABC-HARDWARE-RCV-0001"
            )

        header_ok = bool(input_supplier.strip())

        st.divider()

        with st.container(border=True):
            st.markdown("##### Add Item to Receipt")

            v_item = st.session_state.get("si_add_item_version", 0)
            item_options = [PLACEHOLDER] + items_df["item_name"].tolist()
            selected_raw = st.selectbox(
                "Select Item*",
                item_options,
                key=f"si_add_item_v{v_item}",
            )

            has_item = selected_raw != PLACEHOLDER

            if not has_item:
                st.info("Pick an item from the list to continue.")
                if not header_ok:
                    st.caption(
                        "Fill in **Supplier / Source** in the header before adding items."
                    )
            else:
                item_row = items_df[items_df["item_name"] == selected_raw].iloc[0]
                unit = str(item_row["unit"])
                current_on_hand = float(item_row["current_stock"])

                st.info(
                    f"**Current on-hand:** {_fmt_qty(current_on_hand)} {unit}"
                )

                v_add = st.session_state.get("si_add_version", 0)
                c1, c2 = st.columns([1, 2])
                with c1:
                    qty_text = st.text_input(
                        f"Quantity received ({unit})*",
                        placeholder="Enter quantity...",
                        key=f"si_add_qty_v{v_add}",
                    )
                with c2:
                    notes_text = st.text_input(
                        "Line Notes (optional)",
                        placeholder="e.g., batch A, storage bay 3",
                        key=f"si_add_notes_v{v_add}",
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
                elif qty_val is None:
                    st.caption("Enter a quantity to continue.")
                else:
                    new_total = current_on_hand + qty_val
                    st.caption(
                        f"New on-hand after receipt: {_fmt_qty(new_total)} {unit}"
                    )

                can_add = (
                    qty_val is not None
                    and qty_err is None
                    and qty_val > 0
                    and header_ok
                )

                if st.button(
                    "Add Item to Receipt",
                    width='stretch',
                    type="primary",
                    disabled=not can_add,
                ):
                    st.session_state.si_cart.append({
                        "item_name": selected_raw,
                        "unit": unit,
                        "quantity": float(qty_val),
                        "notes": (notes_text or "").strip(),
                    })
                    _bump_add_versions()
                    st.toast(f"Added {selected_raw} to receipt")
                    st.rerun()

                if not header_ok:
                    st.caption(
                        "Fill in **Supplier / Source** in the header before adding items."
                    )

        if st.session_state.si_cart:
            st.divider()
            st.markdown(f"### Staged Receipt ({len(st.session_state.si_cart)})")

            st.caption(
                f"**Supplier:** {input_supplier.strip() or chr(45)} | "
                f"**DR No.:** {input_dr.strip() or chr(45)}"
            )

            st.markdown("##### Line Items")
            cart_df = pd.DataFrame(st.session_state.si_cart).rename(columns={
                "item_name": "Item",
                "unit": "Unit",
                "quantity": "Quantity",
                "notes": "Notes",
            })
            st.dataframe(
                cart_df,
                width='stretch',
                hide_index=True,
                column_config={
                    "Quantity": st.column_config.NumberColumn(format="%.2f"),
                },
            )

            st.markdown("##### Summary by Item")
            summary = {}
            for line in st.session_state.si_cart:
                key = (line["item_name"], line["unit"])
                if key not in summary:
                    summary[key] = {"total": 0.0, "lines": 0, "notes": []}
                summary[key]["total"] += float(line["quantity"])
                summary[key]["lines"] += 1
                if line["notes"]:
                    summary[key]["notes"].append(line["notes"])

            summary_rows = [
                {
                    "Item": name,
                    "Total Quantity": data["total"],
                    "Unit": unit_,
                    "Lines": data["lines"],
                    "Combined Notes": "; ".join(data["notes"]),
                }
                for (name, unit_), data in summary.items()
            ]
            st.dataframe(
                pd.DataFrame(summary_rows),
                width='stretch',
                hide_index=True,
                column_config={
                    "Total Quantity": st.column_config.NumberColumn(format="%.2f"),
                },
            )

            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Clear Receipt Only", width='stretch'):
                    _reset_cart()
                    st.rerun()
            with c2:
                if st.button("Reset Header + Receipt", width='stretch'):
                    _reset_all()
                    st.rerun()

            st.divider()
            if st.button(
                "Submit Receipt",
                type="primary",
                width='stretch',
            ):
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
                                items=st.session_state.si_cart,
                                transaction_date=input_tx_date,
                            )

                        rcv_id = result.get("rcv_id", "?")
                        lines = result.get("line_count", 0)
                        total_qty = sum(
                            float(l["quantity"]) for l in st.session_state.si_cart
                        )

                        _reset_cart()
                        _bump_add_versions()

                        st.session_state.flash_msg = (
                            "success",
                            f"Receipt {rcv_id} recorded successfully "
                            f"({lines} line(s), "
                            f"{_fmt_qty(total_qty)} total units). "
                            f"Header retained for next receipt.",
                        )
                        st.rerun()
                    except ValueError as e:
                        st.error(f"{e}")
                    except NetworkError as e:
                        st.error(f"{e}")
                    except Exception as e:
                        print(f"[submit receipt] Unexpected: {e}")
                        st.error(
                            "Unexpected error while recording receipt. "
                            "Please try again or contact an administrator."
                        )

    with tab_history:
        st.subheader("Recent Stock IN Entries")

        try:
            res = (
                sb()
                .table("transactions")
                .select("id, timestamp, item_name, quantity, unit, handled_by, notes")
                .eq("type", "IN")
                .order("timestamp", desc=True)
                .limit(50)
                .execute()
            )
            history_df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error loading Stock IN history: {e}")
            return

        if history_df.empty:
            st.info("No recent Stock IN transactions recorded yet.")
            return

        st.dataframe(
            history_df.rename(columns={
                "id": "ID",
                "timestamp": "Timestamp",
                "item_name": "Item Name",
                "quantity": "Quantity",
                "unit": "Unit",
                "handled_by": "Received By",
                "notes": "Receipt / Supplier / Notes",
            }),
            width='stretch',
            hide_index=True,
            column_config={
                "Quantity": st.column_config.NumberColumn(format="%.2f"),
            },
        )
