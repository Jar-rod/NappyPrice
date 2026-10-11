from __future__ import annotations

import re

from core.models import SearchHit
from scraper import parse
from scraper.adapters.base import StoreAdapter


class Clicks(StoreAdapter):
    store_id = "clicks"
    name = "Clicks"
    base_url = "https://clicks.co.za"
    search_url = "https://clicks.co.za/search?text={q}"
    search_root = ".productBlock"

    def selectors(self, soup):
        brand = soup.select_one("h1.product-category")
        name = soup.select_one("h1.product-name")
        price = soup.select_one(".price-wrap .price")
        return {
            "title": name.get_text(" ", strip=True) if name else None,
            "brand": brand.get_text(" ", strip=True) if brand else None,
            "price": parse.parse_price(price.get_text()) if price else None,
        }

    def enrich(self, soup, html, fields):
        # The analytics block carries the regular shelf price; the page shows the promo price.
        regular = re.search(r"'price'\s*:\s*\"([\d.,]+)\"", html)
        if regular:
            fields["was_price"] = parse.parse_price(regular.group(1))
        fields["badges"] = [b.get_text(" ", strip=True) for b in soup.select(".promotionBtn")]
        stock = re.search(r'"availability"\s*:\s*"https?://schema\.org/(\w+)"', html)
        if stock:
            fields["in_stock"] = stock.group(1) in ("InStock", "LimitedAvailability")
        image = re.search(r'var imgUrl\s*=\s*baseUrl\s*\+\s*"([^"]+)"', html)
        if image:
            fields["image_url"] = self.base_url + image.group(1)

    def parse_search(self, html):
        from scraper.extract import make_soup

        hits = []
        for block in make_soup(html).select(".productBlock"):
            link = block.select_one(".detailContent a[href*='/p/']") or block.select_one("a[href*='/p/']")
            name = block.select_one(".product-name")
            if not link or not name:
                continue
            brand = block.select_one("h5")
            title = " ".join(t.get_text(" ", strip=True) for t in (brand, name) if t)
            price = block.select_one(".price")
            hits.append(SearchHit(self.absolute(link["href"]), title,
                                  parse.parse_price(price.get_text()) if price else None))
        return hits
