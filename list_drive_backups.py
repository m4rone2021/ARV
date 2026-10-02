import streamlit as st
from database import get_drive_service

svc, kind = get_drive_service()
print(f"[auth] using: {kind}")

folder_id = None
try:
    folder_id = st.secrets.get("google_drive", {}).get("folder_id", None)
except Exception:
    pass

if folder_id:
    q = f"'{folder_id}' in parents and name contains 'inventory_backup_' and trashed = false"
else:
    q = "name contains 'inventory_backup_' and trashed = false"

res = svc.files().list(
    q=q,
    orderBy="createdTime desc",
    pageSize=20,
    fields="files(id,name,size,createdTime)",
).execute()

files = res.get("files", [])
if not files:
    print("[!] No inventory_backup_*.db files found.")
else:
    print(f"[ok] Found {len(files)} backup(s):\n")
    for f in files:
        size_mb = int(f.get("size", 0)) / (1024 * 1024)
        print(f"  {f['name']}")
        print(f"    size:   {size_mb:.2f} MB")
        print(f"    date:   {f['createdTime']}")
        print(f"    id:     {f['id']}")
        print()
