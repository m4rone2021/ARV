from datetime import datetime

import pandas as pd
import streamlit as st

from database import sb


def _adjust_stock(item_name: str, delta: float):
    """Add `delta` to master_items.current_stock. Delta can be negative."""
    cur = (
        sb()
        .table("master_items")
        .select("current_stock")
        .eq("item_name", item_name)
        .limit(1)
        .execute()
    )
    if not cur.data:
        return
    current = float(cur.data[0].get("current_stock") or 0.0)
    new_stock = max(0.0, current + delta)
    sb().table("master_items").update(
        {"current_stock": new_stock}
    ).eq("item_name", item_name).execute()


def render_edit_void(user_name: str, user_role: str):
    st.title("📝 Edit / Void Transactions")
    st.caption(
        "Correct entry errors or void transactions with automatic inventory updates."
    )

    # ---- 1. Fetch active transactions ----
    try:
        res = (
            sb()
            .table("transactions")
            .select("id, timestamp, type, item_name, quantity, unit, handled_by, "
                    "notes, project_name, edit_status")
            .eq("edit_status", "ACTIVE")
            .order("timestamp", desc=True)
            .limit(50)
            .execute()
        )
        df_tx = pd.DataFrame(res.data or [])
    except Exception as e:
        st.error(f"Error loading transactions: {e}")
        return

    if df_tx.empty:
        st.info("No active transactions available to edit or void.")
        return

    # ---- 2. Select transaction ----
    st.subheader("🔍 Select Record")

    tx_options = {}
    for _, row in df_tx.iterrows():
        label = (
            f"#{str(row['id'])[:8]} | {row['type']} | {row['item_name']} "
            f"({row['quantity']} {row['unit']})"
        )
        tx_options[label] = row["id"]

    selected_label = st.selectbox(
        "Choose transaction to modify:",
        list(tx_options.keys()),
        help="Select a record by ID and item name",
    )
    selected_tx_id = tx_options[selected_label]
    tx_detail = df_tx[df_tx["id"] == selected_tx_id].iloc[0]

    # ---- 3. Details summary ----
    with st.container(border=True):
        m1, m2 = st.columns(2)
        m1.metric("Transaction ID", f"#{str(tx_detail['id'])[:8]}")
        m2.metric("Type", str(tx_detail["type"]))

        st.markdown(f"**Item:** `{tx_detail['item_name']}`")
        st.markdown(f"**Current Quantity:** `{tx_detail['quantity']} {tx_detail['unit']}`")

        with st.expander("📄 View Extended Details"):
            st.markdown(f"* **Handled By:** {tx_detail.get('handled_by', 'N/A')}")
            st.markdown(f"* **Date/Time:** {tx_detail.get('timestamp', 'N/A')}")
            st.markdown(f"* **Project Site:** {tx_detail.get('project_name') or 'N/A'}")
            st.markdown(f"* **Notes:** {tx_detail.get('notes') or 'N/A'}")

    st.divider()

    tab_edit, tab_void = st.tabs(["✏️ Edit Record", "🚫 Void Record"])

    # ================================================================
    # TAB 1: EDIT
    # ================================================================
    with tab_edit:
        st.subheader("Edit Transaction")
        with st.form("edit_tx_form", clear_on_submit=False):
            new_qty = st.number_input(
                "New Quantity",
                value=float(tx_detail["quantity"]),
                min_value=0.01,
                step=1.0,
                format="%.2f",
            )
            existing_project = tx_detail.get("project_name") or ""
            existing_notes = tx_detail.get("notes") or ""

            new_project = st.text_input("Project Site", value=existing_project)
            new_remarks = st.text_area("Remarks / Reason for Edit", value=existing_notes, height=100)

            submit_edit = st.form_submit_button("💾 Save Changes", use_container_width=True)

            if submit_edit:
                old_qty = float(tx_detail["quantity"])
                qty_diff = new_qty - old_qty  # positive = more of what happened originally

                try:
                    tx_type = tx_detail["type"]
                    item_name = tx_detail["item_name"]

                    # Adjust stock based on diff and type
                    # IN increases stock: +diff changes stock by +diff
                    # OUT decreases stock: -diff changes stock by -diff
                    # ADJUSTMENT: replaced by new_qty directly
                    if tx_type == "IN":
                        _adjust_stock(item_name, qty_diff)
                    elif tx_type == "OUT":
                        if qty_diff > 0:
                            # Need to check available stock
                            cur = (
                                sb()
                                .table("master_items")
                                .select("current_stock")
                                .eq("item_name", item_name)
                                .limit(1)
                                .execute()
                            )
                            avail = float(cur.data[0]["current_stock"]) if cur.data else 0.0
                            if qty_diff > avail:
                                st.error(
                                    f"Cannot increase OUT quantity by {qty_diff:.2f}. "
                                    f"Only {avail:.2f} available in stock."
                                )
                                st.stop()
                        _adjust_stock(item_name, -qty_diff)
                    elif tx_type == "ADJUSTMENT":
                        # ADJUSTMENT means "set stock to this value" — so re-set
                        sb().table("master_items").update(
                            {"current_stock": float(new_qty)}
                        ).eq("item_name", item_name).execute()

                    # Update the transaction record
                    edit_msg = (
                        f"{new_remarks.strip()} "
                        f"(Edited by {user_name} on {datetime.now().strftime('%Y-%m-%d %H:%M')})"
                    )
                    sb().table("transactions").update({
                        "quantity": float(new_qty),
                        "project_name": new_project.strip() or None,
                        "notes": edit_msg,
                        "edit_status": "EDITED",
                        "edited_by": user_name,
                        "edited_at": datetime.utcnow().isoformat(),
                    }).eq("id", selected_tx_id).execute()

                    st.toast("✅ Transaction updated!", icon="✏️")
                    st.success("Changes saved.")
                    st.rerun()

                except Exception as e:
                    st.error(f"Update failed: {e}")

    # ================================================================
    # TAB 2: VOID
    # ================================================================
    with tab_void:
        st.subheader("Void Transaction")
        st.warning("⚠️ Voiding reverses the stock balance and marks entry as VOIDED.")

        void_reason = st.text_input(
            "Reason for Voiding",
            placeholder="e.g., Duplicate entry",
        )

        if st.button("🔴 Confirm & Void Transaction", use_container_width=True):
            if not void_reason.strip():
                st.error("Please provide a reason for voiding this transaction.")
            else:
                try:
                    tx_type = tx_detail["type"]
                    item_name = tx_detail["item_name"]
                    qty = float(tx_detail["quantity"])

                    # Reverse stock impact
                    if tx_type == "IN":
                        # IN added stock — check we have enough to remove
                        cur = (
                            sb()
                            .table("master_items")
                            .select("current_stock")
                            .eq("item_name", item_name)
                            .limit(1)
                            .execute()
                        )
                        avail = float(cur.data[0]["current_stock"]) if cur.data else 0.0
                        if qty > avail:
                            st.error(
                                f"Cannot void IN transaction. Stock is at {avail:.2f} "
                                f"but this transaction added {qty}."
                            )
                            st.stop()
                        _adjust_stock(item_name, -qty)
                    elif tx_type == "OUT":
                        # OUT removed stock — add it back
                        _adjust_stock(item_name, qty)
                    # ADJUSTMENT: no reliable reversal — leave stock alone, just mark VOIDED

                    # Mark record
                    void_msg = (
                        f"VOIDED: {void_reason.strip()} "
                        f"(By {user_name} on {datetime.now().strftime('%Y-%m-%d %H:%M')})"
                    )
                    sb().table("transactions").update({
                        "edit_status": "VOIDED",
                        "notes": void_msg,
                        "void_reason": void_reason.strip(),
                        "edited_by": user_name,
                        "edited_at": datetime.utcnow().isoformat(),
                    }).eq("id", selected_tx_id).execute()

                    st.toast("🚫 Transaction voided successfully!", icon="🗑️")
                    st.success("Transaction voided and stock balance reversed.")
                    st.rerun()

                except Exception as e:
                    st.error(f"Void failed: {e}")
