"""Pull product fields out of a page: JSON-LD, then meta tags, then store selectors."""
from __future__ import annotations

import json
import re
from typing import Callable

from bs4 import BeautifulSoup

from core.models import ProductPage
from scraper import parse

Fields = dict  # title, brand, price, was_price, in_stock, image_url, badges, units_per_pack, size


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _walk(node):
    """Yield every dict in a JSON-LD blob, including @graph members."""
    if isinstance(node, list):
        for item in node:
            yield from _walk(item)
    elif isinstance(node, dict):
        yield node
        yield from _walk(node.get("@graph", []))


def _is_type(item: dict, name: str) -> bool:
    kind = item.get("@type")
    return name in kind if isinstance(kind, list) else kind == name


def jsonld_items(soup: BeautifulSoup) -> list[dict]:
    items = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            items.extend(_walk(json.loads(script.string or "", strict=False)))
        except (json.JSONDecodeError, TypeError):
            continue
    return items


def _first(value):
    return value[0] if isinstance(value, list) and value else value


def _stock_from(availability: str | None) -> bool | None:
    if not availability:
        return None
    text = availability.lower()
    if "instock" in text or "in stock" in text or "limitedavailability" in text:
        return True
    if any(word in text for word in ("outofstock", "out of stock", "soldout", "discontinued")):
        return False
    return None


def from_jsonld(soup: BeautifulSoup) -> Fields:
    for item in jsonld_items(soup):
        if not _is_type(item, "Product"):
            continue
        offer = _first(item.get("offers")) or {}
        if _is_type(offer, "AggregateOffer") and "price" not in offer:
            offer = {**offer, "price": offer.get("lowPrice")}
        brand = item.get("brand")
        image = _first(item.get("image"))
        return {
            "title": item.get("name"),
            "brand": brand.get("name") if isinstance(brand, dict) else brand,
            "price": parse.parse_price(offer.get("price")),
            "in_stock": _stock_from(offer.get("availability")),
            "image_url": image.get("url") if isinstance(image, dict) else image,
        }
    return {}


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def from_meta(soup: BeautifulSoup) -> Fields:
    # A page can carry the site's og:title before the product's; take the last.
    titles = [t["content"].strip() for t in soup.find_all("meta", attrs={"property": "og:title"}) if t.get("content")]
    images = [t["content"].strip() for t in soup.find_all("meta", attrs={"property": "og:image"}) if t.get("content")]
    return {
        "title": titles[-1] if titles else None,
        "brand": _meta(soup, "product:brand", "og:brand", "brand"),
        "price": parse.parse_price(_meta(soup, "product:price:amount", "og:price:amount")),
        "in_stock": _stock_from(_meta(soup, "product:availability", "og:availability")),
        "image_url": images[-1] if images else None,
    }


def extract_fields(soup: BeautifulSoup, selectors: Callable[[BeautifulSoup], Fields] | None = None) -> Fields:
    """Try each source in order. The first with a price leads; the rest fill its gaps."""
    sources = [from_jsonld(soup), from_meta(soup), selectors(soup) if selectors else {}]
    priced = [s for s in sources if s.get("price")]
    ordered = priced + [s for s in sources if not s.get("price")]
    merged: Fields = {}
    for source in ordered:
        for key, value in source.items():
            if merged.get(key) in (None, "", []) and value not in (None, "", []):
                merged[key] = value
    return merged


def clean_title(text: str | None) -> str | None:
    if not text:
        return None
    return re.sub(r"\s+", " ", text.replace("&#039;", "'").replace("’", "'")).strip() or None


def to_page(fields: Fields, url: str, store_id: str) -> ProductPage:
    """Turn raw fields into a ProductPage, reading size and pack count from the title."""
    title = clean_title(fields.get("title"))
    brand = clean_title(fields.get("brand"))
    if title and brand and brand.lower() not in title.lower():
        title = f"{brand} {title}"
    known_brand = parse.parse_brand(title) or parse.parse_brand(brand)
    brand = known_brand or (brand.title() if brand and brand.isupper() else brand)
    price, was_price = fields.get("price"), fields.get("was_price")
    if was_price and price and was_price <= price:
        was_price = None
    return ProductPage(
        url=url,
        store_id=store_id,
        title=title,
        brand=brand,
        range_name=parse.parse_range(title, brand),
        size=fields.get("size") or parse.parse_size(title),
        units_per_pack=fields.get("units_per_pack") or parse.parse_pack_count(title),
        price=price,
        was_price=was_price,
        on_special=parse.detect_special(price, was_price, fields.get("badges")),
        in_stock=fields.get("in_stock"),
        image_url=fields.get("image_url"),
    )
