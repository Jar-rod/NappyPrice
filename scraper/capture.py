"""Save a store page as a test fixture.

    uv run python -m scraper.capture <product-url> [<product-url> ...]
    uv run python -m scraper.capture --search <store_id> "<query>"

Pages are slimmed (styles, images and unrelated scripts removed) before they
are written to tests/fixtures/<store>/, and the parsed result is recorded in
tests/fixtures/expected.json. Check the printed values against the live page
before committing: they become what the tests expect.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, Comment

from scraper.adapters import ADAPTERS, adapter_for_url
from scraper.fetch import Fetcher

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
EXPECTED = FIXTURES / "expected.json"
# Inline scripts worth keeping: the ones adapters read prices and specs from.
KEEP_SCRIPT = re.compile(r"'price'\s*:|var imgUrl|\"availability\"|ProductSpecificationValue|__NEXT_DATA__|\"priceType\"")


def slim(html: str, keep_scripts: bool = True, root: str | None = None) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if root and soup.select(root):
        # Search pages: keep only the result cards.
        soup = BeautifulSoup("<html><body>" + "".join(str(el) for el in soup.select(root)) + "</body></html>",
                             "html.parser")
    for tag in soup.find_all(["style", "svg", "noscript", "iframe", "link", "picture", "source",
                              "nav", "header", "footer"]):
        tag.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    for script in soup.find_all("script"):
        text = script.string or ""
        if script.get("type") == "application/ld+json" or script.get("id") == "__NEXT_DATA__":
            continue
        if not keep_scripts or not KEEP_SCRIPT.search(text):
            script.decompose()
    for tag in soup.find_all(True):
        for attr in ("style", "srcset", "data-mage-init", "onclick"):
            tag.attrs.pop(attr, None)
    return re.sub(r"\n\s*\n+", "\n", str(soup))


def _slug(url: str) -> str:
    path = url.split("?")[0].rstrip("/")
    pid = re.search(r"[?&]pid=(\w+)", url)
    name = re.sub(r"[^a-z0-9]+", "-", path.split("//", 1)[-1].split("/", 1)[-1].lower()).strip("-")
    return (name[:70] + ("-" + pid.group(1).lower() if pid else "")) or "page"


def _load_expected() -> dict:
    return json.loads(EXPECTED.read_text()) if EXPECTED.exists() else {}


def _save_expected(data: dict) -> None:
    EXPECTED.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def capture_product(url: str, fetcher: Fetcher) -> None:
    cls = adapter_for_url(url)
    if cls is None:
        raise SystemExit(f"No adapter for {url}")
    adapter = cls(fetcher)
    html = adapter.fetch_product(url, adapter.needs_browser)
    html = slim(html) if adapter.fixture_ext == "html" else adapter.slim_fixture(html)
    page = adapter.parse_product(html, url)
    rel = f"{cls.store_id}/{_slug(url)}.{adapter.fixture_ext}"
    (FIXTURES / cls.store_id).mkdir(parents=True, exist_ok=True)
    (FIXTURES / rel).write_text(html, encoding="utf-8")
    expected = _load_expected()
    expected[rel] = page.to_dict()
    _save_expected(expected)
    print(f"{rel} ({len(html) // 1024} KB)\n  {page}")


def capture_search(store_id: str, query: str, fetcher: Fetcher) -> None:
    adapter = ADAPTERS[store_id](fetcher)
    raw = adapter.fetch_search(query)
    html = slim(raw, keep_scripts=False, root=adapter.search_root) if adapter.fixture_ext == "html" else adapter.slim_fixture(raw)
    hits = adapter.parse_search(html)
    rel = f"{store_id}/search.{adapter.fixture_ext}"
    (FIXTURES / store_id).mkdir(parents=True, exist_ok=True)
    (FIXTURES / rel).write_text(html, encoding="utf-8")
    expected = _load_expected()
    expected[rel] = {"query": query, "count": len(hits), "first": hits[0].__dict__ if hits else None}
    _save_expected(expected)
    print(f"{rel} ({len(html) // 1024} KB): {len(hits)} hits, first: {hits[0] if hits else None}")


def main(argv: list[str]) -> None:
    fetcher = Fetcher()
    try:
        if argv and argv[0] == "--search":
            capture_search(argv[1], argv[2], fetcher)
        else:
            for url in argv:
                try:
                    capture_product(url, fetcher)
                except Exception as exc:  # keep going; one dead link should not stop the rest
                    print(f"FAILED {url}: {exc}")
    finally:
        fetcher.close()


if __name__ == "__main__":
    main(sys.argv[1:])
