"""Database access.

Everything goes through `Repo`, which sits on a small backend with three
operations (select, insert, update). `SupabaseBackend` talks to Supabase;
`MemoryBackend` keeps rows in memory (optionally in a JSON file) so the job,
the alert rules and the app can run without a Supabase project.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from core import config

Row = dict[str, Any]
# A filter value is either a plain value (equality) or an (op, value) pair
# where op is one of: in, gte, lt, is.
Filters = dict[str, Any]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_ts(value: str | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Backend(Protocol):
    def select(self, table: str, filters: Filters | None = None, order: str | None = None,
               desc: bool = False, limit: int | None = None) -> list[Row]: ...
    def insert(self, table: str, row: Row) -> Row: ...
    def update(self, table: str, filters: Filters, values: Row) -> list[Row]: ...


# ---------------------------------------------------------------- Supabase

class SupabaseBackend:
    PAGE = 1000  # Supabase caps a select at 1000 rows

    def __init__(self, url: str, key: str):
        from supabase import create_client

        self.client = create_client(url, key)

    @staticmethod
    def _apply(query, filters: Filters | None):
        for col, value in (filters or {}).items():
            if isinstance(value, tuple):
                op, operand = value
                if op == "in":
                    query = query.in_(col, list(operand))
                elif op == "gte":
                    query = query.gte(col, operand)
                elif op == "lt":
                    query = query.lt(col, operand)
                elif op == "is":
                    query = query.is_(col, operand)
                else:
                    raise ValueError(f"unknown filter op {op}")
            else:
                query = query.eq(col, value)
        return query

    def select(self, table, filters=None, order=None, desc=False, limit=None):
        rows: list[Row] = []
        start = 0
        while True:
            query = self._apply(self.client.table(table).select("*"), filters)
            if order:
                query = query.order(order, desc=desc)
            end = start + self.PAGE - 1
            if limit is not None:
                end = min(end, limit - 1)
            page = query.range(start, end).execute().data
            rows.extend(page)
            start += len(page)
            if len(page) < self.PAGE or (limit is not None and start >= limit):
                return rows

    def insert(self, table, row):
        return self.client.table(table).insert(row).execute().data[0]

    def update(self, table, filters, values):
        return self._apply(self.client.table(table).update(values), filters).execute().data


# ------------------------------------------------------------------ Memory

_TABLES = ["stores", "products", "listings", "price_checks", "alerts_sent", "jobs"]
_SERIAL = {"price_checks", "alerts_sent"}
_DEFAULTS: dict[str, Row] = {
    "stores": {"needs_browser": False, "active": True, "muted": False,
               "consecutive_failures": 0, "last_success_at": None, "note": None},
    "products": {"brand": None, "range_name": None, "size": None, "unit_label": "nappy",
                 "alert_enabled": True, "target_unit_price": None, "active": True,
                 "created_by": None, "image_url": None},
    "listings": {"title": None, "match_score": None, "active": True},
    "price_checks": {"price": None, "unit_price": None, "was_price": None,
                     "on_special": None, "in_stock": None, "error": None},
    "alerts_sent": {"listing_id": None, "store_id": None, "episode_open": True,
                    "channel": None, "status": None, "price": None, "unit_price": None},
    "jobs": {"input": None, "status": "queued", "result": None},
}
_TIMESTAMP = {"products": "created_at", "price_checks": "checked_at",
              "alerts_sent": "sent_at", "jobs": "created_at"}


class MemoryBackend:
    def __init__(self, path: str | None = None):
        self.path = path
        self.data: dict[str, list[Row]] = {t: [] for t in _TABLES}
        self._mtime = 0.0
        self._load()

    def _load(self):
        """Re-read the file if another process (app or job) has written it."""
        if not self.path or not os.path.exists(self.path):
            return
        mtime = os.path.getmtime(self.path)
        if mtime != self._mtime:
            with open(self.path, encoding="utf-8") as f:
                self.data = {t: [] for t in _TABLES} | json.load(f)
            self._mtime = mtime

    def _save(self):
        if not self.path:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=1, default=str)
        os.replace(tmp, self.path)
        self._mtime = os.path.getmtime(self.path)

    @staticmethod
    def _match(row: Row, filters: Filters | None) -> bool:
        for col, value in (filters or {}).items():
            actual = row.get(col)
            if isinstance(value, tuple):
                op, operand = value
                if op == "in" and actual not in operand:
                    return False
                if op == "gte" and (actual is None or actual < operand):
                    return False
                if op == "lt" and (actual is None or actual >= operand):
                    return False
                if op == "is" and actual is not operand and not (operand == "null" and actual is None):
                    return False
            elif actual != value:
                return False
        return True

    def _latest_prices(self) -> list[Row]:
        active = {l["id"] for l in self.data["listings"] if l.get("active")}
        latest: dict[str, Row] = {}
        for check in self.data["price_checks"]:
            lid = check["listing_id"]
            if check.get("ok") and lid in active:
                if lid not in latest or check["checked_at"] > latest[lid]["checked_at"]:
                    latest[lid] = check
        return list(latest.values())

    def select(self, table, filters=None, order=None, desc=False, limit=None):
        self._load()
        source = self._latest_prices() if table == "latest_prices" else self.data[table]
        rows = [dict(r) for r in source if self._match(r, filters)]
        if order:
            rows.sort(key=lambda r: (r.get(order) is None, r.get(order)), reverse=desc)
        return rows[:limit] if limit is not None else rows

    def insert(self, table, row):
        self._load()
        new = dict(_DEFAULTS[table])
        if table in _TIMESTAMP:
            new[_TIMESTAMP[table]] = iso(now_utc())
        new.update(row)
        if "id" not in new:
            new["id"] = len(self.data[table]) + 1 if table in _SERIAL else str(uuid.uuid4())
        self.data[table].append(new)
        self._save()
        return dict(new)

    def update(self, table, filters, values):
        self._load()
        changed = []
        for row in self.data[table]:
            if self._match(row, filters):
                row.update(values)
                changed.append(dict(row))
        self._save()
        return changed


# -------------------------------------------------------------------- Repo

class Repo:
    def __init__(self, backend: Backend):
        self.db = backend

    # stores
    def list_stores(self, active_only: bool = False) -> list[Row]:
        return self.db.select("stores", {"active": True} if active_only else None, order="name")

    def ensure_stores(self, rows: list[Row]) -> None:
        """Insert any store the registry knows that the table does not."""
        existing = {s["id"] for s in self.db.select("stores")}
        for row in rows:
            if row["id"] not in existing:
                self.db.insert("stores", row)

    def update_store(self, store_id: str, **values) -> None:
        self.db.update("stores", {"id": store_id}, values)

    # products
    def list_products(self, active: bool | None = True) -> list[Row]:
        return self.db.select("products", None if active is None else {"active": active}, order="name")

    def get_product(self, product_id: str) -> Row | None:
        rows = self.db.select("products", {"id": product_id})
        return rows[0] if rows else None

    def insert_product(self, row: Row) -> Row:
        return self.db.insert("products", row)

    def update_product(self, product_id: str, **values) -> None:
        self.db.update("products", {"id": product_id}, values)

    # listings
    def list_listings(self, product_id: str | None = None, active_only: bool = True) -> list[Row]:
        filters: Filters = {}
        if product_id:
            filters["product_id"] = product_id
        if active_only:
            filters["active"] = True
        return self.db.select("listings", filters or None)

    def get_listing_by_url(self, url: str) -> Row | None:
        rows = self.db.select("listings", {"url": url})
        return rows[0] if rows else None

    def insert_listing(self, row: Row) -> Row:
        return self.db.insert("listings", row)

    def update_listing(self, listing_id: str, **values) -> None:
        self.db.update("listings", {"id": listing_id}, values)

    def scrapable_listings(self) -> list[Row]:
        """Active listings of active products at active stores."""
        products = {p["id"] for p in self.list_products(active=True)}
        stores = {s["id"] for s in self.list_stores(active_only=True)}
        return [l for l in self.list_listings()
                if l["product_id"] in products and l["store_id"] in stores]

    # price checks
    def insert_price_check(self, row: Row) -> Row:
        return self.db.insert("price_checks", row)

    def latest_prices(self) -> dict[str, Row]:
        """Latest successful check per active listing, keyed by listing id."""
        return {r["listing_id"]: r for r in self.db.select("latest_prices")}

    def checks_since(self, since: datetime, listing_ids: list[str] | None = None) -> list[Row]:
        filters: Filters = {"checked_at": ("gte", iso(since))}
        if listing_ids is not None:
            if not listing_ids:
                return []
            filters["listing_id"] = ("in", listing_ids)
        return self.db.select("price_checks", filters, order="checked_at")

    def last_checked_at(self) -> datetime | None:
        rows = self.db.select("price_checks", order="checked_at", desc=True, limit=1)
        return parse_ts(rows[0]["checked_at"]) if rows else None

    # alerts
    def open_episodes(self) -> list[Row]:
        return self.db.select("alerts_sent", {"episode_open": True})

    def insert_alert(self, row: Row) -> Row:
        return self.db.insert("alerts_sent", row)

    def close_episode(self, rule: str, listing_id: str | None = None, store_id: str | None = None) -> None:
        filters: Filters = {"rule": rule, "episode_open": True}
        if listing_id is not None:
            filters["listing_id"] = listing_id
        if store_id is not None:
            filters["store_id"] = store_id
        self.db.update("alerts_sent", filters, {"episode_open": False})

    def list_alerts(self, limit: int = 200) -> list[Row]:
        return self.db.select("alerts_sent", order="sent_at", desc=True, limit=limit)

    # jobs
    def insert_job(self, kind: str, input: Row | None = None) -> Row:
        return self.db.insert("jobs", {"kind": kind, "input": input or {}})

    def get_job(self, job_id: str) -> Row | None:
        rows = self.db.select("jobs", {"id": job_id})
        return rows[0] if rows else None

    def update_job(self, job_id: str, **values) -> None:
        self.db.update("jobs", {"id": job_id}, values)

    def ping(self) -> None:
        """Raise if the database cannot be reached or the key cannot read the tables."""
        for table in ("stores", "price_checks", "latest_prices"):
            self.db.select(table, limit=1)


LOCAL_DB_PATH = ".local_db.json"


class WrongKeyError(Exception):
    """SUPABASE_SERVICE_KEY holds a key that cannot read or write the tables."""


def get_repo() -> Repo:
    url, key = config.get("SUPABASE_URL"), config.get("SUPABASE_SERVICE_KEY")
    if url and key:
        # The publishable (anon) key connects without error but sees every table as
        # empty, which looks like lost data. Refuse it outright.
        if key.strip().startswith("sb_publishable_"):
            raise WrongKeyError("SUPABASE_SERVICE_KEY holds the publishable key. It needs the secret key, "
                                "which starts with sb_secret_ (Supabase: Project Settings, API Keys, Secret keys).")
        url, key = url.strip().removesuffix("/").removesuffix("/rest/v1"), key.strip()
        return Repo(SupabaseBackend(url, key))
    return Repo(MemoryBackend(config.get("LOCAL_DB_PATH", LOCAL_DB_PATH)))


def days_ago(days: int) -> datetime:
    return now_utc() - timedelta(days=days)
