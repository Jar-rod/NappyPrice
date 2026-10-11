import json

import pytest

from scraper.adapters.base import ExtractError
from scraper.adapters.checkers import Checkers, slugify

SANDTON = [{"storeId": "sandton-1"}, {"storeId": "sandton-2"}]
URL = "https://www.checkers.co.za/product/pampers-premium-care-size-3-6-10kg-diapers-60-pack-10247330EA"


class FakeFetcher:
    """Answers the two Checkers endpoints; `branch` is the store the catalogue replies for."""

    def __init__(self, branch="sandton-1"):
        self.branch = branch
        self.calls = []

    def post_json(self, url, payload, headers=None):
        self.calls.append((url, payload, headers or {}))
        if "fetch-store-contexts" in url:
            return json.dumps({"storeContexts": SANDTON})
        return json.dumps({"products": [{"articleNumber": "10247330", "storeId": self.branch, "price": 359.99,
                                         "name": "Pampers Premium Care Size 3 6-10kg Diapers 60 Pack",
                                         "brand": "Pampers", "oldPrice": 39999, "priceFactor": 100,
                                         "isOnPromotion": True, "isStockAvailable": True}]})


@pytest.fixture(autouse=True)
def fresh_contexts():
    Checkers._contexts = None
    yield
    Checkers._contexts = None


def test_reads_price_was_price_and_promotion():
    page = Checkers(FakeFetcher()).extract(URL)
    assert (page.price, page.was_price, page.on_special, page.units_per_pack, page.size) == (359.99, 399.99, True, 60, "3")


def test_sends_the_branch_cookie_and_looks_up_the_address_once():
    fetcher = FakeFetcher()
    adapter = Checkers(fetcher)
    adapter.extract(URL)
    adapter.extract(URL)
    lookups = [c for c in fetcher.calls if "fetch-store-contexts" in c[0]]
    searches = [c for c in fetcher.calls if "get-products-filter" in c[0]]
    assert len(lookups) == 1 and len(searches) == 2
    assert lookups[0][1]["address"]["city"] == "Sandton"
    assert searches[0][2]["Cookie"].startswith("storeContexts=%5B%7B%22storeId%22%3A%22sandton-1%22")
    assert searches[0][1]["filterData"]["filter"]["productListSource"]["search"] \
        == "pampers premium care size 3 6 10kg diapers 60 pack"


def test_price_from_another_branch_is_refused():
    # The site falls back to a default branch (with different prices) when the cookie is not honoured.
    with pytest.raises(ExtractError, match="different branch"):
        Checkers(FakeFetcher(branch="some-default-branch")).extract(URL)


def test_product_missing_from_results_is_an_error():
    other = URL.replace("10247330", "99999999")
    with pytest.raises(ExtractError, match="not found"):
        Checkers(FakeFetcher()).extract(other)


def test_search_builds_working_links():
    assert slugify("Pampers Premium Care Size 6 16+kg Pants 36 Pack") == "pampers-premium-care-size-6-16kg-pants-36-pack"
    [hit] = Checkers(FakeFetcher()).search("pampers premium care size 3")
    assert hit.url == URL and hit.price == 359.99


def test_single_bottle_and_multipack_share_an_article_number():
    class Formula(FakeFetcher):
        def post_json(self, url, payload, headers=None):
            if "fetch-store-contexts" in url:
                return super().post_json(url, payload, headers)
            base = {"articleNumber": "10704368", "storeId": "sandton-1", "brand": "Alula", "isStockAvailable": True}
            return json.dumps({"products": [
                {**base, "unitOfMeasure": "EA", "price": 16.99, "name": "Alula Gold Stage 1 Infant Starter Formula 200ml"},
                {**base, "unitOfMeasure": "PK1", "price": 93.99, "name": "Alula Gold Stage 1 Ready to Feed 6 x 200ml"},
            ]})

    root = "https://www.checkers.co.za/product/alula-gold-stage-1-ready-to-feed"
    assert Checkers(Formula()).extract(f"{root}-6-x-200ml-10704368PK1").price == 93.99
    assert Checkers(Formula()).extract(f"{root}-200ml-10704368EA").price == 16.99
