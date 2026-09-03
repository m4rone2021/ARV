# views/audit_log.py
import pandas as pd
import streamlit as st
from database import get_db, init_db

def render_audit_log(user_name, user_role):
    st.title("📜 Audit Log & Transaction History")
    st.caption("Track all stock-in, stock-out, and system operations.")

    init_db()

    # Filter controls
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        type_filter = st.selectbox("Filter by Type", ["All", "STOCK IN", "STOCK OUT"])
    
    with col2:
        search_query = st.text_input("Search Item or Handler", placeholder="Type to search...")
        
    with col3:
        st.write("") # Spacing
        st.write("")
        refresh_btn = st.button("🔄 Refresh", use_container_width=True)

    try:
        with get_db() as conn:
            query = "SELECT id, timestamp, type, item_name, quantity, unit, handled_by, notes FROM transactions WHERE 1=1"
            params = []

            if type_filter != "All":
                query += " AND type = ?"
                params.append(type_filter)

            if search_query.strip():
                query += " AND (item_name LIKE ? OR handled_by LIKE ? OR notes LIKE ?)"
                wildcard = f"%{search_query.strip()}%"
                params.extend([wildcard, wildcard, wildcard])

            query += " ORDER BY id DESC"

            df = pd.read_sql_query(query, conn, params=params)

        if not df.empty:
            df_display = df.rename(columns={
                "id": "Trans ID",
                "timestamp": "Date & Time",
                "type": "Type",
                "item_name": "Item Name",
                "quantity": "Quantity",
                "unit": "Unit",
                "handled_by": "Handled By",
                "notes": "Notes / Remarks"
            })

            # Metrics Summary
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Transactions Logged", len(df))
            m2.metric("Stock In Logs", len(df[df["Type"] == "STOCK IN"]))
            m3.metric("Stock Out Logs", len(df[df["Type"] == "STOCK OUT"]))

            st.divider()
            st.dataframe(df_display, use_container_width=True, hide_index=True)

            # Export Option
            csv_data = df_display.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export Audit Log to CSV",
                data=csv_data,
                file_name="audit_log.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.info("No transaction logs found matching the selected filters.")

    except Exception as e:
        st.error(f"Error loading audit log: {e}")
