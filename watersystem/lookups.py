"""Lookup options: category, material, size."""
from database import sb, NetworkError, UpdateFailedError, _now_iso
from watersystem import config as cfg


def list_approved(kind: str) -> list[str]:
    try:
        res = (
            sb().table("lookup_options")
            .select("value").eq("kind", kind)
            .eq("warehouse", cfg.WAREHOUSE)
            .eq("status", "approved")
            .order("value").execute()
        )
    except Exception as e:
        raise NetworkError(f"Failed to list {kind} options: {e}") from e
    return [row["value"] for row in (res.data or [])]


def list_pending() -> list[dict]:
    try:
        res = (
            sb().table("lookup_options")
            .select("*").eq("warehouse", cfg.WAREHOUSE)
            .eq("status", "pending")
            .order("created_at", desc=True).execute()
        )
    except Exception as e:
        raise NetworkError(f"Failed to list pending options: {e}") from e
    return res.data or []


def count_pending() -> int:
    try:
        res = (
            sb().table("lookup_options")
            .select("id", count="exact")
            .eq("warehouse", cfg.WAREHOUSE)
            .eq("status", "pending").execute()
        )
        return res.count or 0
    except Exception:
        return 0


def request_new(kind: str, value: str, requested_by: str) -> str:
    clean = (value or "").strip()
    if not clean:
        raise ValueError("Value cannot be empty.")
    if len(clean) > 100:
        raise ValueError("Value must be 100 characters or fewer.")

    try:
        existing = (
            sb().table("lookup_options")
            .select("id,status").eq("kind", kind).eq("value", clean)
            .eq("warehouse", cfg.WAREHOUSE).limit(1).execute()
        )
    except Exception as e:
        raise NetworkError(f"Failed to check existing option: {e}") from e

    if existing.data:
        return existing.data[0]["status"]

    try:
        sb().table("lookup_options").insert({
            "kind": kind, "value": clean, "warehouse": cfg.WAREHOUSE,
            "status": "pending", "created_by": requested_by,
        }).execute()
    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            return "exists"
        raise NetworkError(f"Failed to request new {kind}: {e}") from e
    return "pending"


def approve(option_id: int, approved_by: str) -> None:
    try:
        res = (
            sb().table("lookup_options").update({
                "status": "approved",
                "approved_at": _now_iso(),
                "approved_by": approved_by,
                "rejection_reason": None,
            }).eq("id", option_id).execute()
        )
    except Exception as e:
        raise NetworkError(f"Failed to approve option: {e}") from e
    if not res.data:
        raise UpdateFailedError("Option not found.")


def reject(option_id: int, reason: str, rejected_by: str) -> None:
    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValueError("Rejection reason is required.")
    try:
        res = (
            sb().table("lookup_options").update({
                "status": "rejected",
                "approved_at": _now_iso(),
                "approved_by": rejected_by,
                "rejection_reason": clean_reason,
            }).eq("id", option_id).execute()
        )
    except Exception as e:
        raise NetworkError(f"Failed to reject option: {e}") from e
    if not res.data:
        raise UpdateFailedError("Option not found.")