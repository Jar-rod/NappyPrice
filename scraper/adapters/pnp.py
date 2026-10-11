from __future__ import annotations

import json
import re
from urllib.parse import quote

from core import config
from core.models import SearchHit
from scraper import parse
from scraper.adapters.base import ExtractError, StoreAdapter
from scraper.extract import to_page

API = "https://www.pnp.co.za/pnphybris/v2/pnp-spa/products"
FIELDS = "code,name,price(FULL),images(DEFAULT),stock(FULL),potentialPromotions(FULL),inStockIndicator,url"


class PicknPay(StoreAdapter):
    """Reads the JSON endpoints the Pick n Pay site itself calls.

    Prices are per store region. PNP_STORE_CODE picks the region (default WC21,
    the site's own default); set it to your local store's code if prices differ.
    """

    store_id = "pnp"
    name = "Pick n Pay"
    base_url = "https://www.pnp.co.za"
    search_url = "https://www.pnp.co.za/search/{q}"
    fixture_ext = "json"

    @staticmethod
    def _region() -> str:
        return f"storeCode={config.get('PNP_STORE_CODE', 'WC21')}&lang=en&curr=ZAR"

    def fetch_product(self, url, browser):
        match = re.search(r"/p/([\w]+)", url)
        if not match:
            raise ExtractError("no product code in the Pick n Pay link")
        return self.fetcher.get(f"{API}/{match.group(1)}?fields={FIELDS}&{self._region()}",
                                headers={"Accept": "application/json"})

    @staticmethod
    def _image(product: dict) -> str | None:
        images = product.get("images") or []
        best = next((i for i in images if i.get("format") == "product"), images[0] if images else {})
        return best.get("url")

    def parse_product(self, html, url):
        data = json.loads(html)
        price = data.get("price") or {}
        stock = (data.get("stock") or {}).get("stockLevelStatus")
        # Multibuy deals ("Buy 2, Save 30%") leave the shelf price unchanged but are still promotions.
        promos = [p.get("promotionTextMessage") or p.get("description") or "promo"
                  for p in data.get("potentialPromotions") or [] if p.get("valid", True)]
        fields = {
            "title": data.get("name"),
            "price": parse.parse_price(price.get("value")),
            "was_price": parse.parse_price(price.get("oldPrice")),
            "in_stock": data.get("inStockIndicator") if stock is None else stock != "outOfStock",
            "image_url": self._image(data),
            "badges": ["promo"] if promos else [],
        }
        return to_page(fields, self.clean_url(url), self.store_id)

    def fetch_search(self, query):
        url = (f"{API}/search?fields=products(code,name,price(FULL),url)&query={quote(query)}"
               f"&pageSize=20&{self._region()}")
        return self.fetcher.get(url, headers={"Accept": "application/json"}, method="POST")

    def parse_search(self, html):
        hits = []
        for product in json.loads(html).get("products") or []:
            if not product.get("code") or not product.get("name"):
                continue
            slug = re.sub(r"[^a-z0-9]+", "-", product["name"].lower()).strip("-")
            hits.append(SearchHit(f"{self.base_url}/{slug}/p/{product['code']}", product["name"],
                                  parse.parse_price((product.get("price") or {}).get("value"))))
        return hits
