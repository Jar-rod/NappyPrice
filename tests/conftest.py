from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.models import ProductPage
from core.repo import MemoryBackend, Repo

FIXTURES = Path(__file__).parent / "fixtures"
DAY0 = datetime(2026, 10, 12, 4, 45, tzinfo=timezone.utc)  # 06:45 SAST


def day(n: int) -> datetime:
    return DAY0 + timedelta(days=n)


def load_expected() -> dict:
    return json.loads((FIXTURES / "expected.json").read_text())


class FakeNotifier:
    """Records sends instead of making them."""

    def __init__(self, results=None):
        self.sent = []
        self.results = results if results is not None else {"push": "sent", "email": "sent"}

    def send(self, title, text, html, click=None, quiet=False):
        self.sent.append({"title": title, "text": text, "html": html, "quiet": quiet})
        return dict(self.results)


class FakeStores:
    """Stands in for the adapter registry: prices are scripted per URL."""

    def __init__(self):
        self.pages: dict[str, dict | None] = {}

    def set(self, url: str, price: float | None, was_price: float | None = None,
            on_special: bool = False, in_stock: bool = True):
        self.pages[url] = None if price is None else {
            "price": price, "was_price": was_price, "on_special": on_special, "in_stock": in_stock}

    def adapter_class(self, store_id: str):
        stores = self

        class Adapter:
            def __init__(self, fetcher):
                pass

            def extract(self, url):
                page = stores.pages.get(url)
                if page is None:
                    raise RuntimeError("store is down")
                return ProductPage(url=url, store_id=store_id, **page)

        return Adapter


STORE_IDS = ["clicks", "dischem", "babycity", "makro"]


@pytest.fixture(autouse=True, scope="session")
def no_module_refresh_during_tests():
    """The app drops stale modules after a deploy. Files do not change mid-test-run, and
    dropping modules here would detach them from the objects other tests have patched."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent / "app"))
    import _bootstrap

    sys._npw_fingerprint = _bootstrap.fingerprint()


@pytest.fixture
def repo() -> Repo:
    repo = Repo(MemoryBackend())
    repo.ensure_stores([{"id": s, "name": s.title(), "base_url": f"https://{s}.test",
                         "search_url": f"https://{s}.test/?q={{q}}"} for s in STORE_IDS])
    return repo


@pytest.fixture
def stores(monkeypatch) -> FakeStores:
    fake = FakeStores()
    monkeypatch.setattr("scraper.run.ADAPTERS", {s: fake.adapter_class(s) for s in STORE_IDS})
    return fake


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


def add_product(repo: Repo, store_ids=("clicks",), target=3.0, units=50, name="Pampers Premium Care", **extra):
    product = repo.insert_product({"name": name, "brand": "Pampers", "category": "nappies", "size": "2",
                                   "target_unit_price": target, **extra})
    listings = [repo.insert_listing({"product_id": product["id"], "store_id": s,
                                     "url": f"https://{s}.test/{product['id']}", "units_per_pack": units,
                                     "title": f"{name} at {s}"}) for s in store_ids]
    return product, listings
