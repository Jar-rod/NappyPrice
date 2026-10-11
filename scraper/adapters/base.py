from __future__ import annotations

from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup

from core.models import ProductPage, SearchHit
from scraper import extract
from scraper.fetch import FetchError, Fetcher


class ExtractError(Exception):
    pass


class StoreAdapter:
    """One store. Subclasses override the parse_* and selectors hooks."""

    store_id: str
    name: str
    base_url: str
    search_url: str            # with a {q} placeholder
    needs_browser = False      # product pages need Playwright
    active = True              # False = shipped switched off, see `note`
<<<<<<< HEAD
    manual_only = False        # True = skipped by the daily run; read only on "Check now"
=======
>>>>>>> 56b44108f4cf891888894d2a762a896877c970a1
    note: str | None = None
    wait_for: str | None = None  # selector that signals a rendered page is ready
    search_wait_for: str | None = None
    search_root: str | None = None  # result-card selector, used to slim search fixtures
    fixture_ext = "html"            # "json" for stores read through a JSON endpoint

    def __init__(self, fetcher: Fetcher):
        self.fetcher = fetcher

    # ---- identity
    @classmethod
    def owns(cls, url: str) -> bool:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        return host == urlparse(cls.base_url).netloc.lower().removeprefix("www.")

    def clean_url(self, url: str) -> str:
        """Drop tracking query strings so a product has one URL."""
        return url.split("#")[0].split("?")[0]

    def absolute(self, href: str) -> str:
        return self.clean_url(urljoin(self.base_url, href))

    @classmethod
    def store_row(cls) -> dict:
        return {"id": cls.store_id, "name": cls.name, "base_url": cls.base_url,
                "search_url": cls.search_url, "needs_browser": cls.needs_browser,
                "active": cls.active, "note": cls.note}

    def slim_fixture(self, text: str) -> str:
        """Cut a JSON response down to what the adapter reads, for saving as a test fixture."""
        return text

    # ---- product pages
    def selectors(self, soup: BeautifulSoup) -> dict:
        """Store-specific CSS fallback for title, brand, price, image."""
        return {}

    def enrich(self, soup: BeautifulSoup, html: str, fields: dict) -> None:
        """Add what structured data lacks: was_price, badges, stock, pack count."""

    def parse_product(self, html: str, url: str) -> ProductPage:
        soup = extract.make_soup(html)
        fields = extract.extract_fields(soup, self.selectors)
        self.enrich(soup, html, fields)
        return extract.to_page(fields, self.clean_url(url), self.store_id)

    def fetch_product(self, url: str, browser: bool) -> str:
        return self.fetcher.render(url, self.wait_for) if browser else self.fetcher.get(url)

    def extract(self, url: str) -> ProductPage:
        page = self.parse_product(self.fetch_product(url, self.needs_browser), url)
        if page.price is None and not self.needs_browser:
            # Step 4: the same three sources again on the rendered page.
            try:
                page = self.parse_product(self.fetch_product(url, True), url)
            except FetchError:
                pass
        if page.price is None:
            raise ExtractError("no price found on page")
        return page

    # ---- search
    def parse_search(self, html: str) -> list[SearchHit]:
        return []

    def fetch_search(self, query: str) -> str:
        url = self.search_url.format(q=quote_plus(query))
        return self.fetcher.render(url, self.search_wait_for) if self.search_needs_browser else self.fetcher.get(url)

    def search(self, query: str) -> list[SearchHit]:
        seen, hits = set(), []
        for hit in self.parse_search(self.fetch_search(query)):
            if hit.url not in seen:
                seen.add(hit.url)
                hits.append(hit)
        return hits

    @property
    def search_needs_browser(self) -> bool:
        return self.needs_browser
