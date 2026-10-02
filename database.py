"""
ARV database.py — Supabase (Postgres) data layer.

Public API preserved so views keep working. Critical stock movements call
Postgres RPC functions for atomicity. Google Drive is kept ONLY for file
attachments.

Session 1 changes:
- Custom exception types (AuthError, ConfigError, NetworkError, etc.)
- Supabase client with timeout
- Input validation on register_item
- Verified updates on change_password / add_stock_transaction
- Replaced deprecated datetime.utcnow()
- Removed dead code (backup_db_to_gdrive, get_db, unused imports)
"""

import io
import os
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
import streamlit as st

# -----------------------------------------------------------------------------
# EXCEPTIONS
# -----------------------------------------------------------------------------
class ARVError(Exception):
    """Base class for all ARV-specific errors."""


class AuthError(ARVError):
    """Invalid credentials or inactive account."""


class ConfigError(ARVError):
    """Missing or invalid configuration (e.g., secrets)."""


class NetworkError(ARVError):
    """Supabase could not be reached."""


class ItemExistsError(ARVError):
    """Item with the same name already exists."""


class UpdateFailedError(ARVError):
    """An update affected zero rows or the response was unexpected."""


# -----------------------------------------------------------------------------
# SUPABASE CLIENT
# -----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _sb_client():
    """Create and cache the Supabase client. Runs once per session."""
    try:
        from supabase import create_client
    except ImportError:
        raise ConfigError(
            "Missing 'supabase' package. Run: python -m pip install supabase"
        )

    cfg = st.secrets.get("supabase", {})
    url = cfg.get("url")
    key = cfg.get("service_role_key")
    if not url or not key:
        raise ConfigError(
            "Missing [supabase] url / service_role_key in .streamlit/secrets.toml"
        )

    try:
        return create_client(url, key)
    except Exception as e:
        raise ConfigError(f"Failed to initialize Supabase client: {e}") from e


def sb():
    """Return the cached Supabase client."""
    return _sb_client()


def _now_iso() -> str:
    """Return current UTC time as ISO string (timezone-aware)."""
    return datetime.now(timezone.utc).isoformat()


# -----------------------------------------------------------------------------
# PATHS (legacy shims kept for compat)
# -----------------------------------------------------------------------------
LOCAL_WIN_DIR = Path(r"D:\Inventory System Files")
if LOCAL_WIN_DIR.exists():
    DATA_DIR = LOCAL_WIN_DIR
else:
    DATA_DIR = Path("./data")
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

DB_FILE = DATA_DIR / "inventory.db"  # no longer used
UPLOAD_DIR = DATA_DIR / "uploads"
try:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass


