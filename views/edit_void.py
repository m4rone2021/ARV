import sqlite3
from datetime import datetime
import pandas as pd
import streamlit as st
from database import get_db, backup_db_to_gdrive


def render_edit_void(user_name: str, user_role: str):
    st.title("📝 Edit or Void Transactions")
    st.caption(
        "Correct entry errors or void erroneous transactions. Inventory stock will update automatically."
    )

    with get_db() as conn:
        # Fallback query if edit_status is missing
        try:
            df_tx = pd.read_sql_query(
                "SELECT * FROM transactions WHERE COALESCE(edit_status, 'ACTIVE') != 'VOIDED' ORDER BY id DESC LIMIT 50",
                conn,
            )
        except sqlite3.OperationalError:
            df_tx = pd.read_sql_query(
                "SELECT * FROM transactions ORDER BY id DESC LIMIT 50",
                conn,
            )

    if df_tx.empty:
        st.info("No active transactions available to edit or void.")
        return

    st.subheader("🔍 Select Transaction")

    # Format selectbox options
    tx_options = {}
    for _, row in df_tx.iterrows():
        label = f"ID #{row['id']} | {row.get('timestamp', 'N/A')} | {row['type']} | {row['item_name']} ({row['quantity']})"
        tx_options[label] = row["id"]

    selected_label = st.selectbox(
        "Choose transaction to modify:", list(tx_options.keys())
    )
    selected_tx_id = tx_options[selected_label]

    # Get details of selected transaction
    tx_detail = df_tx[df_tx["id"] == selected_tx_id].iloc[0]

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Transaction ID:** `{tx_detail['id']}`")
        st.markdown(f"**Type:** `{tx_detail['type']}`")
        st.markdown(f"**Item Name:** `{tx_detail['item_name']}`")
        st.markdown(f"**Current Quantity:** `{tx_detail['quantity']}`")
    with col2:
        logged_by = tx_detail.get("user_name") or tx_detail.get("handled_by") or "N/A"
        logged_role = tx_detail.get("user_role") or "N/A"
        st.markdown(f"**Logged By:** `{logged_by}` ({logged_role})")
        st.markdown(f"**Date/Time:** `{tx_detail.get('timestamp', 'N/A')}`")
        st.markdown(f"**Project Site:** `{tx_detail.get('project_name') or 'N/A'}`")
        st.markdown(f"**Remarks/Notes:** `{tx_detail.get('remarks') or tx_detail.get('notes') or 'N/A'}`")

    tab_edit, tab_void = st.tabs(["✏️ Edit Details / Quantity", "🚫 Void Transaction"])

    # TAB 1: EDIT TRANSACTION
    with tab_edit:
        st.subheader("Edit Transaction Record")
        with st.form("edit_tx_form"):
            new_qty = st.number_input(
                "New Quantity",
                value=float(tx_detail["quantity"]),
                min_value=0.01,
                step=1.0,
                format="%.2f",
            )
            existing_project = tx_detail.get("project_name") or ""
            existing_remarks = tx_detail.get("remarks") or tx_detail.get("notes") or ""

            new_project = st.text_input("Project Site", value=existing_project)
            new_remarks = st.text_area("Remarks / Reason for Edit", value=existing_remarks)

            submit_edit = st.form_submit_button("💾 Save Changes")

            if submit_edit:
                qty_diff = new_qty - float(tx_detail["quantity"])

                try:
                    with get_db() as conn:
                        cursor = conn.cursor()

                        if tx_detail["type"] == "OUT" and qty_diff > 0:
                            cursor.execute(
                                "SELECT current_stock FROM master_items WHERE item_name = ?",
                                (tx_detail["item_name"],),
                            )
                            row = cursor.fetchone()
                            avail_stock = row["current_stock"] if row else 0.0
                            if qty_diff > avail_stock:
                                st.error(
                                    f"Cannot increase OUT quantity by {qty_diff:.2f}. Only {avail_stock:.2f} available in stock."
                                )
                                st.stop()

                        # Adjust master stock balance
                        if tx_detail["type"] == "IN":
                            cursor.execute(
                                "UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?",
                                (qty_diff, tx_detail["item_name"]),
                            )
                        elif tx_detail["type"] == "OUT":
                            cursor.execute(
                                "UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?",
                                (qty_diff, tx_detail["item_name"]),
                            )

                        # Update transaction record
                        edit_msg = f"{new_remarks.strip()} (Edited by {user_name} on {datetime.now().strftime('%Y-%m-%d %H:%M')})"
                        cursor.execute(
                            """
                            UPDATE transactions 
                            SET quantity = ?, project_name = ?, remarks = ?, notes = ?, edit_status = 'EDITED'
                            WHERE id = ?
                        """,
                            (
                                new_qty,
                                new_project.strip(),
                                edit_msg,
                                edit_msg,
                                selected_tx_id,
                            ),
                        )

                        conn.commit()
                        backup_db_to_gdrive()
                        st.toast("✅ Transaction successfully updated!", icon="✏️")
                        st.success("Changes saved and backed up to Drive.")
                        st.rerun()

                except sqlite3.OperationalError as e:
                    st.error(f"Database operation failed: {e}")

    # TAB 2: VOID TRANSACTION
    with tab_void:
        st.subheader("Void Transaction Record")
        st.warning(
            "⚠️ Voiding a transaction reverses its impact on inventory balance and marks the entry as VOIDED."
        )

        void_reason = st.text_input(
            "Reason for Voiding",
            placeholder="e.g., Duplicate entry / Incorrect item selected",
        )

        if st.button("🔴 Confirm & Void Transaction"):
            if not void_reason.strip():
                st.error("Please provide a reason for voiding this transaction.")
            else:
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()

                        if tx_detail["type"] == "IN":
                            cursor.execute(
                                "SELECT current_stock FROM master_items WHERE item_name = ?",
                                (tx_detail["item_name"],),
                            )
                            row = cursor.fetchone()
                            avail_stock = row["current_stock"] if row else 0.0
                            if float(tx_detail["quantity"]) > avail_stock:
                                st.error(
                                    f"Cannot void IN transaction. Stock is already at {avail_stock:.2f}, but this transaction added {tx_detail['quantity']}."
                                )
                                st.stop()

                        # Reverse stock impact
                        if tx_detail["type"] == "IN":
                            cursor.execute(
                                "UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?",
                                (tx_detail["quantity"], tx_detail["item_name"]),
                            )
                        elif tx_detail["type"] == "OUT":
                            cursor.execute(
                                "UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?",
                                (tx_detail["quantity"], tx_detail["item_name"]),
                            )

                        # Mark record as VOIDED
                        void_msg = f"VOIDED: {void_reason.strip()} (By {user_name} on {datetime.now().strftime('%Y-%m-%d %H:%M')})"
                        cursor.execute(
                            """
                            UPDATE transactions 
                            SET edit_status = 'VOIDED', remarks = ?, notes = ?
                            WHERE id = ?
                        """,
                            (void_msg, void_msg, selected_tx_id),
                        )

                        conn.commit()
                        backup_db_to_gdrive()
                        st.toast("🚫 Transaction voided successfully!", icon="🗑️")
                        st.success("Transaction voided and stock balance reversed.")
                        st.rerun()

                except sqlite3.OperationalError as e:
                    st.error(f"Database operation failed: {e}")
