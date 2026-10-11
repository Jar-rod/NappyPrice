"""Store registry. One class per store; add a store by adding it to ADAPTERS."""
from __future__ import annotations

from core import config
from scraper.adapters.base import ExtractError, StoreAdapter
from scraper.adapters.amazon import Amazon
from scraper.adapters.checkers import Checkers
from scraper.adapters.clicks import Clicks
from scraper.adapters.magento import BabiesRUs, BabyCity, DisChem
from scraper.adapters.makro import Makro
from scraper.adapters.pnp import PicknPay
from scraper.adapters.takealot import Takealot
from scraper.fetch import Fetcher

ADAPTERS: dict[str, type[StoreAdapter]] = {
    cls.store_id: cls for cls in (Clicks, DisChem, BabyCity, Makro, PicknPay, Takealot, Checkers, BabiesRUs, Amazon)
}


def store_rows() -> list[dict]:
    return [cls.store_row() for cls in ADAPTERS.values()]


def manual_only_stores() -> set[str]:
    """Stores the daily run skips; they are read only on a manual refresh."""
    return {store_id for store_id, cls in ADAPTERS.items() if cls.manual_only}


def runner() -> str:
    """Where this process is running: 'cloud' (GitHub, Streamlit) or 'home' (the Mac)."""
    return (config.get("RUNNER") or "home").lower()


def reachable(store_id: str) -> bool:
    """Whether the current runner can read this store. Some stores refuse cloud servers."""
    cls = ADAPTERS.get(store_id)
    return bool(cls) and (cls.cloud_ok or runner() != "cloud")


def home_only_stores() -> set[str]:
    return {store_id for store_id, cls in ADAPTERS.items() if not cls.cloud_ok}


def adapter_for_url(url: str) -> type[StoreAdapter] | None:
    return next((cls for cls in ADAPTERS.values() if cls.owns(url)), None)


def get_adapter(store_id: str, fetcher: Fetcher) -> StoreAdapter:
    return ADAPTERS[store_id](fetcher)


__all__ = ["ADAPTERS", "ExtractError", "StoreAdapter", "adapter_for_url", "get_adapter", "home_only_stores",
           "manual_only_stores", "reachable", "runner", "store_rows"]
