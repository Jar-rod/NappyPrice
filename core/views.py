"""Read-side helpers for the app: dashboard rows and price history."""
from __future__ import annotations

from datetime import datetime, timedelta

from core.models import SIZES
from zoneinfo import ZoneInfo

from core.repo import Repo, now_utc, parse_ts

SAST = ZoneInfo("Africa/Johannesburg")

<<<<<<< HEAD
# A reading older than this is stale: shown, but never counted as the best price or in
# the average. It covers manual-only stores and stores whose scraper has been failing.
STALE_AFTER = timedelta(hours=48)


def is_stale(check: dict | None, now: datetime) -> bool:
    return bool(check) and now - parse_ts(check["checked_at"]) > STALE_AFTER


=======
>>>>>>> 56b44108f4cf891888894d2a762a896877c970a1
OTHER_BRANDS = "Other brands"   # label for products with no brand set
CATEGORY_ORDER = ["nappies", "wipes", "formula", "bin_refills", "sterilising", "other"]


def _size_rank(size: str | None) -> int:
    return SIZES.index(size) if size in SIZES else len(SIZES)


def dashboard_rows(repo: Repo, now: datetime | None = None, store_ids: list[str] | None = None,
                   brands: list[str] | None = None) -> list[dict]:
    """One row per active product, with its cheapest current listing.

    `best` is the cheapest in-stock reading (any reading if none is in stock);
    `change` is the cheapest unit price now against a week ago, as a fraction.

    `store_ids` narrows everything to those stores: the cheapest price, the
    special flag and the weekly change are worked out among them only, and
    products none of them sell are left out. `brands` keeps only those brands.
    """
    now = now or now_utc()
    stores = {s["id"]: s for s in repo.list_stores()}
    latest = repo.latest_prices()
    listings_by_product: dict[str, list[dict]] = {}
    for listing in repo.list_listings():
        if store_ids and listing["store_id"] not in store_ids:
            continue
        listings_by_product.setdefault(listing["product_id"], []).append(listing)

    # Last reading at least a week old (taken from the 3 days before that) per listing.
    week_ago = now - timedelta(days=6, hours=12)
    old_unit: dict[str, float] = {}
    for check in repo.checks_since(now - timedelta(days=10)):
        if check.get("ok") and check.get("unit_price") is not None and parse_ts(check["checked_at"]) <= week_ago:
            old_unit[check["listing_id"]] = float(check["unit_price"])

    rows = []
    for product in repo.list_products(active=True):
        listings = listings_by_product.get(product["id"], [])
        if (store_ids and not listings) or (brands and (product.get("brand") or OTHER_BRANDS) not in brands):
            continue
        readings = [(latest[l["id"]], l) for l in listings
                    if l["id"] in latest and latest[l["id"]].get("unit_price") is not None]
<<<<<<< HEAD
        # Prefer current readings; fall back to stale ones only when there is nothing newer.
        readings = [r for r in readings if not is_stale(r[0], now)] or readings
        in_stock = [r for r in readings if r[0].get("in_stock") is not False]
        best = min(in_stock or readings, key=lambda r: float(r[0]["unit_price"]), default=None)
        priced = [float(r[0]["unit_price"]) for r in (in_stock or readings)]
=======
        in_stock = [r for r in readings if r[0].get("in_stock") is not False]
        best = min(in_stock or readings, key=lambda r: float(r[0]["unit_price"]), default=None)
>>>>>>> 56b44108f4cf891888894d2a762a896877c970a1
        old = [old_unit[l["id"]] for l in listings if l["id"] in old_unit]
        change = None
        if best and old and min(old) > 0:
            change = float(best[0]["unit_price"]) / min(old) - 1
        rows.append({
            "product": product,
            "listing_count": len(listings),
            "store_count": len({l["store_id"] for l in listings}),
<<<<<<< HEAD
            # Mean price per unit over every in-stock listing, so the best price has something to be judged against.
            "average": average(priced) if len(priced) > 1 else None,
=======
>>>>>>> 56b44108f4cf891888894d2a762a896877c970a1
            "check": best[0] if best else None,
            "listing": best[1] if best else None,
            "store_name": stores.get(best[1]["store_id"], {}).get("name") if best else None,
            "store": stores.get(best[1]["store_id"]) if best else None,
            "any_special": any(r[0].get("on_special") for r in in_stock),
            "below_target": bool(best and product.get("target_unit_price") is not None
                                 and float(best[0]["unit_price"]) <= float(product["target_unit_price"])),
            "change": change,
        })
    # Category, then brand, then size: the dashboard shows each category as a list of brands.
    rows.sort(key=lambda r: (
        CATEGORY_ORDER.index(r["product"]["category"]) if r["product"]["category"] in CATEGORY_ORDER else 99,
        (r["product"].get("brand") or "~").lower(),
        _size_rank(r["product"].get("size")), r["product"]["name"].lower()))
    return rows


