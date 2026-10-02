from datetime import date, datetime

import pandas as pd
import streamlit as st

from database import sb


def get_due_status_label(scheduled_date_str):
    """Return a human-friendly due-date label."""
    if not scheduled_date_str:
        return "No Date Set"
    try:
        if isinstance(scheduled_date_str, (datetime, date)):
            target = (
                scheduled_date_str.date()
                if isinstance(scheduled_date_str, datetime)
                else scheduled_date_str
            )
        else:
            target = datetime.strptime(str(scheduled_date_str).split()[0], "%Y-%m-%d").date()
        today = date.today()
        days_left = (target - today).days
        if days_left == 0:
            return "📅 Due Today"
        elif days_left < 0:
            return f"⚠️ Overdue ({abs(days_left)} days)"
        else:
            return f"⏳ In {days_left} days"
    except Exception:
        return f"📅 {scheduled_date_str}"


def add_item_to_dispatch(dispatch_id, item_name, unit, quantity, notes, first_row, user_name=None):
    """Insert one item into an existing dispatch batch + reserve stock."""
    try:
        scheduled_date = first_row.get("scheduled_date") or first_row.get("expected_date")
        destination = first_row.get("destination") or ""
        requested_by = first_row.get("requested_by") or ""
        project = first_row.get("project") or ""
        status = first_row.get("status") or "Pending"
        is_priority = bool(first_row.get("is_priority", False))
        driver_name = first_row.get("driver_name") or ""
        created_by = user_name or first_row.get("created_by") or requested_by

        sb().table("deliveries").insert({
            "dispatch_id": dispatch_id,
            "item_name": item_name,
            "unit": unit,
            "expected_quantity": float(quantity),
            "expected_date": str(scheduled_date),
            "scheduled_date": str(scheduled_date),
            "destination": destination,
            "requested_by": requested_by,
            "project": project,
            "status": status,
            "is_priority": is_priority,
            "driver_name": driver_name,
            "notes": notes,
            "created_by": created_by,
        }).execute()

        # Reserve stock
        cur = sb().table("master_items").select("reserved_stock").eq("item_name", item_name).limit(1).execute()
        if cur.data:
            new_reserved = float(cur.data[0].get("reserved_stock") or 0.0) + float(quantity)
            sb().table("master_items").update({"reserved_stock": new_reserved}).eq("item_name", item_name).execute()

        st.toast(f"Added {item_name} to dispatch batch!", icon="✅")
        st.rerun()
    except Exception as e:
        st.error(f"Error adding item to dispatch: {e}")


def update_dispatch_status(dispatch_id, new_status, driver_name=None, delivery_notes=None):
    """Update all items in a dispatch batch + handle stock on Completed/Cancelled."""
    try:
        rows = (
            sb()
            .table("deliveries")
            .select("item_name, expected_quantity")
            .eq("dispatch_id", dispatch_id)
            .execute()
            .data
            or []
        )

        for item in rows:
            item_name = item["item_name"]
            qty = float(item["expected_quantity"])

            cur = (
                sb()
                .table("master_items")
                .select("current_stock, reserved_stock")
                .eq("item_name", item_name)
                .limit(1)
                .execute()
            )
            if not cur.data:
                continue
            stock = cur.data[0]
            current_stock = float(stock.get("current_stock") or 0.0)
            reserved_stock = float(stock.get("reserved_stock") or 0.0)

            if new_status == "Completed":
                new_cs = max(0.0, current_stock - qty)
                new_rs = max(0.0, reserved_stock - qty)
                sb().table("master_items").update(
                    {"current_stock": new_cs, "reserved_stock": new_rs}
                ).eq("item_name", item_name).execute()

                sb().table("transactions").insert({
                    "type": "OUT",
                    "item_name": item_name,
                    "quantity": qty,
                    "unit": item.get("unit", "pcs"),
                    "handled_by": "System",
                    "notes": f"Completed Dispatch #{dispatch_id}",
                }).execute()

            elif new_status == "Cancelled":
                new_rs = max(0.0, reserved_stock - qty)
                sb().table("master_items").update(
                    {"reserved_stock": new_rs}
                ).eq("item_name", item_name).execute()

        update_payload = {"status": new_status}
        if driver_name:
            update_payload["driver_name"] = driver_name
        if delivery_notes:
            update_payload["notes"] = delivery_notes

        sb().table("deliveries").update(update_payload).eq("dispatch_id", dispatch_id).execute()

        st.toast(f"Dispatch {dispatch_id} marked as {new_status}!", icon="🚚")
        st.rerun()
    except Exception as e:
        st.error(f"Error updating status: {e}")


