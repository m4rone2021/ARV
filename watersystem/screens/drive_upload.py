"""Upload item photos to the configured Google Drive folder."""
import re
from datetime import datetime

from database import upload_file_to_gdrive


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", (name or "item").strip())
    return s.strip("_")[:60] or "item"


def upload_image(file_bytes: bytes, original_filename: str, item_name_hint: str = "") -> str | None:
    ext = ".jpg"
    if "." in original_filename:
        ext = "." + original_filename.rsplit(".", 1)[-1].lower()
        if ext not in (".jpg", ".jpeg", ".png"):
            ext = ".jpg"

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    slug = _slug(item_name_hint)
    filename = f"{slug}_{ts}{ext}"

    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

    url = upload_file_to_gdrive(file_bytes, filename, mime)
    if not url:
        raise RuntimeError("Drive upload returned no URL.")
    return url