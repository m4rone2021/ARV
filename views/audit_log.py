import re
from pathlib import Path as _Path

import pandas as pd
import streamlit as st

from database import UPLOAD_DIR, sb, upload_file_to_gdrive


def _extract_drive_link(notes):
    if not isinstance(notes, str):
        return ""
    m = re.search(r"(?:Drive Link|Attachment):\s*(https?://\S+)", notes)
    return m.group(1) if m else ""


def _extract_attachment_filename(notes):
    if not isinstance(notes, str):
        return ""
    m = re.search(r"Attachment:\s*([^\s|]+)", notes)
    if m and not m.group(1).startswith("http"):
        return m.group(1)
    return ""


def _extract_field(notes, label):
    if not isinstance(notes, str):
        return ""
    pattern = re.compile(re.escape(label) + r"\s*:\s*([^|]+)", re.IGNORECASE)
    m = pattern.search(notes)
    return m.group(1).strip() if m else ""


def _extract_req_ref(notes):
    if not isinstance(notes, str):
        return ("", "")
    req_m = re.search(r"([A-Z0-9\-]+-REQ-\d{4})", notes)
    rcv_m = re.search(r"([A-Z0-9\-]+-RCV-\d{4})", notes)
    return (req_m.group(1) if req_m else "", rcv_m.group(1) if rcv_m else "")


def _build_delivery_notes(row):
    status = str(row.get("status") or "")
    notes = str(row.get("notes") or "")
    return status + " | " + notes


def _build_phys_notes(row):
    sysq = str(row.get("system_qty") or "")
    var = str(row.get("variance") or "")
    notes = str(row.get("notes") or "")
    return "System Qty: " + sysq + " | Variance: " + var + " | " + notes