def history(repo: Repo, product_id: str, days: int | None) -> list[dict]:
    """One point per store per day: that store's cheapest price per unit, oldest first.

    A store selling several pack sizes still gets a single line, so the graph
    answers "who was cheapest when" rather than drawing every pack.
    `days=None` is everything.
    """
    listings = {l["id"]: l for l in repo.list_listings(product_id, active_only=False)}
    since = now_utc() - timedelta(days=days) if days else datetime(2000, 1, 1, tzinfo=now_utc().tzinfo)
    stores = {s["id"]: s["name"] for s in repo.list_stores()}
    best: dict[tuple, dict] = {}
    for check in repo.checks_since(since, list(listings)):
        if not check.get("ok") or check.get("unit_price") is None:
            continue
        listing = listings[check["listing_id"]]
        at = parse_ts(check["checked_at"])
        key = (listing["store_id"], at.astimezone(SAST).date())
        point = {"series": stores.get(listing["store_id"], listing["store_id"]), "store_id": listing["store_id"],
                 "at": at, "unit_price": float(check["unit_price"]), "price": float(check["price"]),
                 "units": listing["units_per_pack"], "on_special": bool(check.get("on_special"))}
        if key not in best or point["unit_price"] < best[key]["unit_price"]:
            best[key] = point
    return sorted(best.values(), key=lambda p: (p["series"], p["at"]))


<<<<<<< HEAD
def item_prices(repo: Repo, product_id: str, now: datetime | None = None) -> list[dict]:
    """Every active listing of a product with its latest reading, best price per unit first.

    Current in-stock listings come first, then out-of-stock, then stale readings
    (not refreshed in the last two days), and listings with no price yet come last.
    """
    now = now or now_utc()
=======
def item_prices(repo: Repo, product_id: str) -> list[dict]:
    """Every active listing of a product with its latest reading, best price per unit first.

    In-stock listings come before out-of-stock ones, and listings with no price yet come last.
    """
>>>>>>> 56b44108f4cf891888894d2a762a896877c970a1
    stores = {s["id"]: s for s in repo.list_stores()}
    latest = repo.latest_prices()
    rows = []
    for listing in repo.list_listings(product_id):
        check = latest.get(listing["id"])
        unit = float(check["unit_price"]) if check and check.get("unit_price") is not None else None
<<<<<<< HEAD
        rows.append({"listing": listing, "check": check, "unit_price": unit, "stale": is_stale(check, now),
                     "store": stores.get(listing["store_id"], {"id": listing["store_id"], "name": listing["store_id"]})})
    rows.sort(key=lambda r: (r["unit_price"] is None, r["stale"],
                             bool(r["check"] and r["check"].get("in_stock") is False), r["unit_price"] or 0))
    return rows


def average(unit_prices: list[float]) -> float | None:
    """Plain mean of the given prices per unit."""
    prices = [p for p in unit_prices if p is not None]
    return round(sum(prices) / len(prices), 4) if prices else None


=======
        rows.append({"listing": listing, "check": check, "unit_price": unit,
                     "store": stores.get(listing["store_id"], {"id": listing["store_id"], "name": listing["store_id"]})})
    rows.sort(key=lambda r: (r["unit_price"] is None, bool(r["check"] and r["check"].get("in_stock") is False),
                             r["unit_price"] or 0))
    return rows


>>>>>>> 56b44108f4cf891888894d2a762a896877c970a1
def suggested_target(unit_prices: list[float], discount: float = 0.15) -> float | None:
    """Default target: 15% under today's cheapest price per unit."""
    prices = [p for p in unit_prices if p]
    return round(min(prices) * (1 - discount), 2) if prices else None
