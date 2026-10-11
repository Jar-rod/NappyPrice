"""Find the same product at other stores and score how well each candidate matches."""
from __future__ import annotations

import re

from rapidfuzz import fuzz

from core.models import ProductPage
from core.repo import Repo
from scraper import parse
from scraper.adapters import ADAPTERS, reachable
from scraper.fetch import Fetcher

WEIGHTS = {"brand": 30, "range_name": 20, "size": 25, "units_per_pack": 15}
TITLE_WEIGHT = 10
PRETICK_SCORE = 85
SEARCH_HITS = 10
CANDIDATES_PER_STORE = 5
MIN_TITLE_SCORE = 40   # search hits scoring below this on title alone are not fetched
MIN_SCORE = 60         # candidates below this (wrong size, wrong range) are not offered


def _norm(value) -> str:
    return re.sub(r"[^a-z0-9+]", "", str(value).lower()) if value not in (None, "") else ""


# Words that make two similarly named products different things.
_KINDS = [("compatible", r"compatible|generic"), ("tablets", r"tablet"), ("fluid", r"fluid|liquid"),
          ("spray", r"spray"), ("steriliser", r"sterili[sz]ing unit|steriliser"), ("handwash", r"handwash|hand wash"),
          ("ready to feed", r"ready[\s-]to[\s-]feed|read to feed|\brtf\b|\d\s?ml\b"),
          ("wipes", r"wipes?\b"), ("refill", r"refill|cassette|cartridge"),
          ("nappy bags", r"knot a bag|nappy bags?\b|nappy sacks?")]


def _kinds(title: str | None, category: str) -> set[str]:
    found = {name for name, pattern in _KINDS if re.search(pattern, title or "", re.I)}
    if category != "formula":
        found.discard("ready to feed")   # a volume in the name only signals this for formula
    if category == "wipes":
        found.discard("refill")          # "wipes refill pack" is still the same wipes
    return found


def score(target: dict, candidate: dict) -> int:
    """0-100: brand 30, range 20, size 25, pack count 15, title similarity 10.

    Weight for a field the target does not have (a bin refill has no size) moves
    to title similarity, so such products are judged mostly on their names.
    """
    total, title_weight = 0.0, TITLE_WEIGHT
    for key, weight in WEIGHTS.items():
        wanted = _norm(target.get(key))
        if not wanted:
            title_weight += weight
        elif wanted == _norm(candidate.get(key)):
            total += weight
    similarity = fuzz.token_set_ratio((target.get("title") or "").lower(), (candidate.get("title") or "").lower())
    total += title_weight * similarity / 100
    # A compatible refill is never the genuine one; tablets are never fluid; powder is never ready-to-feed.
    category = target.get("category") or "nappies"
    if _kinds(target.get("title"), category) != _kinds(candidate.get("title"), category):
        total = min(total, 50)
    # A different pack size is worth offering but is never ticked for you.
    elif target.get("units_per_pack") and _norm(target["units_per_pack"]) != _norm(candidate.get("units_per_pack")):
        total = min(total, PRETICK_SCORE - 1)
    return round(total)


def with_category(page: dict, category: str) -> dict:
    """Re-read size and unit count from the title the way this category needs."""
    return {**page, **parse.describe(page.get("title"), category), "category": category}


def _from_title(title: str, category: str) -> dict:
    brand = parse.parse_brand(title)
    base = {"title": title, "brand": brand, "range_name": parse.parse_range(title, brand),
            "size": parse.parse_size(title), "units_per_pack": parse.parse_pack_count(title)}
    return with_category(base, category)


def target_from_page(page: ProductPage | dict, category: str = "nappies") -> dict:
    data = page.to_dict() if isinstance(page, ProductPage) else dict(page)
    return with_category(data, data.get("category") or category)


def find_matches(repo: Repo, fetcher: Fetcher, target: dict, skip_store: str | None = None,
                 only_stores: set[str] | None = None) -> tuple[dict, dict]:
    """Search every other active store (or just `only_stores`). Returns ({store: [candidates]}, {store: error})."""
    query = parse.build_query(target)
    category = target.get("category") or "nappies"
    known = {l["url"] for l in repo.list_listings(active_only=False)}
    candidates, errors = {}, {}
    for store in repo.list_stores(active_only=True):
        store_id = store["id"]
        if store_id == skip_store or store_id not in ADAPTERS or (only_stores and store_id not in only_stores):
            continue
        if not reachable(store_id):
            errors[store_id] = "not searched: only the Mac runner can read this store, and it is offline"
            continue
        adapter = ADAPTERS[store_id](fetcher)
        try:
            hits = adapter.search(query)[:SEARCH_HITS]
        except Exception as exc:
            errors[store_id] = f"search failed: {exc}"
            continue
        # Rank on the search title first so only the likeliest few pages are fetched.
        # Some stores answer a search with unrelated bestsellers; those are dropped here.
        scored = [(score(target, _from_title(h.title, category)), h) for h in hits if h.url not in known]
        ranked = [h for s, h in sorted(scored, key=lambda pair: pair[0], reverse=True) if s >= MIN_TITLE_SCORE]
        found = []
        for hit in ranked[:CANDIDATES_PER_STORE]:
            try:
                page = with_category(adapter.extract(hit.url).to_dict(), category)
            except Exception:
                # Keep the hit with what the search page told us.
                page = {**_from_title(hit.title, category), "url": hit.url, "store_id": store_id, "price": hit.price,
                        "was_price": None, "on_special": False, "in_stock": None, "image_url": None}
            page["score"] = score(target, page)
            if page["score"] >= MIN_SCORE:
                found.append(page)
        candidates[store_id] = sorted(found, key=lambda c: c["score"], reverse=True)
    return candidates, errors