# -----------------------------------------------------------------------------
# PASSWORD HASHING (bcrypt)
# -----------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Return a bcrypt hash for the given password."""
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=12)
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plaintext password against a bcrypt hash.

    Logs (but does not raise) if the hash is malformed.
    """
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except Exception as e:
        print(f"[verify_password] bcrypt check failed: {e}")
        return False


# -----------------------------------------------------------------------------
# AUTH
# -----------------------------------------------------------------------------
def login_user(username: str, password: str) -> dict:
    """Authenticate a user.

    Returns dict with username/role/must_change_password on success.
    Raises AuthError on invalid credentials.
    Raises NetworkError if Supabase can't be reached.
    Raises ConfigError if the client can't be created.
    """
    username = username.strip()
    try:
        res = (
            sb()
            .table("users")
            .select("username, role, password_hash, is_active, must_change_password")
            .eq("username", username)
            .limit(1)
            .execute()
        )
    except ConfigError:
        raise
    except Exception as e:
        msg = str(e).lower()
        if "timeout" in msg or "connection" in msg or "network" in msg:
            raise NetworkError(f"Cannot reach database: {e}") from e
        raise NetworkError(f"Database error during login: {e}") from e

    rows = res.data or []
    if not rows:
        raise AuthError("Invalid username or password.")

    user = rows[0]
    if not user.get("is_active", True):
        raise AuthError("This account is disabled. Contact an administrator.")

    if not verify_password(password, user["password_hash"]):
        raise AuthError("Invalid username or password.")

    # Best-effort last login update
    try:
        sb().table("users").update(
            {"last_login_at": _now_iso()}
        ).eq("username", user["username"]).execute()
    except Exception as e:
        print(f"[login_user] last_login_at update failed: {e}")

    return {
        "username": user["username"],
        "role": user["role"],
        "must_change_password": bool(user.get("must_change_password", False)),
    }


def change_password(username: str, new_password: str) -> None:
    """Change a user's password and clear must_change_password.

    Raises UpdateFailedError if the update did not affect a row.
    """
    if not new_password or len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if not any(c.isalpha() for c in new_password):
        raise ValueError("Password must contain at least one letter.")
    if not any(c.isdigit() for c in new_password):
        raise ValueError("Password must contain at least one number.")

    new_hash = hash_password(new_password)
    try:
        res = (
            sb()
            .table("users")
            .update({
                "password_hash": new_hash,
                "must_change_password": False,
            })
            .eq("username", username)
            .execute()
        )
    except Exception as e:
        raise NetworkError(f"Failed to update password: {e}") from e

    if not res.data:
        raise UpdateFailedError(
            f"No user named '{username}' was updated. Contact support."
        )


def log_user_action(username: str, action: str, details: str = "") -> None:
    """Insert a user activity entry (best-effort, never raises)."""
    try:
        # Truncate untrusted input to keep the log clean
        safe_user = str(username).strip()[:100]
        safe_action = str(action).strip()[:50]
        safe_details = (str(details).strip()[:500]) if details else None
        sb().table("user_logs").insert({
            "username": safe_user,
            "action": safe_action,
            "details": safe_details,
        }).execute()
    except Exception as e:
        print(f"[user_logs] Failed to log {action} for {username}: {e}")


# -----------------------------------------------------------------------------
# INVENTORY WRITES
# -----------------------------------------------------------------------------
def register_item(
    item_name: str,
    category: str,
    unit: str,
    initial_stock: float = 0.0,
    min_threshold: float = 10.0,
    remarks: str = "",
) -> None:
    """Register a new item in master_items.

    Raises ValueError on invalid input.
    Raises ItemExistsError if the item already exists.
    """
    clean_name = (item_name or "").strip()
    clean_cat = (category or "").strip()
    clean_unit = (unit or "").strip()

    if not clean_name:
        raise ValueError("Item name is required.")
    if len(clean_name) > 200:
        raise ValueError("Item name must be 200 characters or fewer.")
    if not clean_cat:
        raise ValueError("Category is required.")
    if not clean_unit:
        raise ValueError("Unit is required.")
    if initial_stock < 0:
        raise ValueError("Initial stock cannot be negative.")
    if min_threshold < 0:
        raise ValueError("Minimum threshold cannot be negative.")

    # Pre-check for duplicate
    try:
        existing = (
            sb()
            .table("master_items")
            .select("item_name")
            .eq("item_name", clean_name)
            .limit(1)
            .execute()
        )
    except Exception as e:
        raise NetworkError(f"Failed to check existing items: {e}") from e

    if existing.data:
        raise ItemExistsError(f"An item named '{clean_name}' already exists.")

    try:
        sb().table("master_items").insert({
            "item_name": clean_name,
            "category": clean_cat,
            "unit": clean_unit,
            "current_stock": float(initial_stock),
            "reserved_stock": 0.0,
            "min_threshold": float(min_threshold),
            "remarks": (remarks or "").strip() or None,
        }).execute()
    except Exception as e:
        # Race: someone else inserted between check and insert
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            raise ItemExistsError(f"An item named '{clean_name}' already exists.")
        raise NetworkError(f"Failed to register item: {e}") from e


def add_stock_transaction(
    trans_type: str,
    item_name: str,
    quantity: float,
    unit: str,
    handled_by: str,
    notes: str = "",
    project_name: str | None = None,
) -> str:
    """Execute a stock transaction via the atomic RPC. Returns transaction ID.

    Raises ValueError on invalid arguments.
    Raises NetworkError on failure.
    """
    trans_type = (trans_type or "").upper().strip()
    if trans_type not in ("IN", "OUT", "ADJUSTMENT", "RECONCILIATION"):
        raise ValueError(
            "trans_type must be IN, OUT, ADJUSTMENT, or RECONCILIATION"
        )
    if not item_name or not str(item_name).strip():
        raise ValueError("Item name is required.")
    if quantity is None:
        raise ValueError("Quantity is required.")
    try:
        qty = float(quantity)
    except (TypeError, ValueError):
        raise ValueError("Quantity must be a number.")
    if qty <= 0 and trans_type != "ADJUSTMENT":
        raise ValueError("Quantity must be positive.")

    try:
        res = sb().rpc(
            "record_stock_transaction",
            {
                "p_type": trans_type,
                "p_item_name": str(item_name).strip(),
                "p_quantity": qty,
                "p_unit": (unit or "pcs").strip(),
                "p_handled_by": (handled_by or "System").strip(),
                "p_notes": (notes or "").strip() or None,
                "p_project_name": project_name,
            },
        ).execute()
    except Exception as e:
        msg = str(e)
        # RPC raises with "Insufficient stock..." — surface that cleanly
        if "insufficient stock" in msg.lower():
            raise ValueError(msg) from e
        raise NetworkError(f"Stock transaction failed: {e}") from e

    tx_id = res.data
    if not tx_id:
        raise UpdateFailedError(
            "Stock transaction did not return an ID — the write may have failed."
        )
    return tx_id


# -----------------------------------------------------------------------------
# DELIVERIES
# -----------------------------------------------------------------------------
def add_scheduled_delivery(
    due_date: str,
    project: str,
    item_description: str,
    qty: float,
    requestor: str,
    created_by: str,
    supplier: str | None = None,
    unit: str = "pcs",
) -> None:
    """Insert a single scheduled delivery row."""
    try:
        sb().table("deliveries").insert({
            "expected_date": due_date,
            "scheduled_date": due_date,
            "project": project,
            "item_name": item_description,
            "expected_quantity": float(qty),
            "unit": unit,
            "requested_by": requestor,
            "created_by": created_by,
            "supplier": supplier,
            "status": "Pending",
        }).execute()
    except Exception as e:
        raise NetworkError(f"Failed to add delivery: {e}") from e


def save_dispatch_batch(
    dispatch_header: dict, delivery_cart: list, created_by: str | None = None
) -> None:
    """Insert a batch of dispatch items and reserve stock.

    Uses an atomic Postgres RPC — deliveries insert and reserved_stock update
    happen in a single transaction. If either fails, both roll back.
    """
    if not delivery_cart:
        raise ValueError("Delivery cart is empty.")

    creator = (
        created_by
        or dispatch_header.get("created_by")
        or (st.session_state.get("user_name") if hasattr(st, "session_state") else None)
        or "System"
    )

    items_payload = []
    for item in delivery_cart:
        items_payload.append({
            "item_name": item["item_name"],
            "unit": item.get("unit", "pcs"),
            "quantity": float(item["quantity"]),
            "notes": item.get("notes", ""),
        })

    try:
        sb().rpc(
            "save_dispatch_batch_atomic",
            {
                "p_dispatch_id":    dispatch_header["dispatch_id"],
                "p_scheduled_date": dispatch_header["scheduled_date"],
                "p_destination":    dispatch_header["destination"],
                "p_requested_by":   dispatch_header["requested_by"],
                "p_project":        dispatch_header["project"],
                "p_created_by":     creator,
                "p_is_priority":    bool(dispatch_header.get("is_priority", 0)),
                "p_driver_name":    dispatch_header.get("driver_name", ""),
                "p_items":          items_payload,
            },
        ).execute()
    except Exception as e:
        raise NetworkError(f"Failed to save dispatch batch: {e}") from e


def update_dispatch_status(
    dispatch_id: str,
    new_status: str,
    handled_by: str = "System",
    driver_name: str | None = None,
    delivery_notes: str | None = None,
) -> None:
    """Update the status of all rows in a dispatch batch.

    Uses an atomic Postgres RPC — stock deductions, transaction log inserts,
    and status updates all happen in one transaction. No partial writes.
    """
    new_status_clean = new_status.strip()
    if new_status_clean not in ("Pending", "In Transit", "Completed", "Cancelled"):
        raise ValueError("Invalid status provided.")

    try:
        sb().rpc(
            "update_dispatch_status_atomic",
            {
                "p_dispatch_id":    dispatch_id,
                "p_new_status":     new_status_clean,
                "p_handled_by":     handled_by,
                "p_driver_name":    driver_name,
                "p_delivery_notes": delivery_notes,
            },
        ).execute()
    except Exception as e:
        msg = str(e)
        if "already" in msg.lower() or "no dispatch" in msg.lower():
            raise ValueError(msg) from e
        raise NetworkError(f"Failed to update dispatch status: {e}") from e


# -----------------------------------------------------------------------------
# DISCREPANCIES
# -----------------------------------------------------------------------------
def resolve_discrepancy(
    discrepancy_id: str,
    resolved_by: str,
    resolution_notes: str,
    approve_adjustment: bool = True,
) -> None:
    """Approve or reject a discrepancy atomically.

    Uses a Postgres RPC — discrepancy update, master_items stock adjustment,
    and reconciliation transaction insert all happen in one transaction.
    """
    try:
        sb().rpc(
            "resolve_discrepancy_atomic",
            {
                "p_discrepancy_id":   discrepancy_id,
                "p_resolved_by":      resolved_by,
                "p_resolution_notes": resolution_notes,
                "p_approve":          bool(approve_adjustment),
            },
        ).execute()
    except Exception as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise ValueError(msg) from e
        raise NetworkError(f"Failed to resolve discrepancy: {e}") from e


# -----------------------------------------------------------------------------
# GOOGLE DRIVE (attachments only)
# -----------------------------------------------------------------------------
def clean_private_key(key_str: str) -> str:
    if not key_str:
        return key_str
    key_str = key_str.strip("'\" ")
    if "\\n" in key_str:
        key_str = key_str.replace("\\n", "\n")
    if (
        "-----BEGIN PRIVATE KEY-----" in key_str
        and not key_str.startswith("-----BEGIN PRIVATE KEY-----")
    ):
        key_str = (
            "-----BEGIN PRIVATE KEY-----"
            + key_str.split("-----BEGIN PRIVATE KEY-----")[-1]
        )
    return key_str.strip()


def get_drive_service():
    """Authenticate and build Google Drive API service (attachments only)."""
    SCOPES = ["https://www.googleapis.com/auth/drive"]

    if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict:
                creds_dict["private_key"] = clean_private_key(
                    creds_dict["private_key"]
                )
            creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=SCOPES
            )
            return build("drive", "v3", credentials=creds), "Service Account"
        except Exception as e:
            print(f"[Drive Warning] Service Account auth failed: {e}")

    if hasattr(st, "secrets") and "gdrive_token" in st.secrets:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            token_info = dict(st.secrets["gdrive_token"])
            creds = Credentials.from_authorized_user_info(token_info, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            return build("drive", "v3", credentials=creds), "OAuth Token"
        except Exception as e:
            print(f"[Drive Warning] OAuth Token auth failed: {e}")

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if os.path.exists("token.json"):
            try:
                creds = Credentials.from_authorized_user_file("token.json", SCOPES)
            except Exception as e:
                print(f"[Drive Warning] Invalid token.json deleted: {e}")
                os.remove("token.json")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif os.path.exists("credentials.json"):
                flow = InstalledAppFlow.from_client_secrets_file(
                    "credentials.json", SCOPES
                )
                creds = flow.run_local_server(port=0)
                with open("token.json", "w") as token:
                    token.write(creds.to_json())
            else:
                print("[Drive Warning] No valid credentials found.")
                return None, None

        return build("drive", "v3", credentials=creds), "Local Credentials"
    except Exception as e:
        print(f"[Drive Auth Error] {e}")
        return None, None


def upload_file_to_gdrive(
    file_bytes: bytes,
    file_name: str,
    mime_type: str = "application/octet-stream",
) -> str | None:
    """Upload raw bytes to Google Drive and return the shareable link."""
    service, auth_type = get_drive_service()
    if not service:
        print("[Drive Upload Error] Could not initialize Drive service.")
        return None

    try:
        from googleapiclient.http import MediaIoBaseUpload

        folder_id = None
        if hasattr(st, "secrets"):
            folder_id = st.secrets.get("google_drive", {}).get("folder_id")

        file_metadata = {"name": file_name}
        if folder_id:
            file_metadata["parents"] = [folder_id]

        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes), mimetype=mime_type, resumable=True
        )

        file = (
            service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
        return file.get("webViewLink")
    except Exception as e:
        print(f"[Drive Upload Error] Failed to upload '{file_name}': {e}")
        return None


def create_test_file_in_gdrive():
    """Sanity-check upload to Drive."""
    content = (
        "ARV test file - if you can read this, Drive auth works.\n"
        f"Timestamp: {_now_iso()}\n"
    )
    return upload_file_to_gdrive(
        content.encode("utf-8"), "ARV_drive_test.txt", "text/plain"
    )
