import pandas as pd
import streamlit as st
from database import get_db, init_db


def render_stock_out(user_name, user_role):
    st.title("📤 Stock Out Workflow")
    st.caption(
        "Record outgoing materials, validate real-time stock balances, and track stock dispatches."
    )

    init_db()

    # Flash notification handling from previous rerun
    if "flash_msg" in st.session_state:
        msg_type, msg_text = st.session_state.pop("flash_msg")
        if msg_type == "success":
            st.success(msg_text)
        elif msg_type == "warning":
            st.warning(msg_text)

    tab_record, tab_history = st.tabs(
        ["📤 Issue Stock / Material Requisition", "📜 Outgoing Stock History"]
    )

    # -------------------------------------------------------------
    # TAB 1: ISSUE STOCK (Stock Out Entry)
    # -------------------------------------------------------------
    with tab_record:
        st.subheader("Record Outgoing Material")

        try:
            with get_db() as conn:
                items_df = pd.read_sql_query(
                    """
                    SELECT id, item_name, category, unit, current_stock, min_threshold 
                    FROM master_items 
                    ORDER BY item_name ASC
                    """,
                    conn,
                )

            if not items_df.empty:
                selected_item_name = st.selectbox(
                    "Select Item to Issue*", 
                    items_df["item_name"].tolist(),
                    key="select_stock_out_item"
                )

                # Fetch selected item details
                item_row = items_df[items_df["item_name"] == selected_item_name].iloc[0]
                current_available = float(item_row["current_stock"])
                unit = str(item_row["unit"])
                min_thresh = float(item_row["min_threshold"])

                # Stock indicator metrics
                st.divider()
                col_info1, col_info2, col_info3 = st.columns(3)
                col_info1.metric("Current Available Stock", f"{current_available:,.2f} {unit}")
                col_info2.metric("Category", str(item_row["category"]))
                col_info3.metric("Minimum Threshold", f"{min_thresh:,.2f} {unit}")

                is_out_of_stock = current_available <= 0
                if is_out_of_stock:
                    st.error(f"⚠️ **{selected_item_name}** is OUT OF STOCK. Submissions are disabled.")

                st.divider()

                with st.form("stock_out_form", clear_on_submit=True):
                    col_q, col_d = st.columns(2)
                    with col_q:
                        quantity_out = st.number_input(
                            f"Quantity to Issue ({unit})*",
                            min_value=0.01,
                            value=1.00,
                            step=1.00,
                            format="%.2f",
                            disabled=is_out_of_stock
                        )
                    with col_d:
                        recipient = st.text_input(
                            "Issued To / Department / Project*",
                            placeholder="e.g., Site Phase 2 / John Doe",
                            disabled=is_out_of_stock
                        )

                    notes = st.text_input(
                        "Purpose / Requisition Details",
                        placeholder="e.g., Formwork preparation, Maintenance release",
                        disabled=is_out_of_stock
                    )

                    submit_btn = st.form_submit_button(
                        "📤 Submit Stock Out", 
                        use_container_width=True,
                        disabled=is_out_of_stock
                    )

                    if submit_btn:
                        clean_recipient = recipient.strip()
                        clean_notes = notes.strip()

                        if not clean_recipient:
                            st.error("⚠️ Please specify the recipient, department, or project.")
                        elif quantity_out <= 0:
                            st.error("⚠️ Quantity to issue must be greater than zero.")
                        else:
                            try:
                                with get_db() as conn_trans:
                                    cursor = conn_trans.cursor()

                                    # Atomic deduction check
                                    cursor.execute(
                                        """
                                        UPDATE master_items 
                                        SET current_stock = current_stock - ? 
                                        WHERE item_name = ? AND current_stock >= ?
                                        """,
                                        (quantity_out, selected_item_name, quantity_out),
                                    )

                                    if cursor.rowcount == 0:
                                        cursor.execute(
                                            "SELECT current_stock FROM master_items WHERE item_name = ?",
                                            (selected_item_name,),
                                        )
                                        live_stock_row = cursor.fetchone()
                                        live_stock = live_stock_row[0] if live_stock_row else 0.0

                                        st.error(
                                            f"❌ **Transaction Blocked! Insufficient Stock.** "
                                            f"Requested: {quantity_out:,.2f} {unit} | Live Available: {live_stock:,.2f} {unit}."
                                        )
                                    else:
                                        formatted_notes = (
                                            f"Issued to: {clean_recipient} | Notes: {clean_notes}"
                                            if clean_notes
                                            else f"Issued to: {clean_recipient}"
                                        )

                                        cursor.execute(
                                            """
                                            INSERT INTO transactions (type, item_name, quantity, unit, handled_by, notes)
                                            VALUES ('STOCK OUT', ?, ?, ?, ?, ?)
                                            """,
                                            (
                                                selected_item_name,
                                                quantity_out,
                                                unit,
                                                user_name,
                                                formatted_notes,
                                            ),
                                        )

                                        cursor.execute(
                                            "SELECT current_stock FROM master_items WHERE item_name = ?",
                                            (selected_item_name,),
                                        )
                                        updated_stock = cursor.fetchone()[0]
                                        conn_trans.commit()

                                        msg = f"✅ Issued {quantity_out:,.2f} {unit} of {selected_item_name}. Remaining: {updated_stock:,.2f} {unit}."
                                        if updated_stock <= min_thresh:
                                            msg += " 🔔 Low Stock Alert triggered!"
                                        
                                        st.session_state["flash_msg"] = ("success", msg)
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
                history_df = pd.read_sql_query(
                    """
                    SELECT id, timestamp, item_name, quantity, unit, handled_by, notes 
                    FROM transactions 
                    WHERE type = 'STOCK OUT'
                    ORDER BY id DESC
                    LIMIT 100
                    """,
                    conn,
                )

            if not history_df.empty:
                df_display = history_df.rename(
                    columns={
                        "id": "Log ID",
                        "timestamp": "Date & Time",
                        "item_name": "Item Name",
                        "quantity": "Quantity Issued",
                        "unit": "Unit",
                        "handled_by": "Handled By",
                        "notes": "Recipient / Purpose",
                    }
                )
                st.dataframe(df_display, use_container_width=True, hide_index=True)
            else:
                st.info("No outgoing stock transactions recorded yet.")

        except Exception as e:
            st.error(f"Error loading Stock Out history: {e}")
