"""Entry point.

    python -m scraper.run daily [--dry-run]     scheduled check of every listing
    python -m scraper.run match --job-id ID     add-item: extract a link, search other stores
    python -m scraper.run single --job-id ID    "Check now" for everything, one item or one store
    python -m scraper.run extract URL [URL...]  print what a product page gives (debugging)
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime

from core.repo import Repo, get_repo, iso, now_utc
from scraper import alerts, health, match, parse
from scraper.adapters import ADAPTERS, adapter_for_url, reachable, store_rows
from scraper.fetch import Fetcher
from scraper.notify import Notifier

RETRY_WAITS = (5, 20)  # seconds before the second and third attempt


def check_listing(adapter, listing: dict, sleep=None) -> dict:
    """Scrape one listing with retries. Returns a price_checks row (not yet saved)."""
    sleep = sleep or time.sleep
    error = "unknown"
    for attempt in range(len(RETRY_WAITS) + 1):
        if attempt:
            sleep(RETRY_WAITS[attempt - 1])
        try:
            page = adapter.extract(listing["url"])
            return {"listing_id": listing["id"], "ok": True, "price": page.price,
                    "unit_price": parse.unit_price(page.price, listing["units_per_pack"]),
                    "was_price": page.was_price, "on_special": page.on_special,
                    "in_stock": page.in_stock}
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:300]
    return {"listing_id": listing["id"], "ok": False, "error": error}


def check_listings(repo: Repo, fetcher: Fetcher, listings: list[dict], write: bool = True,
                   sleep=None, stamp: datetime | None = None) -> dict[str, list[int]]:
    """Check listings one store at a time. A failing store never stops the others.

    Returns {store_id: [ok count, failed count]}.
    """
    by_store = defaultdict(list)
    for listing in listings:
        by_store[listing["store_id"]].append(listing)
    results: dict[str, list[int]] = {}
    for store_id, group in by_store.items():
        results[store_id] = [0, 0]
        if store_id not in ADAPTERS:
            continue
        adapter = ADAPTERS[store_id](fetcher)
        for listing in group:
            row = check_listing(adapter, listing, sleep)
            results[store_id][0 if row["ok"] else 1] += 1
            if write:
                # Every reading in a run carries the run's start time.
                repo.insert_price_check(row | ({"checked_at": iso(stamp)} if stamp else {}))
            status = (f"R{row['price']:.2f} / R{row['unit_price']:.2f} each"
                      + (" SPECIAL" if row["on_special"] else "")) if row["ok"] else f"FAILED {row['error']}"
            print(f"{store_id:10} {status:38} {listing.get('title') or listing['url']}")
    return results


def run_checks(repo: Repo, fetcher: Fetcher, notifier: Notifier, listings: list[dict], *,
               daily: bool, dry_run: bool = False, now: datetime | None = None, sleep=None) -> dict:
    started = now or now_utc()
    results = check_listings(repo, fetcher, listings, write=not dry_run, sleep=sleep, stamp=started)
    summary = {"checked": sum(r[0] for r in results.values()),
               "failed": sum(r[1] for r in results.values()), "alerts": 0, "health": []}
    if not dry_run:
        summary["alerts"] = len(alerts.send_price_alerts(repo, notifier, since=started, now=started))
        summary["health"] = health.update(repo, notifier, results, started, count_failures=daily)
    return summary


def daily_listings(repo: Repo) -> list[dict]:
    """What this runner's scheduled run checks.

    Manual-only stores are always left out. On a cloud runner, so are the stores
    that refuse cloud servers; the home runner reads those (see scraper/worker.py).
    """
    skip = {store_id for store_id, cls in ADAPTERS.items() if getattr(cls, "manual_only", False)}
    return [l for l in repo.scrapable_listings() if l["store_id"] not in skip and reachable(l["store_id"])]


def unreachable_names(repo: Repo, listings: list[dict]) -> list[str]:
    """Names of stores in `listings` that this runner cannot read."""
    names = {s["id"]: s["name"] for s in repo.list_stores()}
    return sorted({names.get(l["store_id"], l["store_id"]) for l in listings if not reachable(l["store_id"])})


def run_match(repo: Repo, fetcher: Fetcher, job_input: dict) -> dict:
    """Extract the pasted link (or take corrected fields) and search the other stores."""
    if job_input.get("url"):
        cls = adapter_for_url(job_input["url"])
        if cls is None:
            raise ValueError("That link is not from a supported store.")
        if not reachable(cls.store_id):
            raise ValueError(f"{cls.name} can only be read by the Mac runner, which is offline. "
                             "Try again when the Mac is on.")
        adapter = cls(fetcher)
        url = adapter.clean_url(job_input["url"])
        if repo.get_listing_by_url(url):
            raise ValueError("That link is already being tracked.")
        try:
            page = adapter.extract(url).to_dict()
        except Exception as exc:
            # Unreadable page: hand back blanks for the user to fill in.
            page = {"url": url, "store_id": cls.store_id, "error": f"{type(exc).__name__}: {exc}"}
        target = match.target_from_page(page, job_input.get("category") or "nappies")
        # Hand the category's reading of the page (stage, bottles, per-100ml units) back to the form.
        page = {**page, **{k: target.get(k) for k in ("size", "units_per_pack", "category")},
                "unit_label": parse.unit_label_for(target["category"], target.get("title"))}
    else:
        page = job_input["fields"]
        # Fields the user corrected are taken as given, not re-read from the title.
        target = {**page, "category": page.get("category") or "nappies"}
    candidates, errors = ({}, {})
    if target.get("title"):
        candidates, errors = match.find_matches(repo, fetcher, target, skip_store=target.get("store_id"))
    return {"page": page, "candidates": candidates, "errors": errors}


def run_job(repo: Repo, fetcher: Fetcher, notifier: Notifier, job_id: str) -> None:
    job = repo.get_job(job_id)
    if job is None:
        raise SystemExit(f"job {job_id} not found")
    repo.update_job(job_id, status="running")
    try:
        job_input = job.get("input") or {}
        if job["kind"] == "match":
            result = run_match(repo, fetcher, job_input)
        else:
            listings = repo.scrapable_listings()
            if job_input.get("product_id"):
                listings = [l for l in listings if l["product_id"] == job_input["product_id"]]
            if job_input.get("store_id"):
                listings = [l for l in listings if l["store_id"] == job_input["store_id"]]
            skipped = unreachable_names(repo, listings)
            result = run_checks(repo, fetcher, notifier, [l for l in listings if reachable(l["store_id"])],
                                daily=False)
            result["skipped_stores"] = skipped   # stores this runner cannot read
        repo.update_job(job_id, status="done", result=result)
    except Exception as exc:
        traceback.print_exc()
        repo.update_job(job_id, status="failed", result={"error": str(exc)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nappy Price Watch scraper")
    parser.add_argument("mode", choices=["daily", "match", "single", "extract"])
    parser.add_argument("urls", nargs="*")
    parser.add_argument("--job-id")
    parser.add_argument("--dry-run", action="store_true", help="scrape and print; write and send nothing")
    args = parser.parse_args(argv)

    fetcher = Fetcher()
    try:
        if args.mode == "extract":
            for url in args.urls:
                cls = adapter_for_url(url)
                print(cls(fetcher).extract(url) if cls else f"no adapter for {url}")
            return 0

        repo = get_repo()
        try:
            repo.ping()
        except Exception as exc:
            # Fail loudly: GitHub emails the repo owner when a scheduled run fails.
            print(f"Cannot reach the database: {exc}", file=sys.stderr)
            return 1
        repo.ensure_stores(store_rows())
        notifier = Notifier(dry_run=args.dry_run)

        if args.mode == "daily":
            summary = run_checks(repo, fetcher, notifier, daily_listings(repo),
                                 daily=True, dry_run=args.dry_run)
            print(summary)
        else:
            if not args.job_id:
                parser.error(f"{args.mode} needs --job-id")
            run_job(repo, fetcher, notifier, args.job_id)
        return 0
    finally:
        fetcher.close()


if __name__ == "__main__":
    sys.exit(main())
