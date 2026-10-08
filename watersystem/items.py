"""Water system item CRUD. All queries scoped to warehouse='watersystem'."""
from database import (
    sb, NetworkError, ItemExistsError, UpdateFailedError,
)
from watersystem import config as cfg


def _compute_prices(cost_php, shipping_php, markup_pct, manual_price):
    c = float(cost_php or 0)
    s = float(shipping_php or 0)
    total = round(c + s, 2)
    if manual_price is not None and manual_price != "":
        return total, round(float(manual_price), 2)
    if markup_pct is not None and markup_pct != "":
        m = float(markup_pct)
        return total, round(total * (1 + m / 100), 2)
    return total, total


def _clean_item_payload(data: dict) -> dict:
    name = (data.get("item_name") or "").strip()
    category = (data.get("category") or "").strip()
    unit = (data.get("unit") or "pcs").strip()
    material = (data.get("material") or "").strip() or None
    size = (data.get("size") or "").strip() or None

    if not name:
        raise ValueError("Item name is required.")
    if len(name) > 200:
        raise ValueError("Item name must be 200 characters or fewer.")
    if not category:
        raise ValueError("Category is required.")
    if not unit:
        raise ValueError("Unit is required.")

    def _to_float(v, label):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{label} must be a number.")

    cost = _to_float(data.get("cost_php"), "Cost (PHP)")
    shipping = _to_float(data.get("shipping_php"), "Shipping (PHP)")
    markup = _to_float(data.get("markup_pct"), "Markup %")
    manual = data.get("selling_price_php")

    for v, label in [(cost, "Cost"), (shipping, "Shipping")]:
        if v is not None and v < 0:
            raise ValueError(f"{label} cannot be negative.")
    if markup is not None and markup < 0:
        raise ValueError("Markup % cannot be negative.")
    if manual not in (None, ""):
        try:
            manual_f = float(manual)
        except (TypeError, ValueError):
            raise ValueError("Selling price must be a number.")
        if manual_f < 0:
            raise ValueError("Selling price cannot be negative.")
        manual = manual_f
    else:
        manual = None

    min_threshold = _to_float(data.get("min_threshold"), "Min threshold") or 0.0
    if min_threshold < 0:
        raise ValueError("Min threshold cannot be negative.")

    initial_stock = _to_float(data.get("initial_stock"), "Initial stock") or 0.0
    if initial_stock < 0:
        raise ValueError("Initial stock cannot be negative.")

    total_cost, selling = _compute_prices(cost, shipping, markup, manual)

    return {
        "item_name": name, "category": category, "unit": unit,
        "material": material, "size": size,
        "cost_php": cost, "shipping_php": shipping,
        "total_cost_php": total_cost, "markup_pct": markup,
        "selling_price_php": selling,
        "min_threshold": min_threshold, "initial_stock": initial_stock,
        "remarks": (data.get("remarks") or "").strip() or None,
        "image_url": (data.get("image_url") or "").strip() or None,
    }


def list_items() -> list[dict]:
    try:
        res = (
            sb().table("master_items").select("*")
            .eq("warehouse", cfg.WAREHOUSE)
            .order("item_name").execute()
        )
    except Exception as e:
        raise NetworkError(f"Failed to list water items: {e}") from e
    return res.data or []


def get_item(item_id: int) -> dict | None:
    try:
        res = (
            sb().table("master_items").select("*")
            .eq("id", item_id).eq("warehouse", cfg.WAREHOUSE)
            .limit(1).execute()
        )
    except Exception as e:
        raise NetworkError(f"Failed to get item: {e}") from e
    return (res.data or [None])[0]


def create_item(data: dict) -> int:
    clean = _clean_item_payload(data)

    try:
        existing = (
            sb().table("master_items").select("id")
            .eq("item_name", clean["item_name"])
            .eq("warehouse", cfg.WAREHOUSE)
            .limit(1).execute()
        )
    except Exception as e:
        raise NetworkError(f"Failed to check existing items: {e}") from e
    if existing.data:
        raise ItemExistsError(
            f"A water item named '{clean['item_name']}' already exists."
        )

    row = {
        "item_name": clean["item_name"], "category": clean["category"],
        "unit": clean["unit"], "current_stock": clean["initial_stock"],
        "reserved_stock": 0.0, "min_threshold": clean["min_threshold"],
        "remarks": clean["remarks"], "warehouse": cfg.WAREHOUSE,
        "material": clean["material"], "size": clean["size"],
        "cost_php": clean["cost_php"], "shipping_php": clean["shipping_php"],
        "total_cost_php": clean["total_cost_php"],
        "markup_pct": clean["markup_pct"],
        "selling_price_php": clean["selling_price_php"],
        "image_url": clean["image_url"],
    }

    try:
        res = sb().table("master_items").insert(row).execute()
    except Exception as e:
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            raise ItemExistsError(
                f"A water item named '{clean['item_name']}' already exists."
            )
        raise NetworkError(f"Failed to create item: {e}") from e

    if not res.data:
        raise UpdateFailedError("Item insert did not return a row.")
    return res.data[0]["id"]


def update_item(item_id: int, data: dict) -> None:
    clean = _clean_item_payload(data)

    existing = get_item(item_id)
    if not existing:
        raise UpdateFailedError("Item not found in water system warehouse.")

    update = {
        "item_name": clean["item_name"], "category": clean["category"],
        "unit": clean["unit"], "min_threshold": clean["min_threshold"],
        "remarks": clean["remarks"], "material": clean["material"],
        "size": clean["size"], "cost_php": clean["cost_php"],
        "shipping_php": clean["shipping_php"],
        "total_cost_php": clean["total_cost_php"],
        "markup_pct": clean["markup_pct"],
        "selling_price_php": clean["selling_price_php"],
        "image_url": clean["image_url"],
    }

    try:
        res = (
            sb().table("master_items").update(update)
            .eq("id", item_id).eq("warehouse", cfg.WAREHOUSE).execute()
        )
    except Exception as e:
        raise NetworkError(f"Failed to update item: {e}") from e
    if not res.data:
        raise UpdateFailedError("Item update did not affect a row.")