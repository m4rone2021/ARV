# views/physical_inventory.py
import sqlite3
import pandas as pd
import streamlit as st
from database import get_db, init_db

def render_physical_inventory(user_name, user_role):
    st.title("📋 Physical Inventory & Stock Audit")
    st.caption("Conduct physical stock counts, calculate variance against system inventory, and apply stock reconciliations.")

    init_db()

    tab_count, tab_history = st.tabs(["📊 Stock Audit & Reconciliation", "📜 Reconciliation History"])

    # -------------------------------------------------------------
    # TAB 1: AUDIT FORM & VARIANCE CALCULATION
    # -------------------------------------------------------------
    with tab_count:
        st.subheader("Physical Count Verification")

        try:
            with get_db() as conn:
                items_df = pd.read_sql_query(
                    "SELECT id, item_name, category, unit, current_stock FROM master_items ORDER BY item_name ASC", 
                    conn
                )

            if not items_df.empty:
                # Item selection
                selected_item_name = st.selectbox("Select Item to Audit*", items_df["item_name"].tolist())
                
                # Fetch row details for selected item
                item_row = items_df[items_df["item_name"] == selected_item_name].iloc[0]
                system_stock = float(item_row["current_stock"])
                unit = item_row["unit"]

                st.divider()

                # Display current system inventory info
                col_sys, col_input = st.columns(2)
                
                with col_sys:
                    st.markdown("### **System Record**")
                    st.metric(label=f"Expected Stock ({unit})", value=f"{system_stock:,.2f}")
                    st.write(f"**Category:** {item_row['category']}")

                with col_input:
                    st.markdown("### **Physical Count**")
                    physical_count = st.number_input(
                        f"Actual Counted Stock ({unit})*", 
                        min_value=0.0, 
                        value=system_stock, 
                        step=1.0
                    )

                # Calculate Variance
                variance = physical_count - system_stock
                
                st.divider()
                st.subheader("🔍 Audit Result & Variance Summary")

                v_col1, v_col2 = st.columns(2)
                
                with v_col1:
                    if variance == 0:
                        st.success("✅ **Zero Variance**: Physical count matches system records perfectly.")
                    elif variance > 0:
                        st.warning(f"📈 **Surplus Detected**: Physical count is **+{variance:,.2f} {unit}** higher than system stock.")
                    else:
                        st.error(f"📉 **Deficit Detected**: Physical count is **{variance:,.2f} {unit}** lower than system stock.")

                with v_col2:
                    audit_notes = st.text_input("Audit Notes / Cause of Discrepancy*", placeholder="e.g., Damaged items removed, Unrecorded site transfer")

                # Form Submission / Stock Reconciliation
                st.divider()
                if st.button("💾 Apply Stock Reconciliation", use_container_width=True):
                    if variance != 0 and not audit_notes.strip():
                        st.error("⚠️ Audit notes are required when there is a stock variance.")
                    else:
                        try:
                            with get_db() as conn:
                                cursor = conn.cursor()

                                # 1. Update Master Stock to match physical count
                                cursor.execute(
                                    "UPDATE master_items SET current_stock = ? WHERE item_name = ?",
                                    (physical_count, selected_item_name)
                                )

                                # 2. Log variance adjustment transaction in Audit Log
                                trans_type = "RECONCILIATION (SURPLUS)" if variance >= 0 else "RECONCILIATION (DEFICIT)"
                                note_entry = f"Physical Audit Count: {physical_count} {unit}. Diff: {variance:+.2f} {unit}. Reason: {audit_notes.strip()}"
                                
                                cursor.execute("""
                                    INSERT INTO transactions (type, item_name, quantity, unit, handled_by, notes)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                """, (trans_type, selected_item_name, abs(variance), unit, user_name, note_entry))

                                conn.commit()
                                st.success(f"✅ Stock for **{selected_item_name}** successfully reconciled to **{physical_count:,.2f} {unit}**.")
                                st.rerun()

                        except Exception as e:
                            st.error(f"Failed to reconcile inventory: {e}")

            else:
                st.info("No items found in Master Catalog to audit.")

        except Exception as e:
            st.error(f"Error loading items for physical count: {e}")

    # -------------------------------------------------------------
    # TAB 2: AUDIT RECONCILIATION HISTORY
    # -------------------------------------------------------------
    with tab_history:
        st.subheader("Recent Physical Inventory Logs")

        try:
            with get_db() as conn:
                rec_df = pd.read_sql_query("""
                    SELECT id, timestamp, type, item_name, quantity, unit, handled_by, notes 
                    FROM transactions 
                    WHERE type LIKE 'RECONCILIATION%' 
                    ORDER BY id DESC
                """, conn)

            if not rec_df.empty:
                df_display = rec_df.rename(columns={
                    "id": "Trans ID",
                    "timestamp": "Date & Time",
                    "type": "Adjustment Type",
                    "item_name": "Item Name",
                    "quantity": "Variance Qty",
                    "unit": "Unit",
                    "handled_by": "Audited By",
                    "notes": "Audit Notes & Observations"
                })
                st.dataframe(df_display, use_container_width=True, hide_index=True)
            else:
                st.info("No physical count reconciliation records found.")

        except Exception as e:
            st.error(f"Error fetching reconciliation logs: {e}")
