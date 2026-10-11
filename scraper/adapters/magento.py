"""Dis-Chem, Baby City and Babies R Us run the same Magento theme."""
from __future__ import annotations

from core.models import SearchHit
from scraper import parse
from scraper.adapters.base import StoreAdapter
from scraper.extract import clean_title, make_soup


class MagentoStore(StoreAdapter):
    search_root = "li.product-item"

    def selectors(self, soup):
        name = soup.select_one("h1.page-title, h1 .base")
        price = soup.select_one(".product-info-main [data-price-type='finalPrice']") \
            or soup.select_one("[data-price-type='finalPrice']")
        return {
            "title": name.get_text(" ", strip=True) if name else None,
            "price": parse.parse_price(price.get("data-price-amount")) if price else None,
        }

    def enrich(self, soup, html, fields):
        old = soup.select_one(".product-info-main [data-price-type='oldPrice']") \
            or soup.select_one(".price-box [data-price-type='oldPrice']")
        if old:
            fields["was_price"] = parse.parse_price(old.get("data-price-amount"))
        if fields.get("in_stock") is None:
            stock = soup.select_one(".product-info-main .stock")
            if stock:
                fields["in_stock"] = "unavailable" not in (stock.get("class") or [])

    def parse_search(self, html):
        hits = []
        for item in make_soup(html).select("li.product-item"):
            link = item.select_one("a.product-item-link")
            if not link or not link.get("href"):
                continue
            price = item.select_one("[data-price-type='finalPrice']")
            hits.append(SearchHit(self.absolute(link["href"]), clean_title(link.get_text(" ", strip=True)) or "",
                                  parse.parse_price(price.get("data-price-amount")) if price else None))
        return hits


class DisChem(MagentoStore):
    store_id = "dischem"
    cloud_ok = False   # answers HTTP 403 to GitHub and Streamlit servers
    name = "Dis-Chem"
    base_url = "https://www.dischem.co.za"
    search_url = "https://www.dischem.co.za/catalogsearch/result/?q={q}"


class BabyCity(MagentoStore):
    store_id = "babycity"
    name = "Baby City"
    base_url = "https://www.babycity.co.za"
    search_url = "https://www.babycity.co.za/catalogsearch/result/?q={q}"


class BabiesRUs(MagentoStore):
    store_id = "babiesrus"
    name = "Babies R Us"
    base_url = "https://www.babiesrus.co.za"
    search_url = "https://www.babiesrus.co.za/catalogsearch/result/?q={q}"
