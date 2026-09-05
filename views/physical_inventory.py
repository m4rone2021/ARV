# views/physical_inventory.py
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db


def render_physical_inventory(user_name, user_role):
    st.title("📋 Physical Inventory & Discrepancy Approval")
    st.caption(
        "Perform physical stock counts. Discrepancies are held for Admin review before stock is modified."
    )

    is_admin = user_role == "Admin"

    # Dynamic Tabs based on user role
    if is_admin:
        tab_count, tab_pending, tab_history = st.tabs(
            [
                "📊 Conduct Stock Count",
                "⚠️ Pending Discrepancies",
                "📜 Audit & Resolution Logs",
            ]
        )
    else:
        tab_count, tab_history = st.tabs(
            [
                "📊 Conduct Stock Count",
                "📜 Audit & Resolution Logs",
            ]
        )

    # -------------------------------------------------------------
    # TAB 1: CONDUCT PHYSICAL COUNT (All Users)
    # -------------------------------------------------------------
    with tab_count:
        st.subheader("Physical Count Entry")

        try:
            with get_db() as conn:
                items_df = pd.read_sql_query(
                    """
                    SELECT id, item_name, category, unit, current_stock 
                    FROM master_items 
                    ORDER BY item_name ASC
                    """,
                    conn,
                )

            if not items_df.empty:
                selected_item_name = st.selectbox(
                    "Select Item to Audit*",
                    items_df["item_name"].tolist(),
                    key="audit_item_selector",
                )
                item_row = items_df[
                    items_df["item_name"] == selected_item_name
                ].iloc[0]
                system_stock = float(item_row["current_stock"])
                unit = str(item_row["unit"])

                st.divider()

                col_sys, col_input = st.columns(2)
                with col_sys:
                    st.markdown("### **System Record**")
                    st.metric(
                        label=f"Expected Stock ({unit})",
                        value=f"{system_stock:,.2f}",
                    )
                    st.write(f"**Category:** {item_row['category']}")

                with col_input:
                    st.markdown("### **Physical Count**")
                    # Key ensures default value resets whenever the selected item changes
                    physical_count = st.number_input(
                        f"Actual Counted Stock ({unit})*",
                        min_value=0.0,
                        value=system_stock,
                        step=1.0,
                        format="%.2f",
                        key=f"physical_input_{selected_item_name}",
                    )

                variance = physical_count - system_stock

                st.divider()
                st.subheader("🔍 Variance Summary")

                v_col1, v_col2 = st.columns(2)
                with v_col1:
                    if variance == 0:
                        st.success(
                            "✅ **Zero Variance**: Physical count matches system stock."
                        )
                    elif variance > 0:
                        st.warning(
                            f"📈 **Surplus (+{variance:,.2f} {unit})**: Pending Admin verification."
                        )
                    else:
                        st.error(
                            f"📉 **Deficit ({variance:,.2f} {unit})**: Pending Admin investigation."
                        )

                with v_col2:
                    submission_notes = st.text_input(
                        "Observation / Cause of Discrepancy*",
                        placeholder="e.g., Damaged materials found during count",
                        key=f"notes_{selected_item_name}",
                    )

                st.divider()

                if st.button(
                    "💾 Submit Physical Audit", use_container_width=True
                ):
                    if variance != 0 and not submission_notes.strip():
                        st.error(
                            "⚠️ Observation notes are required when submitting a stock discrepancy."
                        )
                    else:
                        try:
                            with get_db() as conn:
                                cursor = conn.cursor()

                                if variance == 0:
                                    st.toast(
                                        f"✅ Verified zero variance for {selected_item_name}",
                                        icon="✅",
                                    )
                                    st.success(
                                        f"Physical count for **{selected_item_name}** verified with zero variance."
                                    )
                                else:
                                    cursor.execute(
                                        """
                                        INSERT INTO discrepancies 
                                        (item_name, system_stock, physical_count, variance, unit, submitted_by, submission_notes, status)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
                                    """,
                                        (
                                            selected_item_name,
                                            system_stock,
                                            physical_count,
                                            variance,
                                            unit,
                                            user_name,
                                            submission_notes.strip(),
                                        ),
                                    )

                                    conn.commit()
                                    st.toast(
                                        f"⚠️ Discrepancy logged for {selected_item_name}",
                                        icon="📌",
                                    )
                                    st.warning(
                                        f"Discrepancy logged for **{selected_item_name}**. Sent to Admin for review."
                                    )
                                    st.rerun()

                        except sqlite3.OperationalError as e:
                            st.error(f"Failed to submit physical count: {e}")

            else:
                st.info("No items found in Master Catalog to audit.")

        except Exception as e:
            st.error(f"Error loading catalog items: {e}")

    # -------------------------------------------------------------
    # TAB 2: PENDING DISCREPANCIES (Admin Only)
    # -------------------------------------------------------------
    if is_admin:
        with tab_pending:
            st.subheader("⚠️ Pending Inventory Discrepancies")

            try:
                with get_db() as conn:
                    pending_df = pd.read_sql_query(
                        """
                        SELECT id, timestamp, item_name, system_stock, physical_count, variance, unit, submitted_by, submission_notes 
                        FROM discrepancies 
                        WHERE status = 'PENDING'
                        ORDER BY id DESC
                    """,
                        conn,
                    )

                if not pending_df.empty:
                    st.info(
                        f"🔔 You have **{len(pending_df)}** discrepancy request(s) awaiting resolution."
                    )

                    for _, row in pending_df.iterrows():
                        disc_id = int(row["id"])
                        var_val = float(row["variance"])
                        var_type = "SURPLUS" if var_val > 0 else "DEFICIT"

                        with st.expander(
                            f"📌 Request #{disc_id}: {row['item_name']} ({var_type}: {var_val:+.2f} {row['unit']})"
                        ):
                            c1, c2, c3 = st.columns(3)
                            c1.metric(
                                "System Stock (At Audit)",
                                f"{row['system_stock']} {row['unit']}",
                            )
                            c2.metric(
                                "Physical Count",
                                f"{row['physical_count']} {row['unit']}",
                            )
                            c3.metric(
                                "Variance", f"{var_val:+.2f} {row['unit']}"
                            )

                            st.write(
                                f"**Submitted By:** {row['submitted_by']} on `{row['timestamp']}`"
                            )
                            st.write(
                                f"**Supervisor Notes:** {row['submission_notes']}"
                            )

                            st.markdown("---")
                            st.markdown("#### **Admin Resolution Decision**")

                            resolution_reason = st.text_input(
                                f"Resolution Reason / Investigation Finding (Req #{disc_id})*",
                                key=f"res_note_{disc_id}",
                                placeholder="e.g., Investigation confirmed leakage; adjusting stock balance.",
                            )

                            btn_approve, btn_reject = st.columns(2)

                            # APPROVE DISCREPANCY
                            with btn_approve:
                                if st.button(
                                    "✅ Approve & Apply Stock Change",
                                    key=f"app_{disc_id}",
                                    use_container_width=True,
                                ):
                                    if not resolution_reason.strip():
                                        st.error(
                                            "⚠️ You must provide a resolution reason before approving."
                                        )
                                    else:
                                        try:
                                            with get_db() as conn_action:
                                                cursor = conn_action.cursor()

                                                # Atomic updates inside explicit transaction
                                                cursor.execute(
                                                    "UPDATE master_items SET current_stock = ? WHERE item_name = ?",
                                                    (
                                                        row["physical_count"],
                                                        row["item_name"],
                                                    ),
                                                )

                                                cursor.execute(
                                                    """
                                                    UPDATE discrepancies
                                                    SET status = 'APPROVED', resolved_by = ?, resolved_timestamp = CURRENT_TIMESTAMP, resolution_notes = ?
                                                    WHERE id = ?
                                                """,
                                                    (
                                                        user_name,
                                                        resolution_reason.strip(),
                                                        disc_id,
                                                    ),
                                                )

                                                audit_note = f"Discrepancy Approved. Diff: {var_val:+.2f} {row['unit']}. Reason: {resolution_reason.strip()}"
                                                cursor.execute(
                                                    """
                                                    INSERT INTO transactions (type, item_name, quantity, unit, handled_by, notes)
                                                    VALUES (?, ?, ?, ?, ?, ?)
                                                """,
                                                    (
                                                        f"RECONCILIATION ({var_type})",
                                                        row["item_name"],
                                                        abs(var_val),
                                                        row["unit"],
                                                        user_name,
                                                        audit_note,
                                                    ),
                                                )

                                                conn_action.commit()
                                                st.toast(
                                                    f"✅ Approved Request #{disc_id}",
                                                    icon="✅",
                                                )
                                                st.success(
                                                    f"Request #{disc_id} Approved. Stock updated to {row['physical_count']} {row['unit']}."
                                                )
                                                st.rerun()
                                        except Exception as e:
                                            st.error(
                                                f"Error approving discrepancy: {e}"
                                            )

                            # REJECT DISCREPANCY
                            with btn_reject:
                                if st.button(
                                    "❌ Reject (Keep System Stock)",
                                    key=f"rej_{disc_id}",
                                    use_container_width=True,
                                ):
                                    if not resolution_reason.strip():
                                        st.error(
                                            "⚠️ You must provide a resolution reason before rejecting."
                                        )
                                    else:
                                        try:
                                            with get_db() as conn_action:
                                                cursor = conn_action.cursor()
                                                cursor.execute(
                                                    """
                                                    UPDATE discrepancies
                                                    SET status = 'REJECTED', resolved_by = ?, resolved_timestamp = CURRENT_TIMESTAMP, resolution_notes = ?
                                                    WHERE id = ?
                                                """,
                                                    (
                                                        user_name,
                                                        resolution_reason.strip(),
                                                        disc_id,
                                                    ),
                                                )
                                                conn_action.commit()
                                                st.toast(
                                                    f"❌ Rejected Request #{disc_id}",
                                                    icon="❌",
                                                )
                                                st.warning(
                                                    f"Request #{disc_id} Rejected. System stock preserved."
                                                )
                                                st.rerun()
                                        except Exception as e:
                                            st.error(
                                                f"Error rejecting discrepancy: {e}"
                                            )

                else:
                    st.success(
                        "🎉 No pending inventory discrepancies requiring review."
                    )

            except Exception as e:
                st.error(f"Error loading pending discrepancies: {e}")

    # -------------------------------------------------------------
    # TAB 3: RESOLUTION & AUDIT LOGS (All Users)
    # -------------------------------------------------------------
    with tab_history:
        st.subheader("📜 Physical Audit & Resolution History")

        try:
            with get_db() as conn:
                history_df = pd.read_sql_query(
                    """
                    SELECT id, timestamp, item_name, variance, unit, submitted_by, submission_notes, status, resolved_by, resolved_timestamp, resolution_notes
                    FROM discrepancies 
                    ORDER BY id DESC
                """,
                    conn,
                )

            if not history_df.empty:
                df_display = history_df.rename(
                    columns={
                        "id": "Req ID",
                        "timestamp": "Submitted Date",
                        "item_name": "Item Name",
                        "variance": "Variance",
                        "unit": "Unit",
                        "submitted_by": "Audited By",
                        "submission_notes": "Audit Notes",
                        "status": "Status",
                        "resolved_by": "Resolved By",
                        "resolved_timestamp": "Resolution Date",
                        "resolution_notes": "Admin Resolution Reason",
                    }
                )
                st.dataframe(
                    df_display,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Variance": st.column_config.NumberColumn(format="%.2f")
                    },
                )
            else:
                st.info("No audit history recorded yet.")

        except Exception as e:
            st.error(f"Error loading audit history: {e}")
