# views/edit_void.py
import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime
from database import get_db

def render_edit_void(user_name, user_role):
    st.title("📝 Edit or Void Transactions")
    st.caption("Correct entry errors or void erroneous transactions. Inventory stock will update automatically.")

    with get_db() as conn:
        df_tx = pd.read_sql_query(
            "SELECT * FROM transactions WHERE edit_status != 'VOIDED' ORDER BY id DESC LIMIT 50", 
            conn
        )

    if df_tx.empty:
        st.info("No active transactions available to edit or void.")
        return

    st.subheader("🔍 Select Transaction")
    
    # Format selectbox options for quick identification
    tx_options = {}
    for _, row in df_tx.iterrows():
        label = f"ID #{row['id']} | {row['timestamp']} | {row['type']} | {row['item_name']} ({row['quantity']})"
        tx_options[label] = row['id']

    selected_label = st.selectbox("Choose transaction to modify:", list(tx_options.keys()))
    selected_tx_id = tx_options[selected_label]

    # Get details of selected transaction
    tx_detail = df_tx[df_tx['id'] == selected_tx_id].iloc[0]

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Transaction ID:** `{tx_detail['id']}`")
        st.markdown(f"**Type:** `{tx_detail['type']}`")
        st.markdown(f"**Item Name:** `{tx_detail['item_name']}`")
        st.markdown(f"**Current Quantity:** `{tx_detail['quantity']}`")
    with col2:
        st.markdown(f"**Logged By:** `{tx_detail['user_name']}` ({tx_detail['user_role']})")
        st.markdown(f"**Date/Time:** `{tx_detail['timestamp']}`")
        st.markdown(f"**Project Site:** `{tx_detail['project_name'] or 'N/A'}`")
        st.markdown(f"**Remarks:** `{tx_detail['remarks'] or 'N/A'}`")

    tab_edit, tab_void = st.tabs(["✏️ Edit Details / Quantity", "🚫 Void Transaction"])

    # TAB 1: EDIT TRANSACTION
    with tab_edit:
        st.subheader("Edit Transaction Record")
        with st.form("edit_tx_form"):
            new_qty = st.number_input(
                "New Quantity", 
                value=float(tx_detail['quantity']), 
                min_value=0.01, 
                step=1.0, 
                format="%.2f"
            )
            new_project = st.text_input("Project Site", value=tx_detail['project_name'] or "")
            new_remarks = st.text_area("Remarks / Reason for Edit", value=tx_detail['remarks'] or "")

            submit_edit = st.form_submit_button("💾 Save Changes")

            if submit_edit:
                qty_diff = new_qty - float(tx_detail['quantity'])

                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("BEGIN IMMEDIATE")

                        # If Stock IN, adding qty increases stock; decreasing qty reduces stock
                        # If Stock OUT, adding qty reduces stock; decreasing qty adds stock back
                        if tx_detail['type'] == 'IN':
                            cursor.execute(
                                "UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?", 
                                (qty_diff, tx_detail['item_name'])
                            )
                        elif tx_detail['type'] == 'OUT':
                            cursor.execute(
                                "UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", 
                                (qty_diff, tx_detail['item_name'])
                            )

                        # Update transaction log
                        edit_msg = f"{new_remarks} (Edited by {user_name} on {datetime.now().strftime('%Y-%m-%d %H:%M')})"
                        cursor.execute("""
                            UPDATE transactions 
                            SET quantity = ?, project_name = ?, remarks = ?, edit_status = 'EDITED'
                            WHERE id = ?
                        """, (new_qty, new_project.strip(), edit_msg, selected_tx_id))

                        conn.commit()
                        st.toast("✅ Transaction successfully updated!", icon="✏️")
                        st.success("Changes saved successfully.")
                        st.rerun()
                except sqlite3.OperationalError:
                    st.error("Database is currently busy. Please try again.")

    # TAB 2: VOID TRANSACTION
    with tab_void:
        st.subheader("Void Transaction Record")
        st.warning("⚠️ Voiding a transaction reverses its impact on inventory balance and marks the entry as VOIDED.")

        void_reason = st.text_input("Reason for Voiding", placeholder="e.g., Duplicate entry / Incorrect item selected")

        if st.button("🔴 Confirm & Void Transaction"):
            if not void_reason.strip():
                st.error("Please provide a reason for voiding this transaction.")
            else:
                try:
                    with get_db() as conn:
                        cursor = conn.cursor()
                        cursor.execute("BEGIN IMMEDIATE")

                        # Reverse stock impact
                        if tx_detail['type'] == 'IN':
                            cursor.execute(
                                "UPDATE master_items SET current_stock = current_stock - ? WHERE item_name = ?", 
                                (tx_detail['quantity'], tx_detail['item_name'])
                            )
                        elif tx_detail['type'] == 'OUT':
                            cursor.execute(
                                "UPDATE master_items SET current_stock = current_stock + ? WHERE item_name = ?", 
                                (tx_detail['quantity'], tx_detail['item_name'])
                            )

                        # Mark as VOIDED
                        void_msg = f"VOIDED: {void_reason.strip()} (By {user_name} on {datetime.now().strftime('%Y-%m-%d %H:%M')})"
                        cursor.execute("""
                            UPDATE transactions 
                            SET edit_status = 'VOIDED', remarks = ? 
                            WHERE id = ?
                        """, (void_msg, selected_tx_id))

                        conn.commit()
                        st.toast("🚫 Transaction voided successfully!", icon="🗑️")
                        st.success("Transaction voided and stock balance reversed.")
                        st.rerun()
                except sqlite3.OperationalError:
                    st.error("Database is currently busy. Please try again.")
