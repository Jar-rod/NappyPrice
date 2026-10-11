from __future__ import annotations

import json
import re
from urllib.parse import quote

from core import config
from core.models import SearchHit
from scraper import parse
from scraper.adapters.base import ExtractError, StoreAdapter
from scraper.extract import to_page

API = "https://www.checkers.co.za/api"
# Sixty60 prices are per branch and depend on the delivery address. This one
# (Sandton City) is the default; set CHECKERS_ADDRESS_JSON to the same shape
# with your own address to see the prices you would actually pay.
DEFAULT_ADDRESS = {
    "fullAddress": "83 Rivonia Rd, Sandhurst, Sandton, 2196, South Africa",
    "streetNumber": "83", "street": "Rivonia Rd", "suburb": "Sandhurst", "city": "Sandton",
    "postalCode": "2196", "coordinates": {"longitude": 28.0527198, "latitude": -26.1088467},
    "id": "", "type": "", "name": "",
}
HEADERS = {"Accept": "application/json", "Origin": "https://www.checkers.co.za",
           "Referer": "https://www.checkers.co.za/"}


def slugify(name: str) -> str:
    return re.sub(r"\s+", "-", re.sub(r"[^a-z0-9\s-]", "", name.lower()).strip())


class Checkers(StoreAdapter):
    """Checkers Sixty60, read through the JSON endpoints its own site calls.

    No sign-in is involved: the site lets any visitor set a delivery address,
    and the branches serving that address decide the prices.
    """

    store_id = "checkers"
    name = "Checkers Sixty60"
    base_url = "https://www.checkers.co.za"
    search_url = "https://www.checkers.co.za/search?Search={q}"
    fixture_ext = "json"

    _contexts: list[dict] | None = None  # branches for the address, looked up once per run

    @staticmethod
    def address() -> dict:
        custom = config.get("CHECKERS_ADDRESS_JSON")
        return json.loads(custom) if custom else DEFAULT_ADDRESS

    def contexts(self) -> list[dict]:
        if Checkers._contexts is None:
            text = self.fetcher.post_json(f"{API}/store/fetch-store-contexts?update=false",
                                          {"address": self.address()}, headers=HEADERS)
            found = json.loads(text).get("storeContexts") or []
            if not found:
                raise ExtractError("Checkers has no branch serving the configured address")
            Checkers._contexts = found
        return Checkers._contexts

    def _query(self, text: str) -> str:
        contexts = self.contexts()
        body = {
            "storeContexts": contexts,
            "filterData": {
                "filter": {
                    "showAllDisplayVariants": False, "showNotRangedProducts": False,
                    "productListSource": {"search": text},
                    "paginationOptions": {"page": 0, "pageSize": 30},
                    "filterOptions": {"dealsOnly": False, "brandOptions": [], "departmentOptions": [],
                                      "serviceOptions": [], "facetOptions": []},
                    "sortOptions": None,
                },
                "displayOptions": {"includeDisplayCategoryTree": False},
            },
            "forYouBonusBuyIds": [],
        }
        # The cookie, not the body, is what selects the branch.
        cookie = "storeContexts=" + quote(json.dumps(contexts, separators=(",", ":")))
        raw = self.fetcher.post_json(f"{API}/catalogue/get-products-filter", body,
                                     headers={**HEADERS, "Cookie": cookie})
        # Without a valid cookie the site silently answers for a default branch
        # with different prices. Never accept a price from a branch we did not ask for.
        wanted = {c["storeId"] for c in contexts}
        strays = {p.get("storeId") for p in json.loads(raw).get("products") or []} - wanted
        if strays:
            raise ExtractError("Checkers answered for a different branch than the configured address")
        return raw

    def slim_fixture(self, text):
        keep = ("articleNumber", "name", "brand", "price", "priceFactor", "oldPrice", "isOnPromotion",
                "isStockAvailable", "outOfStock", "imageId", "unitOfMeasure", "storeId", "attributes")
        data = json.loads(text)
        products = [{k: p[k] for k in keep if k in p} for p in data.get("products") or []]
        return json.dumps({"products": products, "totalCount": data.get("totalCount")}, indent=1)

    @staticmethod
    def _article(url: str) -> tuple[str, str]:
        """Article number and unit of measure. One article can be sold as a single
        ('EA') and as a multipack ('PK1') at different prices, so both identify it."""
        match = re.search(r"-(\d{5,})([A-Z]{2}\d*)?/?$", url.split("?")[0])
        if not match:
            raise ExtractError("no article number in the Checkers link")
        return match.group(1), match.group(2) or "EA"

    def fetch_product(self, url, browser):
        # There is no single-product endpoint to call, so search by the product's
        # own name (taken from its link) and pick it out by article number.
        words = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1].rsplit("-", 1)[0].replace("-", " ")
        return self._query(words)

    def parse_product(self, html, url):
        article, uom = self._article(url)
        product = next((p for p in json.loads(html).get("products") or []
                        if str(p.get("articleNumber")) == article and (p.get("unitOfMeasure") or "EA") == uom), None)
        if product is None:
            raise ExtractError("product not found at Checkers for the configured address")
        factor = product.get("priceFactor") or 100
        size = next((a.get("value") for a in product.get("attributes") or [] if a.get("name") == "Nappy Size"), None)
        fields = {
            "title": product.get("name"),
            "brand": product.get("brand"),
            "price": parse.parse_price(product.get("price")),
            "was_price": parse.parse_price((product.get("oldPrice") or 0) / factor),
            "in_stock": bool(product.get("isStockAvailable")) and not product.get("outOfStock"),
            "image_url": (f"https://catalog.sixty60.co.za/v2/files/{product['imageId']}?width=320&height=320"
                          if product.get("imageId") else None),
            "badges": ["promo"] if product.get("isOnPromotion") else [],
            "size": size if size and re.fullmatch(r"\d\+?", size) else None,
        }
        return to_page(fields, self.clean_url(url), self.store_id)

    def fetch_search(self, query):
        return self._query(query)

    def parse_search(self, html):
        hits = []
        for product in json.loads(html).get("products") or []:
            if not product.get("articleNumber") or not product.get("name"):
                continue
            url = (f"{self.base_url}/product/{slugify(product['name'])}-"
                   f"{product['articleNumber']}{product.get('unitOfMeasure') or 'EA'}")
            hits.append(SearchHit(url, product["name"], parse.parse_price(product.get("price"))))
        return hits
