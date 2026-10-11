"""The home runner: reads the stores that refuse cloud servers.

Dis-Chem, Checkers and Amazon.co.za answer cloud servers with errors but read
normally from a home connection. This runs on the
Mac, started once a minute by a LaunchAgent (scripts/install-mac-runner.sh).
Each start is one short pass:

  1. report in, so the app knows the Mac is online
  2. run any job the app has queued for it ("Check now", "Retry", "Add item")
  3. once a day, after 06:45, check the home-only stores

    python -m scraper.worker            one pass
    python -m scraper.worker --daily    one pass, forcing the daily check now
"""
from __future__ import annotations

import argparse
import fcntl
import sys
import tempfile
from datetime import datetime, time as clock
from pathlib import Path

from core.jobs import HEARTBEAT_KIND, HOME_DAILY_KIND, SAST, STUCK_AFTER
from core.repo import Repo, get_repo, iso, now_utc, parse_ts
from scraper.adapters import home_only_stores, store_rows
from scraper.fetch import Fetcher
from scraper.notify import Notifier
from scraper.run import run_checks, run_job

DAILY_AT = clock(6, 45)   # South African time
LOCK = Path(tempfile.gettempdir()) / "nappy-price-watch-worker.lock"


def beat(repo: Repo, now: datetime) -> None:
    """Re-stamp the single heartbeat row."""
    rows = repo.list_jobs(HEARTBEAT_KIND, datetime(2000, 1, 1, tzinfo=SAST))
    if rows:
        repo.update_job(rows[0]["id"], created_at=iso(now), status="done")
    else:
        row = repo.insert_job(HEARTBEAT_KIND, {})
        repo.update_job(row["id"], created_at=iso(now), status="done")


def queued_home_jobs(repo: Repo, now: datetime) -> list[dict]:
    """Jobs addressed to this runner that are still waiting, oldest first. Stale ones are left alone."""
    since = now - STUCK_AFTER
    found = [job for kind in ("match", "check_now") for job in repo.list_jobs(kind, since)
             if job.get("status") == "queued" and (job.get("input") or {}).get("runner") == "home"]
    return sorted(found, key=lambda j: j["created_at"])


def daily_due(repo: Repo, now: datetime) -> bool:
    """After 06:45 South African time, and not already done (or under way) today."""
    local = now.astimezone(SAST)
    if local.time() < DAILY_AT:
        return False
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return not any(job.get("status") in ("running", "done") for job in repo.list_jobs(HOME_DAILY_KIND, midnight))


def run_daily(repo: Repo, fetcher: Fetcher, notifier: Notifier, now: datetime) -> dict:
    """Check every listing at the home-only stores and record that today's run happened."""
    stores = home_only_stores()
    listings = [l for l in repo.scrapable_listings() if l["store_id"] in stores]
    record = repo.insert_job(HOME_DAILY_KIND, {"stores": sorted(stores)})
    repo.update_job(record["id"], status="running", created_at=iso(now))
    try:
        summary = run_checks(repo, fetcher, notifier, listings, daily=True)
        repo.update_job(record["id"], status="done", result=summary)
        return summary
    except Exception as exc:
        repo.update_job(record["id"], status="failed", result={"error": str(exc)})
        raise


def one_pass(repo: Repo, fetcher: Fetcher, notifier: Notifier, now: datetime | None = None,
             force_daily: bool = False) -> dict:
    now = now or now_utc()
    beat(repo, now)
    done = {"jobs": 0, "daily": None}
    for job in queued_home_jobs(repo, now):
        print(f"{now.astimezone(SAST):%d %b %H:%M} running {job['kind']} job {job['id']}")
        run_job(repo, fetcher, notifier, job["id"])
        done["jobs"] += 1
        beat(repo, now_utc())   # stay "online" through a long job
    if force_daily or daily_due(repo, now):
        print(f"{now.astimezone(SAST):%d %b %H:%M} daily check of {', '.join(sorted(home_only_stores()))}")
        done["daily"] = run_daily(repo, fetcher, notifier, now)
        print(done["daily"])
        beat(repo, now_utc())
    return done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nappy Price Watch home runner")
    parser.add_argument("--daily", action="store_true", help="run the daily check now, whatever the time")
    args = parser.parse_args(argv)

    # Only one pass at a time: a long check must not overlap the next minute's start.
    with open(LOCK, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return 0
        try:
            repo = get_repo()
            repo.ping()
        except Exception as exc:
            print(f"Cannot reach the database: {exc}", file=sys.stderr)
            return 1
        repo.ensure_stores(store_rows())
        fetcher = Fetcher()
        try:
            one_pass(repo, fetcher, Notifier(), force_daily=args.daily)
        finally:
            fetcher.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
