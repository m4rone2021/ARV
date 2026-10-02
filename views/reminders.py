from datetime import date, datetime

import pandas as pd
import streamlit as st

from database import sb


def calculate_days_left(due_date_str):
    """Return (days_left_int, display_string)."""
    if not due_date_str:
        return 9999, "No Date"
    try:
        due_dt = datetime.strptime(str(due_date_str).strip(), "%Y-%m-%d").date()
        today = date.today()
        diff = (due_dt - today).days
        if diff < 0:
            return diff, f"🔴 OVERDUE ({abs(diff)}d ago)"
        elif diff == 0:
            return diff, "🟠 DUE TODAY"
        elif diff == 1:
            return diff, "🟡 1 day left"
        else:
            return diff, f"🟢 {diff} days left"
    except Exception:
        return 9999, "Invalid Date"


def render_reminders(user_name: str = "", user_role: str = ""):
    st.title("📝 Reminders & Tasks")

    active_user = user_name or st.session_state.get("user_name", "User")
    active_role = user_role or st.session_state.get("user_role", "User")

    is_admin = active_role.lower() in ["admin", "manager"]

    if is_admin:
        st.caption(f"👑 **Admin Mode** ({active_user}): Viewing and managing **all** site tasks.")
    else:
        st.caption(f"👤 **User Mode** ({active_user}): Viewing tasks assigned specifically to you.")

    tab_tasks, tab_add = st.tabs(["📋 Task List", "➕ Create Task / Reminder"])

    # ================================================================
    # TAB 1: TASK LIST
    # ================================================================
    with tab_tasks:
        try:
            query = (
                sb()
                .table("reminders")
                .select("id, due_date, task, assigned_to, status, priority")
            )
            if not is_admin:
                query = query.ilike("assigned_to", active_user.strip())
            res = query.execute()
            df = pd.DataFrame(res.data or [])
        except Exception as e:
            st.error(f"Error loading tasks: {e}")
            return

        if df.empty:
            if is_admin:
                st.info("No task reminders registered in the system.")
            else:
                st.info("No task reminders recorded for your user account.")
            return

        parsed = df["due_date"].apply(calculate_days_left)
        df["days_left_num"] = [d[0] for d in parsed]
        df["days_left_str"] = [d[1] for d in parsed]

        open_df = df[df["status"].isin(["OPEN", "PENDING"])].copy()
        closed_df = df[df["status"].isin(["COMPLETED", "CANCELLED"])].copy()

        view_mode = st.radio(
            "Display Format",
            ["📱 Cards (Mobile Friendly)", "📊 Full Data Table"],
            horizontal=True,
            key="tasks_view_mode",
        )

        st.divider()

        # ---- OPEN ----
        st.subheader("🟡 Open & Pending Tasks")
        if not open_df.empty:
            open_df = open_df.sort_values(by=["days_left_num", "priority"], ascending=[True, False])

            if view_mode == "📱 Cards (Mobile Friendly)":
                for _, row in open_df.iterrows():
                    p_tag = "🚨" if row["priority"] == "HIGH" else "🔹"
                    with st.expander(f"{p_tag} #{str(row['id'])[:8]} - {row['task']} ({row['days_left_str']})"):
                        st.write(f"**Due Date:** `{row['due_date']}`")
                        st.write(f"**Assigned To:** {row['assigned_to']}")
                        st.write(f"**Priority:** {'🚨 HIGH' if row['priority'] == 'HIGH' else 'NORMAL'}")
                        st.write(f"**Status:** `{row['status']}`")
            else:
                display_df = open_df[["id", "due_date", "days_left_str", "priority", "task", "assigned_to", "status"]].rename(
                    columns={
                        "id": "ID", "due_date": "Due Date", "days_left_str": "Days Left",
                        "priority": "Priority", "task": "Task Description",
                        "assigned_to": "Assigned To", "status": "Status",
                    }
                )
                st.dataframe(display_df, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.markdown("#### 🔄 Update Task Status / Schedule")

            with st.form("update_open_task_form", clear_on_submit=False):
                task_options = {
                    f"#{str(row['id'])[:8]} [{row['priority']}] - {row['task']} ({row['days_left_str']})": row["id"]
                    for _, row in open_df.iterrows()
                }
                selected_label = st.selectbox("Select Task to Update*", list(task_options.keys()))
                action_type = st.selectbox(
                    "Action*",
                    [
                        "MARK COMPLETED",
                        "MOVE DUE DATE (RESCHEDULE)",
                        "SET AS HIGH PRIORITY",
                        "SET AS NORMAL PRIORITY",
                        "MARK PENDING",
                        "CANCEL TASK",
                    ],
                )
                new_due_date = st.date_input("Select New Target Date (If Rescheduling)", value=date.today())

                submit_update = st.form_submit_button("💾 Submit Update", use_container_width=True)

                if submit_update and selected_label:
                    task_id = task_options[selected_label]
                    try:
                        if action_type == "MOVE DUE DATE (RESCHEDULE)":
                            sb().table("reminders").update(
                                {"due_date": str(new_due_date), "status": "OPEN"}
                            ).eq("id", task_id).execute()
                        elif action_type == "SET AS HIGH PRIORITY":
                            sb().table("reminders").update({"priority": "HIGH"}).eq("id", task_id).execute()
                        elif action_type == "SET AS NORMAL PRIORITY":
                            sb().table("reminders").update({"priority": "NORMAL"}).eq("id", task_id).execute()
                        elif action_type == "MARK COMPLETED":
                            sb().table("reminders").update({
                                "status": "COMPLETED",
                                "completed_at": datetime.utcnow().isoformat(),
                            }).eq("id", task_id).execute()
                        elif action_type == "MARK PENDING":
                            sb().table("reminders").update({"status": "PENDING"}).eq("id", task_id).execute()
                        elif action_type == "CANCEL TASK":
                            sb().table("reminders").update({"status": "CANCELLED"}).eq("id", task_id).execute()

                        st.success(f"Task #{str(task_id)[:8]} updated successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to update task: {e}")
        else:
            st.info(
                "No open tasks in the database." if is_admin
                else "No open or pending tasks assigned to you."
            )

        st.divider()

        # ---- CLOSED ----
        st.subheader("✅ Completed & Cancelled History")
        if not closed_df.empty:
            closed_df = closed_df.sort_values(by="due_date", ascending=False)

            if view_mode == "📱 Cards (Mobile Friendly)":
                for _, row in closed_df.iterrows():
                    status_flag = "🟢 COMPLETED" if row["status"] == "COMPLETED" else "⚪ CANCELLED"
                    with st.expander(f"#{str(row['id'])[:8]} - {row['task']} ({status_flag})"):
                        st.write(f"**Due Date:** `{row['due_date']}`")
                        st.write(f"**Assigned To:** {row['assigned_to']}")
                        st.write(f"**Status:** `{row['status']}`")
            else:
                display_df = closed_df[["id", "due_date", "task", "assigned_to", "status"]].rename(
                    columns={
                        "id": "ID", "due_date": "Due Date", "task": "Task Description",
                        "assigned_to": "Assigned To", "status": "Status",
                    }
                )
                st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.info("No completed or cancelled tasks found.")

    # ================================================================
    # TAB 2: CREATE NEW TASK
    # ================================================================
    with tab_add:
        st.subheader("Create New Task or Reminder")

        with st.form("add_reminder_form", clear_on_submit=True):
            task_desc = st.text_input("Task Description*", placeholder="e.g., Weekly Fuel Reserve Audit")
            due_date = st.date_input("Target Due Date*", value=date.today())
            assigned_to = st.text_input("Assigned Personnel / Team", value=active_user, placeholder="e.g., Warehouse Team")
            is_high_priority = st.checkbox("🚨 Mark as High Priority", value=False)

            submit_add = st.form_submit_button("💾 Save Task / Reminder", use_container_width=True)

            if submit_add:
                if not task_desc.strip():
                    st.error("⚠️ Task Description is required.")
                else:
                    try:
                        priority_val = "HIGH" if is_high_priority else "NORMAL"
                        sb().table("reminders").insert({
                            "due_date": str(due_date),
                            "task": task_desc.strip(),
                            "assigned_to": assigned_to.strip(),
                            "status": "OPEN",
                            "priority": priority_val,
                            "created_by": active_user,
                        }).execute()

                        st.success(f"Task assigned to **{assigned_to.strip()}**: **{task_desc.strip()}**")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save task: {e}")
