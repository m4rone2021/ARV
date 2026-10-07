from datetime import datetime

import pandas as pd
import streamlit as st

from database import sb


def render_physical_inventory(user_name, user_role):
    st.title("Ã°Å¸â€œâ€¹ Physical Inventory & Discrepancy Approval")
    st.caption(
        "Perform physical stock counts. Discrepancies are held for Admin review before stock is modified."
    )

    is_admin = user_role == "Admin"

    if is_admin:
        tab_count, tab_pending, tab_history = st.tabs(
            ["Ã°Å¸â€œÅ  Conduct Stock Count", "Ã¢Å¡Â Ã¯Â¸Â Pending Discrepancies", "Ã°Å¸â€œÅ“ Audit & Resolution Logs"]
        )
    else:
        tab_count, tab_history = st.tabs(
            ["Ã°Å¸â€œÅ  Conduct Stock Count", "Ã°Å¸â€œÅ“ Audit & Resolution Logs"]
        )

    with tab_count:
        st.subheader("Physical Count Entry")

        try:
            res = (
                sb()
                .table("master_items")
                .select("id, item_name, category, unit, current_stock")
                .order("item_name")
                .execute()
            )
            items_df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error loading catalog items: {e}")
            items_df = pd.DataFrame()

        if items_df.empty:
            st.info("No items found in Master Catalog to audit.")
        else:
            selected_item_name = st.selectbox(
                "Select Item to Audit*",
                items_df["item_name"].tolist(),
                key="audit_item_selector",
            )
            item_row = items_df[items_df["item_name"] == selected_item_name].iloc[0]
            system_stock = float(item_row["current_stock"] or 0)
            unit = str(item_row["unit"])

            st.divider()
            st.markdown("### **System Record**")
            st.metric(label=f"Expected Stock ({unit})", value=f"{system_stock:,.2f}")
            st.write(f"**Category:** {item_row['category']}")

            st.markdown("---")
            st.markdown("### **Physical Count**")
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
            st.subheader("Ã°Å¸â€Â Variance Summary")

            if variance == 0:
                st.success("Ã¢Å“â€¦ **Zero Variance**: Physical count matches system stock.")
            elif variance > 0:
                st.warning(f"Ã°Å¸â€œË† **Surplus (+{variance:,.2f} {unit})**: Pending Admin verification.")
            else:
                st.error(f"Ã°Å¸â€œâ€° **Deficit ({variance:,.2f} {unit})**: Pending Admin investigation.")

            submission_notes = st.text_input(
                "Observation / Cause of Discrepancy*",
                placeholder="e.g., Damaged materials found during count",
                key=f"notes_{selected_item_name}",
            )

            st.divider()

            if st.button("Ã°Å¸â€™Â¾ Submit Physical Audit", width='stretch'):
                if variance != 0 and not submission_notes.strip():
                    st.error("Ã¢Å¡Â Ã¯Â¸Â Observation notes are required when submitting a stock discrepancy.")
                else:
                    try:
                        sb().table("physical_inventory_logs").insert({
                            "item_name": selected_item_name,
                            "system_qty": system_stock,
                            "counted_qty": physical_count,
                            "variance": variance,
                            "unit": unit,
                            "counted_by": user_name,
                            "notes": submission_notes.strip() or None,
                        }).execute()

                        if variance != 0:
                            sb().table("discrepancies").insert({
                                "item_name": selected_item_name,
                                "system_stock": system_stock,
                                "physical_count": physical_count,
                                "variance": variance,
                                "unit": unit,
                                "submitted_by": user_name,
                                "submission_notes": submission_notes.strip(),
                                "status": "PENDING",
                            }).execute()
                            st.toast(f"Ã¢Å¡Â Ã¯Â¸Â Discrepancy logged for {selected_item_name}", icon="Ã°Å¸â€œÅ’")
                            st.warning(f"Discrepancy logged for **{selected_item_name}**. Sent to Admin.")
                        else:
                            st.toast(f"Ã¢Å“â€¦ Verified zero variance for {selected_item_name}", icon="Ã¢Å“â€¦")
                            st.success(f"Physical count for **{selected_item_name}** verified.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to submit physical count: {e}")

    if is_admin:
        with tab_pending:
            st.subheader("Ã¢Å¡Â Ã¯Â¸Â Pending Inventory Discrepancies")
            try:
                res = (
                    sb()
                    .table("discrepancies")
                    .select("id, timestamp, created_at, item_name, system_stock, physical_count, variance, "
                            "unit, submitted_by, submission_notes")
                    .eq("status", "PENDING")
                    .order("created_at", desc=True).order("timestamp", desc=True)
                    .execute()
                )
                pending_df = pd.DataFrame(res.data or [])
            except Exception as e:
                st.error(f"Error loading pending discrepancies: {e}")
                pending_df = pd.DataFrame()

            if pending_df.empty:
                st.success("Ã°Å¸Å½â€° No pending inventory discrepancies requiring review.")
            else:
                st.info(f"Ã°Å¸â€â€ You have **{len(pending_df)}** discrepancy request(s) awaiting resolution.")

                for _, row in pending_df.iterrows():
                    disc_id = row["id"]
                    var_val = float(row["variance"])
                    var_type = "SURPLUS" if var_val > 0 else "DEFICIT"

                    with st.expander(
                        f"Ã°Å¸â€œÅ’ Request #{str(disc_id)[:8]}Ã¢â‚¬Â¦: {row['item_name']} ({var_type}: {var_val:+.2f} {row['unit']})"
                    ):
                        st.metric("System Stock (At Audit)", f"{row['system_stock']} {row['unit']}")
                        st.metric("Physical Count", f"{row['physical_count']} {row['unit']}")
                        st.metric("Variance", f"{var_val:+.2f} {row['unit']}")

                        st.markdown("---")
                        st.write(f"**Submitted By:** {row['submitted_by']} on `{row['timestamp']}`")
                        st.write(f"**Supervisor Notes:** {row['submission_notes']}")

                        st.markdown("---")
                        st.markdown("#### **Admin Resolution Decision**")

                        resolution_reason = st.text_input(
                            f"Resolution Reason (Req #{str(disc_id)[:8]})*",
                            key=f"res_note_{disc_id}",
                            placeholder="e.g., Investigation confirmed leakage.",
                        )

                        col_a, col_b = st.columns(2)

                        with col_a:
                            if st.button("Ã¢Å“â€¦ Approve & Apply Stock Change", key=f"app_{disc_id}", width='stretch'):
                                if not resolution_reason.strip():
                                    st.error("Ã¢Å¡Â Ã¯Â¸Â You must provide a resolution reason before approving.")
                                else:
                                    try:
                                        sb().table("master_items").update(
                                            {"current_stock": float(row["physical_count"])}
                                        ).eq("item_name", row["item_name"]).execute()

                                        sb().table("discrepancies").update({
                                            "status": "APPROVED",
                                            "resolved_by": user_name,
                                            "resolved_timestamp": datetime.utcnow().isoformat(),
                                            "resolution_notes": resolution_reason.strip(),
                                        }).eq("id", disc_id).execute()

                                        audit_note = (
                                            f"Discrepancy Approved. Diff: {var_val:+.2f} {row['unit']}. "
                                            f"Reason: {resolution_reason.strip()}"
                                        )
                                        sb().table("transactions").insert({
                                            "type": "RECONCILIATION",
                                            "item_name": row["item_name"],
                                            "quantity": abs(var_val),
                                            "unit": row["unit"],
                                            "handled_by": user_name,
                                            "notes": audit_note,
                                        }).execute()

                                        st.toast("Ã¢Å“â€¦ Approved Request", icon="Ã¢Å“â€¦")
                                        st.success(f"Request approved. Stock updated to {row['physical_count']} {row['unit']}.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error approving discrepancy: {e}")

                        with col_b:
                            if st.button("Ã¢ÂÅ’ Reject (Keep System Stock)", key=f"rej_{disc_id}", width='stretch'):
                                if not resolution_reason.strip():
                                    st.error("Ã¢Å¡Â Ã¯Â¸Â You must provide a resolution reason before rejecting.")
                                else:
                                    try:
                                        sb().table("discrepancies").update({
                                            "status": "REJECTED",
                                            "resolved_by": user_name,
                                            "resolved_timestamp": datetime.utcnow().isoformat(),
                                            "resolution_notes": resolution_reason.strip(),
                                        }).eq("id", disc_id).execute()

                                        st.toast("Ã¢ÂÅ’ Rejected Request", icon="Ã¢ÂÅ’")
                                        st.warning("Request rejected. System stock preserved.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error rejecting discrepancy: {e}")

    with tab_history:
        st.subheader("Ã°Å¸â€œÅ“ Physical Audit & Resolution History")

        try:
            res = (
                sb()
                .table("discrepancies")
                .select("id, timestamp, created_at, item_name, variance, unit, submitted_by, "
                        "submission_notes, status, resolved_by, resolved_timestamp, resolution_notes")
                .order("created_at", desc=True).order("timestamp", desc=True)
                .execute()
            )
            history_df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error loading audit history: {e}")
            history_df = pd.DataFrame()

        if history_df.empty:
            st.info("No audit history recorded yet.")
        else:
            df_display = history_df.rename(columns={
                "id": "Req ID", "timestamp": "Submitted Date", "created_at": "Logged At", "item_name": "Item Name",
                "variance": "Variance", "unit": "Unit", "submitted_by": "Audited By",
                "submission_notes": "Audit Notes", "status": "Status",
                "resolved_by": "Resolved By", "resolved_timestamp": "Resolution Date",
                "resolution_notes": "Admin Resolution Reason",
            })

            view_mode = st.radio(
                "Display Mode",
                ["Cards (Mobile)", "Full Table"],
                horizontal=True,
                label_visibility="collapsed",
                key="history_display_mode",
            )

            if view_mode == "Cards (Mobile)":
                for _, row in df_display.iterrows():
                    status_flag = (
                        "Ã°Å¸Å¸Â¢ APPROVED" if row["Status"] == "APPROVED"
                        else "Ã°Å¸â€Â´ REJECTED" if row["Status"] == "REJECTED"
                        else "Ã°Å¸Å¸Â¡ PENDING"
                    )
                    var_val = float(row["Variance"])
                    with st.expander(f"#{str(row['Req ID'])[:8]} - {row['Item Name']} ({status_flag})"):
                        st.markdown(f"**Variance:** `{var_val:+.2f} {row['Unit']}`")
                        st.markdown(f"**Audited By:** {row['Audited By']} on `{row['Submitted Date']}`")
                        if row["Audit Notes"]:
                            st.caption(f"Audit Notes: {row['Audit Notes']}")
                        if row["Status"] != "PENDING":
                            st.markdown("---")
                            st.markdown(f"**Resolved By:** {row['Resolved By']} on `{row['Resolution Date']}`")
                            if row["Admin Resolution Reason"]:
                                st.caption(f"Reason: {row['Admin Resolution Reason']}")
            else:
                st.dataframe(
                    df_display,
                    width='stretch',
                    hide_index=True,
                    column_config={"Variance": st.column_config.NumberColumn(format="%.2f")},
                )



