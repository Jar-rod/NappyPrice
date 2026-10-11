"""Each store's adapter against saved pages. A layout change shows up here as a
failing field once the fixture is re-captured with `python -m scraper.capture`."""
import pytest

from scraper.adapters import ADAPTERS, adapter_for_url
from scraper.extract import extract_fields, make_soup
from tests.conftest import FIXTURES, load_expected

EXPECTED = load_expected()
PRODUCTS = {k: v for k, v in EXPECTED.items() if "/search." not in k}
SEARCHES = {k: v for k, v in EXPECTED.items() if "/search." in k}


@pytest.mark.parametrize("rel", sorted(PRODUCTS))
def test_product_page(rel):
    expected = PRODUCTS[rel]
    adapter = ADAPTERS[expected["store_id"]](None)
    page = adapter.parse_product((FIXTURES / rel).read_text(encoding="utf-8"), expected["url"])
    assert page.to_dict() == expected
    assert page.price and page.price > 0
    assert page.title and page.brand


@pytest.mark.parametrize("rel", sorted(SEARCHES))
def test_search_page(rel):
    expected = SEARCHES[rel]
    adapter = ADAPTERS[rel.split("/")[0]](None)
    hits = adapter.parse_search((FIXTURES / rel).read_text(encoding="utf-8"))
    assert len(hits) == expected["count"] >= 5
    assert hits[0].__dict__ == expected["first"]
    assert all(adapter.owns(h.url) for h in hits)


def test_every_store_has_a_fixture():
    covered = {rel.split("/")[0] for rel in PRODUCTS}
    assert {s for s, cls in ADAPTERS.items() if cls.active} <= covered


def test_clicks_and_dischem_have_five_pages_each():
    for store in ("clicks", "dischem"):
        assert sum(rel.startswith(store + "/") for rel in PRODUCTS) >= 5


def test_adapter_for_url():
    assert adapter_for_url("https://clicks.co.za/x/p/1").store_id == "clicks"
    assert adapter_for_url("https://www.dischem.co.za/x").store_id == "dischem"
    assert adapter_for_url("https://dischem.co.za/x").store_id == "dischem"
    assert adapter_for_url("https://evil.example/clicks.co.za") is None


def test_jsonld_leads_and_meta_fills_gaps():
    html = """<html><head>
      <meta property="og:image" content="https://x.test/a.jpg">
      <meta property="product:price:amount" content="99.00">
      <script type="application/ld+json">{"@graph": [{"@type": "Product", "name": "Huggies Gold Size 3 76s",
        "brand": {"name": "Huggies"}, "offers": {"price": "189.99", "availability": "https://schema.org/OutOfStock"}}]}
      </script></head></html>"""
    fields = extract_fields(make_soup(html))
    assert fields["price"] == 189.99           # JSON-LD wins over the meta price
    assert fields["image_url"] == "https://x.test/a.jpg"
    assert fields["in_stock"] is False


def test_falls_back_to_meta_then_selectors():
    meta_only = '<meta property="og:title" content="Thing 10s"><meta property="product:price:amount" content="50">'
    assert extract_fields(make_soup(meta_only))["price"] == 50.0
    assert extract_fields(make_soup("<b class='p'>R 12.50</b>"), lambda s: {"price": 12.5})["price"] == 12.5
    assert not extract_fields(make_soup("<p>nothing</p>")).get("price")
