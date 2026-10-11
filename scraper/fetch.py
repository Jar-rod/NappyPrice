"""Polite page fetching: one shared client, a pause between hits to the same host."""
from __future__ import annotations

import time
from urllib.parse import urlparse

import httpx

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-ZA,en;q=0.9",
}
MIN_GAP_SECONDS = 3.0
DEADLINE_SECONDS = 60   # hard limit for one page, however slowly it arrives


class FetchError(Exception):
    pass


class Fetcher:
    def __init__(self, min_gap: float = MIN_GAP_SECONDS):
        self.min_gap = min_gap
        self._last_hit: dict[str, float] = {}
        self._client = httpx.Client(headers=HEADERS, follow_redirects=True, timeout=httpx.Timeout(30, connect=15))
        self._gaps: dict[str, float] = {}     # per-store pause, where a store needs longer
        self._playwright = None
        self._browser = None
        self._context = None
        self._warmed: set[str] = set()

    def set_gap(self, url: str, seconds: float) -> None:
        """Pause at least this long between requests to the store at `url`."""
        self._gaps[urlparse(url).netloc] = max(seconds, self.min_gap)

    def _wait(self, url: str) -> None:
        host = urlparse(url).netloc
        wait = self._last_hit.get(host, 0) + self._gaps.get(host, self.min_gap) - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def get(self, url: str, headers: dict | None = None, method: str = "GET") -> str:
        self._wait(url)
        started = time.monotonic()
        try:
            # Streamed so a server that trickles bytes cannot hold the run up:
            # httpx's own timeouts only bound each read, not the whole response.
            with self._client.stream(method, url, headers=headers) as response:
                if response.status_code != 200:
                    raise FetchError(f"HTTP {response.status_code}")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if time.monotonic() - started > DEADLINE_SECONDS:
                        raise FetchError(f"timed out after {DEADLINE_SECONDS}s")
                return bytes(body).decode(response.encoding or "utf-8", errors="replace")
        except httpx.HTTPError as exc:
            raise FetchError(f"{type(exc).__name__}: {exc}") from exc

    def post_json(self, url: str, payload: dict, headers: dict | None = None) -> str:
        """POST a JSON body. Uses no cookie jar, so only the cookies passed in are sent."""
        self._wait(url)
        try:
            response = httpx.post(url, json=payload, headers={**HEADERS, **(headers or {})},
                                  timeout=httpx.Timeout(DEADLINE_SECONDS, connect=15))
        except httpx.HTTPError as exc:
            raise FetchError(f"{type(exc).__name__}: {exc}") from exc
        if response.status_code != 200:
            raise FetchError(f"HTTP {response.status_code}")
        return response.text

    def render(self, url: str, wait_for: str | None = None, warm_up: str | None = None) -> str:
        """Load the page in headless Chromium and return the rendered HTML.

        One browser session is kept for the whole run, and `warm_up` (a store's
        home page) is visited once before that store's first page, so a store sees
        one visitor browsing slowly instead of a stream of brand-new sessions.
        """
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeout
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise FetchError("Playwright is not installed") from exc
        try:
            if self._browser is None:
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(headless=True)
            if self._context is None:
                self._context = self._browser.new_context(user_agent=USER_AGENT, locale="en-ZA",
                                                          viewport={"width": 1280, "height": 900})
            page = self._context.new_page()
            try:
                host = urlparse(url).netloc
                if warm_up and host not in self._warmed:
                    self._wait(warm_up)
                    page.goto(warm_up, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(2500)
                    self._warmed.add(host)
                self._wait(url)
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                if wait_for:
                    try:
                        page.wait_for_selector(wait_for, timeout=20000)
                    except PlaywrightTimeout:
                        pass   # hand back whatever loaded; the adapter says what kind of page it is
                else:
                    page.wait_for_timeout(4000)
                return page.content()
            finally:
                page.close()
        except PlaywrightError as exc:
            raise FetchError(f"browser: {str(exc).splitlines()[0]}") from exc

    def close(self) -> None:
        self._client.close()
        if self._browser is not None:
            self._browser.close()
            self._playwright.stop()
            self._browser = self._playwright = self._context = None
            self._warmed.clear()