def render_audit_log(user_name, user_role):
    st.title("Complete Audit Log")
    st.caption(
        "Track stock movement, deliveries, physical counts, and user activity "
        "with full project traceability."
    )

    frames = []

    # 1. transactions
    try:
        res = (
            sb()
            .table("transactions")
            .select("id, timestamp, type, item_name, quantity, unit, handled_by, notes, project_name")
            .order("timestamp", desc=True)
            .limit(500)
            .execute()
        )
        if res.data:
            df = pd.DataFrame(res.data)
            df["type"] = df["type"].apply(_normalize_tx_type)
            frames.append(df)
    except Exception as e:
        st.warning("Could not load transactions: " + str(e))

    # 2. deliveries
    try:
        res = (
            sb()
            .table("deliveries")
            .select("id, created_at, item_name, expected_quantity, unit, created_by, status, notes, project")
            .order("created_at", desc=True)
            .limit(500)
            .execute()
        )
        if res.data:
            df = pd.DataFrame(res.data)
            df = df.rename(columns={
                "created_at": "timestamp",
                "expected_quantity": "quantity",
                "created_by": "handled_by",
                "project": "project_name",
            })
            df["type"] = "SCHEDULED DELIVERY"
            df["notes"] = df.apply(_build_delivery_notes, axis=1)
            frames.append(df[["id", "timestamp", "type", "item_name", "quantity", "unit", "handled_by", "notes", "project_name"]])
    except Exception as e:
        st.warning("Could not load deliveries: " + str(e))

    # 3. physical_inventory_logs
    try:
        res = (
            sb()
            .table("physical_inventory_logs")
            .select("id, timestamp, item_name, system_qty, counted_qty, variance, unit, counted_by, notes")
            .order("timestamp", desc=True)
            .limit(500)
            .execute()
        )
        if res.data:
            df = pd.DataFrame(res.data)
            df = df.rename(columns={
                "counted_qty": "quantity",
                "counted_by": "handled_by",
            })
            df["type"] = "PHYSICAL INVENTORY"
            df["project_name"] = None
            df["notes"] = df.apply(_build_phys_notes, axis=1)
            frames.append(df[["id", "timestamp", "type", "item_name", "quantity", "unit", "handled_by", "notes", "project_name"]])
    except Exception as e:
        st.warning("Could not load physical inventory logs: " + str(e))

    # 4. user_logs
    try:
        res = (
            sb()
            .table("user_logs")
            .select("id, timestamp, username, action, details")
            .order("timestamp", desc=True)
            .limit(500)
            .execute()
        )
        if res.data:
            df = pd.DataFrame(res.data)
            df = df.rename(columns={
                "username": "handled_by",
                "action": "item_name",
            })
            df["type"] = "USER LOG"
            df["quantity"] = "-"
            df["unit"] = "-"
            df["notes"] = df["details"]
            df["project_name"] = None
            frames.append(df[["id", "timestamp", "type", "item_name", "quantity", "unit", "handled_by", "notes", "project_name"]])
    except Exception as e:
        st.warning("Could not load user logs: " + str(e))

    if not frames:
        st.info("No audit logs found.")
        return

    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.sort_values("timestamp", ascending=False).reset_index(drop=True)

    # Derive extended fields
    df["Destination"] = df["notes"].apply(_extract_destination)
    df["Requested By"] = df["notes"].apply(_extract_requested_by)
    df["Supplier"] = df["notes"].apply(_extract_supplier)
    refs = df["notes"].apply(_extract_req_ref)
    df["Requisition"] = [r[0] for r in refs]
    df["Receipt"] = [r[1] for r in refs]

    # Filters
    with st.expander("Search and Filter", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            proj_vals = sorted([p for p in df["project_name"].dropna().unique() if p])
            project_filter = st.selectbox("Project", ["All Projects"] + proj_vals)
            type_filter = st.selectbox(
                "Log Type",
                ["All Activity", "STOCK IN", "STOCK OUT", "SCHEDULED DELIVERY",
                 "PHYSICAL INVENTORY", "USER LOG"],
            )
        with c2:
            search_query = st.text_input(
                "Search (item, handler, notes)",
                placeholder="Type keyword...",
            )
            ref_filter = st.text_input(
                "Requisition / Receipt ID",
                placeholder="e.g., PRJ-2026-A-REQ-0001",
            )

    filtered = df.copy()
    if project_filter != "All Projects":
        filtered = filtered[filtered["project_name"] == project_filter]
    if type_filter == "STOCK IN":
        filtered = filtered[filtered["type"].isin(["STOCK IN", "IN"])]
    elif type_filter == "STOCK OUT":
        filtered = filtered[filtered["type"].isin(["STOCK OUT", "OUT"])]
    elif type_filter != "All Activity":
        filtered = filtered[filtered["type"] == type_filter]
    if search_query.strip():
        q = search_query.strip().lower()
        mask = (
            filtered["item_name"].astype(str).str.lower().str.contains(q, na=False)
            | filtered["handled_by"].astype(str).str.lower().str.contains(q, na=False)
            | filtered["notes"].astype(str).str.lower().str.contains(q, na=False)
        )
        filtered = filtered[mask]
    if ref_filter.strip():
        q = ref_filter.strip().lower()
        mask = (
            filtered["Requisition"].astype(str).str.lower().str.contains(q, na=False)
            | filtered["Receipt"].astype(str).str.lower().str.contains(q, na=False)
        )
        filtered = filtered[mask]

    if filtered.empty:
        st.info("No audit logs match the selected filters.")
        return

    # KPI metrics
    in_count = len(filtered[filtered["type"].isin(["STOCK IN", "IN"])])
    out_count = len(filtered[filtered["type"].isin(["STOCK OUT", "OUT"])])
    del_count = len(filtered[filtered["type"] == "SCHEDULED DELIVERY"])
    phys_count = len(filtered[filtered["type"] == "PHYSICAL INVENTORY"])
    user_count = len(filtered[filtered["type"] == "USER LOG"])

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Logs", len(filtered))
    m2.metric("Stock IN", in_count)
    m3.metric("Stock OUT", out_count)
    m4.metric("Deliveries", del_count)
    m5.metric("Phys / User", phys_count + user_count)

    # Project summary
    with_project = filtered[filtered["project_name"].notna() & (filtered["project_name"] != "")]
    if not with_project.empty:
        with st.expander("Project Summary", expanded=False):
            summary = (
                with_project.groupby("project_name")
                .agg(
                    Lines=("id", "count"),
                    First_Move=("timestamp", "min"),
                    Last_Move=("timestamp", "max"),
                )
                .reset_index()
                .rename(columns={"project_name": "Project"})
                .sort_values("Last_Move", ascending=False)
            )
            summary_display = summary.copy()
            summary_display = summary_display.astype(str).replace("None", "").replace("nan", "")
            st.dataframe(summary_display, use_container_width=True, hide_index=True)

    # Main table
    display_cols = [
        "timestamp", "type", "project_name", "Requisition", "Receipt",
        "item_name", "quantity", "unit", "Destination",
        "Requested By", "Supplier", "handled_by", "notes",
    ]
    display_df = filtered[display_cols].rename(columns={
        "timestamp": "Date and Time",
        "type": "Log Type",
        "project_name": "Project",
        "item_name": "Item",
        "quantity": "Qty",
        "unit": "Unit",
        "handled_by": "Handled By",
        "notes": "Details",
    })

    # Clean None/NaN before string coercion
    display_df = display_df.fillna("")
    display_df = display_df.replace(["None", "nan", "NaT", "<NA>"], "")
    display_df = display_df.astype(str)
    # In case astype re-introduced None as string
    display_df = display_df.replace(["None", "nan", "NaT", "<NA>"], "")

    st.divider()
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Attachments
    with st.expander("Attachments and Drive Links"):
        has_media = False
        for _, row in filtered.iterrows():
            notes_str = str(row["notes"])
            link = _extract_drive_link(notes_str)
            local = _extract_attachment_filename(notes_str)
            if link:
                has_media = True
                st.markdown(
                    "Log #" + str(row["id"])[:8] + " (" + row["type"] + " - " +
                    row["item_name"] + "): [Open Document](" + link + ")"
                )
            elif local:
                has_media = True
                file_path = _Path(str(UPLOAD_DIR)) / local
                if file_path.exists():
                    with open(file_path, "rb") as f:
                        st.download_button(
                            label="Download " + local,
                            data=f.read(),
                            file_name=local,
                            key="audit_dl_" + str(row["id"]),
                        )
                else:
                    st.caption("Local file not found: " + local)
        if not has_media:
            st.info("No attachments in the current filter.")

    # Export
    st.divider()
    csv_data = display_df.to_csv(index=False).encode("utf-8")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            label="Export to CSV",
            data=csv_data,
            file_name="audit_log.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with c2:
        if st.button("Upload CSV to Google Drive", use_container_width=True):
            with st.spinner("Uploading..."):
                link = upload_file_to_gdrive(
                    file_bytes=csv_data,
                    file_name="audit_log_backup.csv",
                    mime_type="text/csv",
                )
                if link:
                    st.success("Uploaded to Google Drive.")
                    st.markdown("[Open in Drive](" + link + ")")
                else:
                    st.error("Drive upload failed. Check Drive credentials.")


def _normalize_tx_type(t):
    if t == "IN":
        return "STOCK IN"
    if t == "OUT":
        return "STOCK OUT"
    return t


def _extract_destination(notes):
    return _extract_field(notes, "Destination")


def _extract_requested_by(notes):
    return _extract_field(notes, "Requested by")


def _extract_supplier(notes):
    return _extract_field(notes, "Supplier")