def update_dispatch_schedule_date(dispatch_id, new_date):
    """Reschedule the delivery date for the whole dispatch."""
    try:
        sb().table("deliveries").update(
            {"expected_date": str(new_date), "scheduled_date": str(new_date)}
        ).eq("dispatch_id", dispatch_id).execute()
        st.toast(f"Dispatch {dispatch_id} rescheduled to {new_date}", icon="📅")
        st.rerun()
    except Exception as e:
        st.error(f"Error updating schedule date: {e}")


def update_dispatch_item_quantity(dispatch_id, item_name, action, change_qty, notes):
    """Adjust a single batch item's qty and keep reserved_stock in sync."""
    try:
        rows = (
            sb()
            .table("deliveries")
            .select("id, expected_quantity")
            .eq("dispatch_id", dispatch_id)
            .eq("item_name", item_name)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not rows:
            st.error("Selected item not found in dispatch batch.")
            return

        row = rows[0]
        current_qty = float(row["expected_quantity"])

        if action == "Increase Batch":
            qty_delta = change_qty
            new_qty = current_qty + change_qty
        else:
            qty_delta = -min(current_qty, change_qty)
            new_qty = max(0.0, current_qty - change_qty)

        if new_qty == 0:
            sb().table("deliveries").delete().eq("id", row["id"]).execute()
        else:
            payload = {"expected_quantity": new_qty}
            if notes:
                payload["notes"] = notes.strip()
            sb().table("deliveries").update(payload).eq("id", row["id"]).execute()

        # Adjust reserved stock
        cur = (
            sb()
            .table("master_items")
            .select("reserved_stock")
            .eq("item_name", item_name)
            .limit(1)
            .execute()
        )
        if cur.data:
            new_reserved = max(
                0.0, float(cur.data[0].get("reserved_stock") or 0.0) + qty_delta
            )
            sb().table("master_items").update(
                {"reserved_stock": new_reserved}
            ).eq("item_name", item_name).execute()

        st.toast(f"Updated {item_name} batch quantity to {new_qty:.2f}", icon="✅")
        st.rerun()
    except Exception as e:
        st.error(f"Error modifying dispatch item: {e}")


def remove_item_from_dispatch(dispatch_id, item_name, qty):
    """Remove a batch item and release its reserved stock."""
    try:
        sb().table("deliveries").delete().eq("dispatch_id", dispatch_id).eq("item_name", item_name).execute()

        cur = (
            sb()
            .table("master_items")
            .select("reserved_stock")
            .eq("item_name", item_name)
            .limit(1)
            .execute()
        )
        if cur.data:
            new_reserved = max(0.0, float(cur.data[0].get("reserved_stock") or 0.0) - qty)
            sb().table("master_items").update(
                {"reserved_stock": new_reserved}
            ).eq("item_name", item_name).execute()

        st.toast(f"Removed {item_name} from dispatch batch.", icon="🗑️")
        st.rerun()
    except Exception as e:
        st.error(f"Error removing item: {e}")


def render_dispatch_card(dispatch_id, items_df, get_due_status_label_fn, add_item_to_dispatch_fn):
    """Render one unified dispatch card."""

    def fetch_latest_items_df(d_id):
        res = (
            sb()
            .table("deliveries")
            .select("id, dispatch_id, item_name, unit, expected_quantity, notes, status, "
                    "destination, expected_date, scheduled_date, requested_by, project, "
                    "is_priority, driver_name, created_by, created_at")
            .eq("dispatch_id", d_id)
            .execute()
        )
        df = pd.DataFrame(res.data or [])
        if not df.empty:
            df = df.rename(columns={
                "expected_quantity": "quantity",
                "expected_date": "scheduled_date",
            })
        return df

    current_items_df = (
        fetch_latest_items_df(dispatch_id)
        if items_df is None or items_df.empty
        else items_df.copy()
    )

    if current_items_df.empty:
        st.warning(f"No records found for Dispatch #{dispatch_id}")
        return

    first_row = current_items_df.iloc[0]

    prio_badge = "🔥 HIGH PRIORITY | " if first_row.get("is_priority") else ""
    req_info = f"Requested by: {first_row.get('requested_by') or 'N/A'}"
    project_info = f" | Project: {first_row.get('project')}" if first_row.get("project") else ""

    due_status = get_due_status_label_fn(first_row.get("scheduled_date"))
    header_label = (
        f"{prio_badge}🚛 Dispatch #{dispatch_id} | {req_info}{project_info} "
        f"➔ {first_row.get('destination', 'N/A')} [{first_row.get('status')}] ({due_status})"
    )

    key_prefix = f"disp_{dispatch_id}"

    with st.expander(header_label, expanded=False):
        c1, c2, c3, c4 = st.columns(4)

        c1.markdown(f"**Dispatch ID:** `{dispatch_id}`")
        c1.markdown(f"**Requested By:** {first_row.get('requested_by') or 'N/A'}")
        c1.markdown(f"**Destination:** {first_row.get('destination', 'N/A')}")

        c2.markdown(f"**Project:** {first_row.get('project') or 'N/A'}")
        c2.markdown(f"**Total Items:** `{len(current_items_df)}`")

        c3.markdown(f"**Created:** `{first_row.get('created_at', 'N/A')}`")
        c3.markdown(f"**Scheduled:** `{first_row.get('scheduled_date', 'N/A')}`")

        c4.markdown(f"**Priority:** {'🔴 HIGH' if first_row.get('is_priority') else '🟢 Normal'}")
        c4.markdown(f"**Status:** `{first_row.get('status')}`")

        if first_row.get("driver_name"):
            st.markdown(f"🚛 **Assigned Driver:** {first_row['driver_name']}")

        st.divider()

        st.markdown("##### ⚙️ Dispatch Management & Reschedule")
        ctl_col1, ctl_col2, ctl_col3 = st.columns(3)

        with ctl_col1:
            status_options = ["Pending", "In Transit", "Completed", "Cancelled"]
            current_status = first_row.get("status") or "Pending"
            idx = status_options.index(current_status) if current_status in status_options else 0
            selected_status = st.selectbox(
                "Update Dispatch Status",
                options=status_options,
                index=idx,
                key=f"status_sel_{key_prefix}",
            )

        with ctl_col2:
            try:
                curr_date = datetime.strptime(
                    str(first_row.get("scheduled_date")).split()[0], "%Y-%m-%d"
                ).date()
            except Exception:
                curr_date = date.today()
            new_scheduled_date = st.date_input(
                "Reschedule Delivery Date", value=curr_date, key=f"date_input_{key_prefix}"
            )

        with ctl_col3:
            input_driver = st.text_input(
                "Assigned Driver Name",
                value=first_row.get("driver_name") or "",
                key=f"driver_input_{key_prefix}",
            )

        input_notes = st.text_input(
            "Dispatch Delivery Notes",
            value=first_row.get("notes") or "",
            key=f"notes_input_{key_prefix}",
        )

        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button("🔄 Update Status & Driver Notes", key=f"btn_status_{key_prefix}", type="primary", width='stretch'):
                update_dispatch_status(dispatch_id, selected_status, input_driver, input_notes)

        with btn_c2:
            if str(new_scheduled_date) != str(curr_date):
                if st.button("📅 Save Rescheduled Date", key=f"btn_date_{key_prefix}", width='stretch'):
                    update_dispatch_schedule_date(dispatch_id, new_scheduled_date)

        st.divider()

        items_in_batch = current_items_df["item_name"].unique().tolist()
        if items_in_batch:
            st.markdown("##### ➕ Modify Batch Item Quantities")
            mod_col1, mod_col2 = st.columns(2)
            with mod_col1:
                target_item = st.selectbox("Select Batch Item", options=items_in_batch, key=f"sel_item_{key_prefix}")
                action_type = st.radio("Action", ["Increase Batch", "Decrease Batch"], key=f"act_item_{key_prefix}")
            with mod_col2:
                change_q = st.number_input("Quantity Change", min_value=0.01, value=1.0, step=1.0, key=f"qty_item_{key_prefix}")
                mod_notes = st.text_input("Item Notes", placeholder="Optional", key=f"item_notes_{key_prefix}")

            if st.button("💾 Apply Quantity Adjustment", key=f"btn_qty_{key_prefix}"):
                update_dispatch_item_quantity(dispatch_id, target_item, action_type, change_q, mod_notes)

        st.divider()

        st.markdown("##### 📦 Current Batch Items To Be Dispatched")
        for idx2, row in current_items_df.iterrows():
            item_col1, item_col2, item_col3, item_col4 = st.columns([3, 2, 3, 1])
            item_col1.markdown(f"**{row['item_name']}**")
            item_col2.markdown(f"`{float(row['quantity']):.2f} {row['unit']}`")
            item_col3.markdown(f"_{row.get('notes') or 'No notes'}_")
            if item_col4.button("🗑️", key=f"del_{dispatch_id}_{row['item_name']}"):
                remove_item_from_dispatch(dispatch_id, row["item_name"], float(row["quantity"]))
