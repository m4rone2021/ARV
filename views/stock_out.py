# views/stock_out.py
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db, init_db

def render_stock_out(user_name, user_role):
    st.title("📤 Stock Out Workflow")
    st.caption("Record outgoing materials, validate real-time stock balances, and track stock dispatches.")

    init_db()

    tab_record, tab_history = st.tabs([
        "📤 Issue Stock / Material Requisition", 
        "📜 Outgoing Stock History"
    ])

    # -------------------------------------------------------------
    # TAB 1: ISSUE STOCK (Stock Out Entry)
    # -------------------------------------------------------------
    with tab_record:
        st.subheader("Record Outgoing Material")

        try:
            with get_db() as conn:
                items_df = pd.read_sql_query(
                    "SELECT id, item_name, category, unit, current_stock, min_threshold FROM master_items ORDER BY item_name ASC", 
                    conn
                )

            if not items_df.empty:
                with st.form("stock_out_form"):
                    selected_item_name = st.selectbox("Select Item to Issue*", items_df["item_name"].tolist())
                    
                    # Fetch selected item's current stock details
                    item_row = items_df[items_df["item_name"] == selected_item_name].iloc[0]
                    current_available = float(item_row["current_stock"])
                    unit = item_row["unit"]
                    min_thresh = float(item_row["min_threshold"])

                    # Stock indicator metrics
                    st.divider()
                    col_info1, col_info2, col_info3 = st.columns(3)
                    col_info1.metric("Current Available Stock", f"{current_available:,.2f} {unit}")
                    col_info2.metric("Category", item_row["category"])
                    col_info3.metric("Minimum Threshold Alert", f"{min_thresh:,.2f} {unit}")

                    if current_available <= 0:
                        st.error(f"⚠️ **{selected_item_name}** is currently OUT OF STOCK. Stock Out is disabled.")

                    st.divider()

                    col_q, col_d = st.columns(2)
                    with col_q:
                        quantity_out = st.number_input(
                            f"Quantity to Issue ({unit})*", 
                            min_value=0.01, 
                            value=1.0, 
                            step=1.0
                        )
                    with col_d:
                        recipient = st.text_input("Issued To / Department / Project*", placeholder="e.g., Site Phase 2 / John Doe")

                    notes = st.text_input("Purpose / Requisition Details", placeholder="e.g., Formwork preparation, Maintenance release")

                    submit_btn = st.form_submit_button("📤 Submit Stock Out", use_container_width=True)

                    if submit_btn:
                        if current_available <= 0:
                            st.error(f"❌ Cannot process Stock Out: **{selected_item_name}** is out of stock.")
                        elif quantity_out > current_available:
                            st.error(f"❌ **Insufficient Stock!** Requested: {quantity_out:,.2f} {unit} | Available: {current_available:,.2f} {unit}.")
                        elif not recipient.strip():
                            st.error("⚠️ Please specify the recipient, department, or project taking the materials.")
                        else:
                            try:
                                with get_db() as conn_trans:
                                    cursor = conn_trans.cursor()

                                    # 1. Update Master Stock
                                    new_stock = current_available - quantity_out
                                    cursor.execute(
                                        "UPDATE master_items SET current_stock = ? WHERE item_name = ?",
                                        (new_stock, selected_item_name)
                                    )

                                    # 2. Log in Transactions
                                    formatted_notes = f"Issued to: {recipient.strip()} | Notes: {notes.strip()}" if notes.strip() else f"Issued to: {recipient.strip()}"
                                    cursor.execute("""
                                        INSERT INTO transactions (type, item_name, quantity, unit, handled_by, notes)
                                        VALUES ('STOCK OUT', ?, ?, ?, ?, ?)
                                    """, (selected_item_name, quantity_out, unit, user_name, formatted_notes))

                                    conn_trans.commit()

                                    st.success(f"✅ Issued **{quantity_out:,.2f} {unit}** of **{selected_item_name}**. Remaining balance: **{new_stock:,.2f} {unit}**.")

                                    # Low Stock Warning
                                    if new_stock <= min_thresh:
                                        st.warning(f"🔔 **Low Stock Alert**: {selected_item_name} has dropped to or below its threshold ({min_thresh:,.2f} {unit}).")

                                    st.rerun()

                            except Exception as e:
                                st.error(f"Error executing Stock Out: {e}")

            else:
                st.info("No items found in Master Catalog. Add items first before issuing stock.")

        except Exception as e:
            st.error(f"Error loading items catalog: {e}")

    # -------------------------------------------------------------
    # TAB 2: OUTGOING STOCK HISTORY
    # -------------------------------------------------------------
    with tab_history:
        st.subheader("📜 Outgoing Stock Transaction Logs")

        try:
            with get_db() as conn:
                history_df = pd.read_sql_query("""
                    SELECT id, timestamp, item_name, quantity, unit, handled_by, notes 
                    FROM transactions 
                    WHERE type = 'STOCK OUT'
                    ORDER BY id DESC
                """, conn)

            if not history_df.empty:
                df_display = history_df.rename(columns={
                    "id": "Log ID",
                    "timestamp": "Date & Time",
                    "item_name": "Item Name",
                    "quantity": "Quantity Issued",
                    "unit": "Unit",
                    "handled_by": "Handled By",
                    "notes": "Recipient / Purpose"
                })
                st.dataframe(df_display, use_container_width=True, hide_index=True)
            else:
                st.info("No outgoing stock transactions recorded yet.")

        except Exception as e:
            st.error(f"Error loading Stock Out history: {e}")
