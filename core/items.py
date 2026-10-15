"""Saving a new item: one product, its store listings and their first prices."""
from __future__ import annotations

from core.models import UNIT_LABELS
from core.repo import Repo, iso, now_utc
from core.views import suggested_target


def unit_price(price, units) -> float | None:
    return round(float(price) / int(units), 4) if price and units else None


def save_item(repo: Repo, fields: dict, entries: list[dict], created_by: str | None = None) -> dict:
    """Create the product and a listing per entry.

    `fields` describes the product (name, brand, range_name, category, size,
    unit_label, image_url). Each entry is a store page: url, store_id, title,
    units_per_pack, and optionally score, price, was_price, on_special, in_stock.
    Prices already read by the search are saved as today's first check, and the
    target defaults to 15% under the cheapest in-stock price per unit.
    """
    category = fields.get("category") or "nappies"
    # A second press of Save can interrupt the first after it created the product but
    # before its listings were written. Reuse that empty product instead of making another,
    # and never create a second product for a link that is already tracked.
    for entry in entries:
        if repo.get_listing_by_url(entry["url"]):
            raise ValueError("This item is already being tracked.")
    orphan = next((p for p in repo.list_products(active=None)
                   if p["name"] == fields["name"] and p.get("size") == fields.get("size")
                   and p.get("category") == category and not repo.list_listings(p["id"], active_only=False)), None)
    if orphan:
        repo.update_product(orphan["id"], active=True)
        add_listings(repo, orphan, entries)
        return orphan
    in_stock = [unit_price(e.get("price"), e["units_per_pack"]) for e in entries if e.get("in_stock") is not False]
    product = repo.insert_product({
        "name": fields["name"], "brand": fields.get("brand"), "range_name": fields.get("range_name"),
        "category": category, "size": fields.get("size"),
        "unit_label": fields.get("unit_label") or UNIT_LABELS.get(category, "unit"),
        "image_url": fields.get("image_url") or next((e.get("image_url") for e in entries if e.get("image_url")), None),
        "alert_enabled": True, "created_by": created_by,
        "target_unit_price": suggested_target([p for p in in_stock if p]),
    })
    add_listings(repo, product, entries)
    return product


def add_listings(repo: Repo, product: dict, entries: list[dict]) -> int:
    """Attach store pages to a product, saving any price already read as today's first check."""
    stamp = iso(now_utc())
    for entry in entries:
        listing = repo.insert_listing({"product_id": product["id"], "store_id": entry["store_id"],
                                       "url": entry["url"], "title": entry.get("title"),
                                       "units_per_pack": int(entry["units_per_pack"]),
                                       "match_score": entry.get("score")})
        if entry.get("price"):
            repo.insert_price_check({"listing_id": listing["id"], "ok": True, "checked_at": stamp,
                                     "price": entry["price"],
                                     "unit_price": unit_price(entry["price"], entry["units_per_pack"]),
                                     "was_price": entry.get("was_price"),
                                     "on_special": bool(entry.get("on_special")),
                                     "in_stock": entry.get("in_stock")})
    return len(entries)
