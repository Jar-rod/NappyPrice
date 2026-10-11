from __future__ import annotations

import re

from core.models import SearchHit
from scraper import parse
from scraper.adapters.base import ExtractError, StoreAdapter
from scraper.extract import make_soup


class Amazon(StoreAdapter):
    """Amazon.co.za needs a real browser. If it answers with a CAPTCHA the
    check simply fails for the day; nothing here tries to get around it."""

    store_id = "amazon"
    name = "Amazon.co.za"
    base_url = "https://www.amazon.co.za"
    search_url = "https://www.amazon.co.za/s?k={q}"
    needs_browser = True
    # Read correctly from a home connection in testing, but answered repeated requests
    # with "503 Service Unavailable". Shipped off; set stores.active = true to try it.
    active = False
    note = "Amazon.co.za throttles repeated requests (503 errors), so it is off by default."
    wait_for = "#productTitle, form[action*='validateCaptcha']"
    search_wait_for = "div[data-component-type='s-search-result'], form[action*='validateCaptcha']"
    search_root = "div[data-component-type='s-search-result']"

    def clean_url(self, url):
        asin = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
        return f"{self.base_url}/dp/{asin.group(1)}" if asin else url.split("?")[0]

    def selectors(self, soup):
        def text(selector):
            node = soup.select_one(selector)
            return node.get_text(" ", strip=True) if node else None

        brand = text("#bylineInfo") or ""
        brand = re.sub(r"^(Visit the|Brand:)\s*|\s*Store$", "", brand).strip() or None
        image = soup.select_one("#landingImage")
        return {
            "title": text("#productTitle"),
            "brand": brand,
            "price": parse.parse_price(text("#corePrice_feature_div .a-price .a-offscreen")
                                       or text("#corePriceDisplay_desktop_feature_div .a-price .a-offscreen")),
            "image_url": image.get("src") if image else None,
        }

    def enrich(self, soup, html, fields):
        if soup.select_one("form[action*='validateCaptcha']"):
            raise ExtractError("blocked by a CAPTCHA")
        was = soup.select_one(".basisPrice .a-offscreen")
        if was:
            fields["was_price"] = parse.parse_price(was.get_text())
        availability = soup.select_one("#availability")
        if availability:
            text = availability.get_text(" ", strip=True).lower()
            fields["in_stock"] = not any(word in text for word in ("unavailable", "out of stock"))
        # "(6-10 kg) 120 Nappies, Airflow..." - only the part before the comma names the pack.
        if fields.get("title"):
            fields["title"] = fields["title"].split(",")[0].strip()

    def parse_search(self, html):
        hits = []
        for result in make_soup(html).select("div[data-component-type='s-search-result']"):
            asin, image = result.get("data-asin"), result.select_one("img.s-image")
            if not asin or not image or not image.get("alt"):
                continue
            price = result.select_one(".a-price .a-offscreen")
            title = re.sub(r"^Sponsored Ad\s*[-–]\s*", "", image["alt"]).split(",")[0].strip()
            hits.append(SearchHit(f"{self.base_url}/dp/{asin}", title,
                                  parse.parse_price(price.get_text()) if price else None))
        return hits
