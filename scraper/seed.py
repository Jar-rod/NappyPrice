"""Seed a few products by reading their live store pages.

    uv run python -m scraper.seed

Works against Supabase or the local JSON database. Listings already present
(matched by URL) are skipped, so it is safe to run twice.
"""
from __future__ import annotations

from core.models import UNIT_LABELS
from core.repo import get_repo
from scraper.adapters import adapter_for_url, store_rows
from scraper.fetch import Fetcher

SEED = [
    {"name": "Pampers Premium Care", "category": "nappies", "urls": [
        "https://clicks.co.za/pampers_premium-care-nappies-value-pack-size-3-60s/p/139010",
        "https://www.dischem.co.za/pampers-premium-care-size-3-value-pack-60-s-038",
        "https://www.babycity.co.za/pampers-premium-care-size-3-value-pack-60-s-038",
        "https://www.babiesrus.co.za/premium-care-midi-s3-vp-60",
        "https://www.pnp.co.za/pampers-premium-care-size-3-60-nappies/p/000000000000409837_EA",
        "https://www.takealot.com/pampers-premium-care-size-3-taped-6-10-kg-120-nappies/PLID28062255",
        "https://www.checkers.co.za/product/pampers-premium-care-size-3-6-10kg-diapers-60-pack-10247330EA",
    ]},
    {"name": "Pampers Premium Care", "category": "nappies", "urls": [
        "https://clicks.co.za/pampers_premium-care-nappies-size-4-52s/p/139004",
        "https://www.dischem.co.za/pampers-premium-care-size-4-value-pack-52-s-037",
        "https://www.babycity.co.za/pampers-premium-care-mega-box-size-4-104-144",
        "https://www.makro.co.za/pampers-premium-care-mb-maxi-size-4-104s-tape-diapers/p/itm541ac7d799741?pid=DIRHMWDZSJBYXVPH",
    ]},
    {"name": "Pampers Premium Care", "category": "nappies", "urls": [
        "https://clicks.co.za/pampers_premium-care-nappies-size-1-82s/p/138992",
    ]},
    {"name": "Huggies Extra Care", "category": "nappies", "urls": [
        "https://www.dischem.co.za/huggies-extra-care-size-2-94s-259",
        "https://www.babycity.co.za/huggies-extra-care-size-2-94s-259",
    ]},
]


def main() -> None:
    repo = get_repo()
    repo.ensure_stores(store_rows())
    fetcher = Fetcher()
    try:
        for item in SEED:
            pages = []
            for url in item["urls"]:
                adapter = adapter_for_url(url)(fetcher)
                url = adapter.clean_url(url)
                if repo.get_listing_by_url(url):
                    print(f"skip (already tracked) {url}")
                    continue
                try:
                    pages.append(adapter.extract(url))
                except Exception as exc:
                    print(f"skip ({exc}) {url}")
            pages = [p for p in pages if p.units_per_pack]
            if not pages:
                continue
            first = pages[0]
            cheapest = min(p.price / p.units_per_pack for p in pages)
            product = repo.insert_product({
                "name": item["name"], "brand": first.brand, "range_name": first.range_name,
                "category": item["category"], "size": first.size,
                "unit_label": UNIT_LABELS[item["category"]], "image_url": first.image_url,
                "target_unit_price": round(cheapest * 0.85, 4), "created_by": "seed",
            })
            for page in pages:
                repo.insert_listing({"product_id": product["id"], "store_id": page.store_id, "url": page.url,
                                     "title": page.title, "units_per_pack": page.units_per_pack})
            print(f"added {item['name']} size {first.size}: {len(pages)} listings")
    finally:
        fetcher.close()


if __name__ == "__main__":
    main()
