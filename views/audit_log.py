# views/audit_log.py
import os
import pandas as pd
import streamlit as st
from datetime import datetime
from database import get_db

def render_audit_log():
    st.title("📜 Master Audit & Transaction Ledger")
    st.caption("Complete, immutable history of stock receipts, material issuances, and manual adjustments.")

    with get_db() as conn:
        df_all_tx = pd.read_sql_query("SELECT * FROM transactions ORDER BY id DESC", conn)

    if df_all_tx.empty:
        st.info("Audit log is currently empty. No transactions recorded yet.")
        return

    # Filter & Search Controls
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        search_query = st.text_input("🔍 Search Keyword (Item, User, Destination, DR, Remarks)", "")
    with col_f2:
        type_filter = st.multiselect(
            "Filter Transaction Type", 
            options=["IN", "OUT", "ADJUSTMENT"], 
            default=["IN", "OUT", "ADJUSTMENT"]
        )

    # Filter logic
    filtered_df = df_all_tx[df_all_tx['type'].isin(type_filter)]

    if search_query.strip():
        query = search_query.lower().strip()
        filtered_df = filtered_df[
            filtered_df['item_name'].str.lower().str.contains(query, na=False) |
            filtered_df['user_name'].str.lower().str.contains(query, na=False) |
            filtered_df['project_name'].str.lower().str.contains(query, na=False) |
            filtered_df['remarks'].str.lower().str.contains(query, na=False) |
            filtered_df['driver_details'].str.lower().str.contains(query, na=False)
        ]

    st.dataframe(filtered_df, use_container_width=True, hide_index=True)

    # CSV Export Button
    csv_data = filtered_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Export Filtered Ledger as CSV",
        data=csv_data,
        file_name=f"audit_log_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv"
    )

    st.divider()
    st.markdown("##### 🖼️ Attached Proof Photos Viewer")
    
    # Filter transactions containing a recorded photo path
    has_photo = filtered_df[filtered_df['photo_path'].str.strip() != ""]
    
    if not has_photo.empty:
        photo_options = {}
        for _, row in has_photo.iterrows():
            label = f"Tx #{row['id']} | {row['timestamp']} | {row['item_name']} ({row['type']})"
            photo_options[label] = row['photo_path']

        selected_label = st.selectbox("Select Transaction to View Attached Proof", list(photo_options.keys()))
        img_path = photo_options[selected_label]

        if os.path.exists(img_path):
            st.image(img_path, caption=f"Proof Attachment: {selected_label}", width=450)
        else:
            st.warning("⚠️ Photo file record exists in database, but the image file was not found on disk.")
    else:
        st.info("No photo attachments found in the current filtered transaction set.")
