from __future__ import annotations

import json
import re

from core.models import SearchHit
from scraper import parse
from scraper.adapters.base import StoreAdapter
from scraper.extract import jsonld_items, make_soup


def _spec(html: str, name: str) -> str | None:
    """A value from the page's embedded specification table."""
    match = re.search(r'\{"name":' + json.dumps(name) + r',"values":\["([^"]*)"', html)
    return match.group(1) if match else None


class Makro(StoreAdapter):
    store_id = "makro"
    # Read fine from GitHub Actions (though Streamlit's servers got HTTP 412), so it stays on the cloud run.
    name = "Makro"
    base_url = "https://www.makro.co.za"
    search_url = "https://www.makro.co.za/search?q={q}"

    def clean_url(self, url):
        # Makro needs the pid to pick the variant; everything else is tracking.
        base = url.split("#")[0].split("?")[0]
        pid = re.search(r"[?&]pid=([A-Z0-9]+)", url)
        return f"{base}?pid={pid.group(1)}" if pid else base

    def enrich(self, soup, html, fields):
        # Titles end in " - 3" (the size) and rarely carry the count; the spec table does.
        title = fields.get("title") or ""
        fields["title"] = re.sub(r"\s+-\s+\w{1,3}$", "", title)
        # Sellers fill "Pack of" unreliably (some repeat the nappy count there), so a
        # count in the title wins and "Pack of" only multiplies when it is a small number.
        per_pack, packs = _spec(html, "No of Diapers Per Pack"), _spec(html, "Pack of")
        if not parse.parse_pack_count(fields["title"]) and per_pack and per_pack.isdigit():
            multiple = int(packs) if packs and packs.isdigit() and int(packs) <= 6 else 1
            fields["units_per_pack"] = int(per_pack) * multiple
        size = _spec(html, "Size")
        if size and re.fullmatch(r"\d\+?", size):
            fields["size"] = "NB" if size == "0" else size
        mrp = re.search(r'"priceType":"MRP","strikeOff":true,"textStyle":null,"value":([\d.]+)', html)
        if mrp:
            fields["was_price"] = float(mrp.group(1))
        if re.search(r'"actionType":"ADD_TO_BASKET","enabled":true', html):
            fields["in_stock"] = True
        elif re.search(r"Sold Out|Out of Stock|Currently Unavailable", html, re.I):
            fields["in_stock"] = False

    def parse_search(self, html):
        hits = []
        for item in jsonld_items(make_soup(html)):
            if item.get("@type") != "ItemList":
                continue
            for entry in item.get("itemListElement", []):
                if entry.get("url") and entry.get("name"):
                    hits.append(SearchHit(self.clean_url(entry["url"]),
                                          re.sub(r"\s+-\s+\w{1,3}$", "", entry["name"])))
        return hits
