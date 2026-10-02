import io
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from database import UPLOAD_DIR, sb, upload_file_to_gdrive


def extract_drive_link(notes_str: str) -> str:
    if not isinstance(notes_str, str):
        return ""
    match = re.search(r"(?:Drive Link|Attachment):\s*(https?://[^\s|]+)", notes_str)
    return match.group(1) if match else ""


def extract_attachment_filename(notes_str: str) -> str:
    if not isinstance(notes_str, str):
        return ""
    match = re.search(r"Attachment:\s*([^\s|]+)", notes_str)
    if match and not match.group(1).startswith("http"):
        return match.group(1)
    return ""


def upload_csv_to_gdrive(csv_bytes: bytes, filename: str = "audit_log.csv"):
    """Upload a CSV to Google Drive (uses same DB-less Drive path as stock_in)."""
    try:
        link = upload_file_to_gdrive(
            file_bytes=csv_bytes,
            file_name=filename,
            mime_type="text/csv",
        )
        return link
    except Exception as e:
        st.error(f"Failed to sync with Google Drive: {e}")
        return None


def render_audit_log(user_name: str, user_role: str):
    st.title("📜 Complete Audit Log")
    st.caption("Track stock movement, deliveries, physical logs, user activity, and attachments.")

    # ---- Filters ----
    with st.expander("🔍 Search & Filter Controls", expanded=True):
        search_query = st.text_input(
            "Search Item, Handler, or Notes",
            placeholder="Type keyword...",
            key="mobile_search",
        )
        type_filter = st.selectbox(
            "Filter by Category / Log Type",
            [
                "All Activity",
                "STOCK IN",
                "STOCK OUT",
                "SCHEDULED DELIVERY",
                "PHYSICAL INVENTORY",
                "USER LOG",
            ],
            key="mobile_type",
        )
        st.button("🔄 Refresh Data", width='stretch')

    # ---- Fetch each source table separately, then merge ----
    frames = []

    # 1. transactions
    try:
        res = (
            sb()
            .table("transactions")
            .select("id, timestamp, type, item_name, quantity, unit, handled_by, notes")
            .order("timestamp", desc=True)
            .limit(500)
            .execute()
        )
        if res.data:
            df = pd.DataFrame(res.data)
            df["type"] = df["type"].apply(
                lambda t: "STOCK IN" if t == "IN"
                else "STOCK OUT" if t == "OUT"
                else t
            )
            frames.append(df)
    except Exception as e:
        st.warning(f"Could not load transactions: {e}")

    # 2. deliveries (as scheduled delivery)
    try:
        res = (
            sb()
            .table("deliveries")
            .select("id, created_at, item_name, expected_quantity, unit, created_by, status, notes")
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
            })
            df["type"] = "SCHEDULED DELIVERY"
            df["notes"] = df.apply(
                lambda r: f"{r.get('status', '')} | {r.get('notes') or ''}", axis=1
            )
            frames.append(df[["id", "timestamp", "type", "item_name", "quantity", "unit", "handled_by", "notes"]])
    except Exception as e:
        st.warning(f"Could not load deliveries: {e}")

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
            df["notes"] = df.apply(
                lambda r: (
                    f"System Qty: {r['system_qty']} | Variance: {r['variance']} | "
                    f"{r.get('notes') or ''}"
                ),
                axis=1,
            )
            frames.append(df[["id", "timestamp", "type", "item_name", "quantity", "unit", "handled_by", "notes"]])
    except Exception as e:
        st.warning(f"Could not load physical inventory logs: {e}")

    # 4. user_logs (currently empty, but supported)
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
            frames.append(df[["id", "timestamp", "type", "item_name", "quantity", "unit", "handled_by", "notes"]])
    except Exception as e:
        st.warning(f"Could not load user logs: {e}")

    # ---- Merge ----
    if not frames:
        st.info("No audit logs found matching the selected filters.")
        return

    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.sort_values("timestamp", ascending=False).reset_index(drop=True)

    # ---- Apply filters ----
    if type_filter == "STOCK IN":
        df = df[df["type"].isin(["STOCK IN", "IN"])]
    elif type_filter == "STOCK OUT":
        df = df[df["type"].isin(["STOCK OUT", "OUT"])]
    elif type_filter != "All Activity":
        df = df[df["type"] == type_filter]

    if search_query.strip():
        q = search_query.strip().lower()
        mask = (
            df["item_name"].astype(str).str.lower().str.contains(q, na=False)
            | df["handled_by"].astype(str).str.lower().str.contains(q, na=False)
            | df["notes"].astype(str).str.lower().str.contains(q, na=False)
            | df["type"].astype(str).str.lower().str.contains(q, na=False)
        )
        df = df[mask]

    if df.empty:
        st.info("No audit logs found matching the selected filters.")
        return

    # ---- KPI metrics ----
    in_count = len(df[df["type"].isin(["STOCK IN", "IN"])])
    out_count = len(df[df["type"].isin(["STOCK OUT", "OUT"])])
    delivery_count = len(df[df["type"] == "SCHEDULED DELIVERY"])
    physical_count = len(df[df["type"] == "PHYSICAL INVENTORY"])
    user_count = len(df[df["type"] == "USER LOG"])

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Logs", len(df))
    m2.metric("Stock IN", in_count)
    m3.metric("Stock OUT", out_count)
    m4.metric("Deliveries", delivery_count)
    m5.metric("User / Physical", user_count + physical_count)

    df_display = df.rename(columns={
        "id": "Log ID",
        "timestamp": "Date & Time",
        "type": "Log Type",
        "item_name": "Item Name",
        "quantity": "Quantity",
        "unit": "Unit",
        "handled_by": "Handled / Executed By",
        "notes": "Notes / Details / Audit Ref",
    })

    st.divider()
    st.dataframe(df_display, width='stretch', hide_index=True)

    # ---- Attachments ----
    with st.expander("📎 Attachments & Drive Links"):
        has_media = False
        for _, row in df.iterrows():
            notes = str(row["notes"])
            drive_url = extract_drive_link(notes)
            local_file = extract_attachment_filename(notes)

            if drive_url:
                has_media = True
                st.markdown(
                    f"🔗 **Log #{str(row['id'])[:8]} ({row['type']} - {row['item_name']})**  \n"
                    f"[Open Document]({drive_url})"
                )
                st.divider()
            elif local_file:
                has_media = True
                file_path = Path(UPLOAD_DIR) / local_file
                if file_path.exists():
                    with open(file_path, "rb") as f:
                        st.download_button(
                            label=f"📄 Download #{str(row['id'])[:8]}: {local_file}",
                            data=f.read(),
                            file_name=local_file,
                            key=f"audit_dl_{row['id']}",
                            width='stretch',
                        )
                else:
                    st.caption(f"⚠️ Log local file `{local_file}` not found on disk.")

        if not has_media:
            st.info("No external file links or attachments found in records.")

    # ---- Export ----
    st.divider()
    csv_data = df_display.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Export Audit Log (CSV)",
        data=csv_data,
        file_name="audit_log.csv",
        mime="text/csv",
        width='stretch',
    )

    if st.button("☁️ Sync Audit Log to Google Drive", width='stretch'):
        with st.spinner("Uploading to Google Drive..."):
            link = upload_csv_to_gdrive(csv_data, filename="audit_log_backup.csv")
            if link:
                st.success("Successfully uploaded to Google Drive!")
                st.markdown(f"🔗 [Open Uploaded File in Drive]({link})")
            else:
                st.error("Upload failed — check Drive credentials.")
