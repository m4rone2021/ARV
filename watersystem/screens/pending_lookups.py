"""Admin-only: approve or reject pending lookup requests."""
import streamlit as st

from database import ARVError
from watersystem import lookups


def render(user_name: str):
    st.title("⚙️ Pending Lookup Requests")
    st.caption(
        "Users can request new categories, materials, and sizes. "
        "Approved values become available in all dropdowns."
    )

    try:
        pending = lookups.list_pending()
    except ARVError as e:
        st.error(f"⚠️ {e}")
        return

    if not pending:
        st.info("No pending requests. 🎉")
        return

    st.caption(f"{len(pending)} pending request(s).")

    for row in pending:
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 4])

            with c1:
                st.markdown(f"**{row['kind'].title()}:** `{row['value']}`")
                st.caption(
                    f"Requested by {row.get('created_by') or 'unknown'} "
                    f"on {str(row.get('created_at',''))[:19]}"
                )

            with c2:
                approve_clicked = st.button(
                    "✅ Approve", key=f"appr_{row['id']}", width="stretch",
                )

            with c3:
                with st.expander("❌ Reject"):
                    reason = st.text_input(
                        "Rejection reason", key=f"rej_reason_{row['id']}",
                    )
                    reject_clicked = st.button(
                        "Confirm rejection",
                        key=f"rej_{row['id']}",
                        width="stretch",
                    )

            if approve_clicked:
                try:
                    lookups.approve(row["id"], user_name)
                    st.success(f"Approved `{row['value']}`.")
                    st.rerun()
                except ARVError as e:
                    st.error(f"⚠️ {e}")

            if reject_clicked:
                try:
                    lookups.reject(row["id"], reason, user_name)
                    st.success(f"Rejected `{row['value']}`.")
                    st.rerun()
                except ValueError as e:
                    st.error(f"⚠️ {e}")
                except ARVError as e:
                    st.error(f"⚠️ {e}")