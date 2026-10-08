"""Water system physical inventory — count, submit discrepancies, admin resolve."""
from datetime import datetime

import pandas as pd
import streamlit as st

from database import sb
from watersystem import config as cfg


def render(user_name: str, is_admin: bool):
    st.title("📋 Water System — Physical Inventory")
    st.caption("Conduct physical counts. Discrepancies are held for Admin review.")

    if is_admin:
        tab_count, tab_pending, tab_history = st.tabs(
            ["📊 Conduct Stock Count", "⚠️ Pending Discrepancies", "📜 Audit & Resolution Logs"]
        )
    else:
        tab_count, tab_history = st.tabs(
            ["📊 Conduct Stock Count", "📜 Audit & Resolution Logs"]
        )

    with tab_count:
        st.subheader("Physical Count Entry")
        try:
            res = (
                sb().table("master_items")
                .select("id, item_name, category, unit, current_stock, size")
                .eq("warehouse", cfg.WAREHOUSE)
                .order("item_name").execute()
            )
            items_df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error loading water items: {e}")
            items_df = pd.DataFrame()

        if items_df.empty:
            st.info("No water items found.")
        else:
            names = sorted(items_df["item_name"].unique().tolist())
            picked_name = st.selectbox(
                "Select Item to Audit*", names, key="_wspi_item",
            )
            subset = items_df[items_df["item_name"] == picked_name]
            size_options = subset["size"].fillna("").tolist()
            if len(size_options) == 1:
                picked_size = size_options[0]
                if picked_size:
                    st.caption(f"Size: {picked_size}")
            else:
                picked_size = st.radio(
                    "Size", size_options, horizontal=True, key="_wspi_size",
                )
            item_row = subset[subset["size"].fillna("") == picked_size].iloc[0]
            selected_item_name = item_row["item_name"]
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
                min_value=0.0, value=system_stock, step=1.0, format="%.2f",
                key=f"_wspi_count_{selected_item_name}",
            )

            variance = physical_count - system_stock

            st.divider()
            st.subheader("🔍 Variance Summary")
            if variance == 0:
                st.success("✅ **Zero Variance**: Physical count matches system stock.")
            elif variance > 0:
                st.warning(f"📈 **Surplus (+{variance:,.2f} {unit})**: Pending Admin verification.")
            else:
                st.error(f"📉 **Deficit ({variance:,.2f} {unit})**: Pending Admin investigation.")

            submission_notes = st.text_input(
                "Observation / Cause of Discrepancy*",
                placeholder="e.g., Damaged fittings found during count",
                key=f"_wspi_notes_{selected_item_name}",
            )

            st.divider()
            if st.button("💾 Submit Physical Audit", width="stretch", key="_wspi_submit"):
                if variance != 0 and not submission_notes.strip():
                    st.error("⚠️ Observation notes required when variance is non-zero.")
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
                            "warehouse": cfg.WAREHOUSE,
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
                                "warehouse": cfg.WAREHOUSE,
                            }).execute()
                            st.toast(f"⚠️ Discrepancy logged for {selected_item_name}")
                            st.warning(f"Discrepancy logged for **{selected_item_name}**. Sent to Admin.")
                        else:
                            st.toast(f"✅ Verified zero variance for {selected_item_name}")
                            st.success(f"Physical count for **{selected_item_name}** verified.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to submit physical count: {e}")

    if is_admin:
        with tab_pending:
            st.subheader("⚠️ Pending Water Discrepancies")
            try:
                res = (
                    sb().table("discrepancies")
                    .select("id, timestamp, created_at, item_name, system_stock, physical_count, variance, "
                            "unit, submitted_by, submission_notes")
                    .eq("status", "PENDING")
                    .eq("warehouse", cfg.WAREHOUSE)
                    .order("created_at", desc=True).order("timestamp", desc=True).execute()
                )
                pending_df = pd.DataFrame(res.data or [])
            except Exception as e:
                st.error(f"Error loading pending discrepancies: {e}")
                pending_df = pd.DataFrame()

            if pending_df.empty:
                st.success("🎉 No pending water discrepancies.")
            else:
                st.info(f"🔔 **{len(pending_df)}** water discrepancy request(s) awaiting resolution.")

                for _, row in pending_df.iterrows():
                    disc_id = row["id"]
                    var_val = float(row["variance"])
                    var_type = "SURPLUS" if var_val > 0 else "DEFICIT"

                    with st.expander(
                        f"📌 Request #{str(disc_id)[:8]}…: {row['item_name']} ({var_type}: {var_val:+.2f} {row['unit']})"
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
                            key=f"_wspi_res_{disc_id}",
                            placeholder="e.g., Leakage confirmed during site inspection.",
                        )

                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button("✅ Approve & Apply Stock Change", key=f"_wspi_app_{disc_id}", width="stretch"):
                                if not resolution_reason.strip():
                                    st.error("⚠️ Resolution reason required.")
                                else:
                                    try:
                                        sb().table("master_items").update(
                                            {"current_stock": float(row["physical_count"])}
                                        ).eq("item_name", row["item_name"]).eq("warehouse", cfg.WAREHOUSE).execute()

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
                                            "warehouse": cfg.WAREHOUSE,
                                        }).execute()

                                        st.toast("✅ Approved Request")
                                        st.success(f"Stock updated to {row['physical_count']} {row['unit']}.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error approving discrepancy: {e}")

                        with col_b:
                            if st.button("❌ Reject (Keep System Stock)", key=f"_wspi_rej_{disc_id}", width="stretch"):
                                if not resolution_reason.strip():
                                    st.error("⚠️ Resolution reason required.")
                                else:
                                    try:
                                        sb().table("discrepancies").update({
                                            "status": "REJECTED",
                                            "resolved_by": user_name,
                                            "resolved_timestamp": datetime.utcnow().isoformat(),
                                            "resolution_notes": resolution_reason.strip(),
                                        }).eq("id", disc_id).execute()

                                        st.toast("❌ Rejected Request")
                                        st.warning("Request rejected. System stock preserved.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error rejecting discrepancy: {e}")

    with tab_history:
        st.subheader("📜 Water Physical Audit History")
        try:
            res = (
                sb().table("discrepancies")
                .select("id, timestamp, created_at, item_name, variance, unit, submitted_by, "
                        "submission_notes, status, resolved_by, resolved_timestamp, resolution_notes")
                .eq("warehouse", cfg.WAREHOUSE)
                .order("created_at", desc=True).order("timestamp", desc=True).execute()
            )
            history_df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error loading audit history: {e}")
            history_df = pd.DataFrame()

        if history_df.empty:
            st.info("No water audit history recorded yet.")
        else:
            df_display = history_df.rename(columns={
                "id": "Req ID", "timestamp": "Submitted Date", "created_at": "Logged At",
                "item_name": "Item Name", "variance": "Variance", "unit": "Unit",
                "submitted_by": "Audited By", "submission_notes": "Audit Notes",
                "status": "Status", "resolved_by": "Resolved By",
                "resolved_timestamp": "Resolution Date",
                "resolution_notes": "Admin Resolution Reason",
            })

            view_mode = st.radio(
                "Display Mode", ["Cards (Mobile)", "Full Table"],
                horizontal=True, label_visibility="collapsed", key="_wspi_hist_mode",
            )

            if view_mode == "Cards (Mobile)":
                for _, row in df_display.iterrows():
                    status_flag = (
                        "🟢 APPROVED" if row["Status"] == "APPROVED"
                        else "🔴 REJECTED" if row["Status"] == "REJECTED"
                        else "🟡 PENDING"
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
                    df_display, width="stretch", hide_index=True,
                    column_config={"Variance": st.column_config.NumberColumn(format="%.2f")},
                )