from __future__ import annotations

import json
import re
from core.models import SearchHit
from scraper import parse
from scraper.adapters.base import ExtractError, StoreAdapter
from scraper.extract import to_page

API = "https://api.takealot.com/rest/v-1-19-0"


class Takealot(StoreAdapter):
    """Reads Takealot's public product JSON, the same data its own pages load."""

    store_id = "takealot"
    name = "Takealot"
    base_url = "https://www.takealot.com"
    search_url = API + "/searches/products?qsearch={q}"
    fixture_ext = "json"

    @staticmethod
    def _plid(url: str) -> str:
        match = re.search(r"PLID(\d+)", url)
        if not match:
            raise ExtractError("no PLID in the Takealot link")
        return match.group(1)

    def fetch_product(self, url, browser):
        return self.fetcher.get(f"{API}/product-details/PLID{self._plid(url)}?platform=desktop")

    def parse_product(self, html, url):
        data = json.loads(html)
        items = (data.get("buybox") or {}).get("items") or []
        offer = next((i for i in items if i.get("is_selected")), items[0] if items else {})
        images = (data.get("gallery") or {}).get("images") or []
        fields = {
            "title": data.get("title"),
            "brand": (data.get("core") or {}).get("brand"),
            "price": parse.parse_price(offer.get("price")),
            "was_price": parse.parse_price(offer.get("listing_price")),
            "in_stock": bool(offer.get("is_add_to_cart_available")) if offer else None,
            "image_url": images[0].replace("{size}", "pdpxl") if images else None,
        }
        return to_page(fields, self.clean_url(url), self.store_id)

    def parse_search(self, html):
        hits = []
        results = (((json.loads(html).get("sections") or {}).get("products") or {}).get("results")) or []
        for result in results:
            view = result.get("product_views") or {}
            core = view.get("core") or {}
            if not core.get("id") or not core.get("slug"):
                continue
            prices = (view.get("buybox_summary") or {}).get("prices") or []
            hits.append(SearchHit(f"{self.base_url}/{core['slug']}/PLID{core['id']}", core.get("title") or "",
                                  parse.parse_price(prices[0]) if prices else None))
        return hits
