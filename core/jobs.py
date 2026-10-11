"""Start an on-demand scraper run from the app.

The app cannot run Playwright, so it writes a row to `jobs`, starts the GitHub
Actions workflow and polls the row. With no GitHub token (local development)
the scraper runs as a subprocess instead.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from core import config
from core.repo import Repo, now_utc, parse_ts

MODES = {"match": "match", "check_now": "single"}
WORKFLOW = "check.yml"
SAST = ZoneInfo("Africa/Johannesburg")
STUCK_AFTER = timedelta(minutes=30)   # a job not finished by now is treated as never having run


class JobError(Exception):
    pass


def refresh_used_today(repo: Repo, store_id: str | None = None, now: datetime | None = None) -> dict | None:
    """The job that used up today's manual refresh, or None if one is still available.

    A manual refresh is allowed once per calendar day (South African time), shared
    by everyone using the app. A full refresh and each store's retry are counted
    separately. Jobs that failed do not count, and nor does one still waiting to
    start after half an hour, so a run that never began cannot lock the day.
    The scheduled daily run is not a job and is never limited.
    """
    now = now or now_utc()
    midnight = now.astimezone(SAST).replace(hour=0, minute=0, second=0, microsecond=0)
    for job in repo.list_jobs("check_now", midnight):
        job_input = job.get("input") or {}
        same_scope = (job_input.get("store_id") == store_id) if store_id \
            else not job_input.get("store_id") and not job_input.get("product_id")
        if not same_scope or job.get("status") == "failed":
            continue
        if job.get("status") in ("queued", "running") and now - parse_ts(job["created_at"]) > STUCK_AFTER:
            continue
        return job
    return None


def used_message(job: dict) -> str:
    at = parse_ts(job["created_at"]).astimezone(SAST).strftime("%H:%M")
    return f"Refreshed manually today at {at}. Next manual refresh available tomorrow."


HEARTBEAT_KIND = "home_heartbeat"   # one row, re-stamped by the Mac runner every minute
HOME_DAILY_KIND = "home_daily"      # one row per day the Mac runner did its daily check
ONLINE_WITHIN = timedelta(minutes=4)


def home_runner_seen(repo: Repo) -> datetime | None:
    """When the Mac runner last reported in."""
    rows = repo.list_jobs(HEARTBEAT_KIND, datetime(2000, 1, 1, tzinfo=SAST))
    return parse_ts(rows[0]["created_at"]) if rows else None


def home_runner_online(repo: Repo, now: datetime | None = None) -> bool:
    seen = home_runner_seen(repo)
    return bool(seen) and (now or now_utc()) - seen <= ONLINE_WITHIN


def on_hosted_server() -> bool:
    """True on Streamlit Community Cloud, where the app's own machine is a cloud server."""
    return os.path.isdir("/mount/src")


def start_job(repo: Repo, kind: str, job_input: dict | None = None) -> dict:
    """Queue a job and hand it to a runner.

    The Mac runner takes it if it is online: it can read every store. Otherwise
    GitHub Actions runs it, covering the stores that accept cloud servers. With
    neither (local development), the scraper runs as a subprocess.
    """
    job_input = dict(job_input or {})
    if kind == "check_now":
        # Enforced here as well as on the button, so a second tab or a double tap cannot get round it.
        used = refresh_used_today(repo, store_id=job_input.get("store_id"))
        if used:
            raise JobError(used_message(used))
    if home_runner_online(repo):
        return repo.insert_job(kind, {**job_input, "runner": "home"})   # picked up within a minute
    job = repo.insert_job(kind, {**job_input, "runner": "cloud"})
    token, repo_name = config.get("GITHUB_TOKEN"), config.get("GITHUB_REPO")
    if token and repo_name:
        response = httpx.post(
            f"https://api.github.com/repos/{repo_name}/actions/workflows/{WORKFLOW}/dispatches",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"},
            json={"ref": config.get("GITHUB_REF", "main"),
                  "inputs": {"mode": MODES[kind], "job_id": str(job["id"])}},
            timeout=20,
        )
        if response.status_code >= 300:
            repo.update_job(job["id"], status="failed", result={"error": f"GitHub said {response.status_code}"})
            raise JobError(f"Could not start the job (GitHub returned {response.status_code}).")
    else:
        env = dict(os.environ, RUNNER="cloud") if on_hosted_server() else None
        subprocess.Popen([sys.executable, "-m", "scraper.run", MODES[kind], "--job-id", str(job["id"])], env=env)
    return job
