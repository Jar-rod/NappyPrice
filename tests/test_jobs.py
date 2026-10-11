from datetime import datetime, timedelta, timezone

import pytest

from core import jobs
from core.jobs import JobError, refresh_used_today, start_job
from core.repo import iso

# 14:00 South African time on 12 October 2026
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


def job(repo, minutes_ago=0, status="done", **job_input):
    row = repo.insert_job("check_now", job_input)
    repo.update_job(row["id"], status=status, created_at=iso(NOW - timedelta(minutes=minutes_ago)))
    return repo.get_job(row["id"])


def test_no_refresh_yet_today(repo):
    assert refresh_used_today(repo, now=NOW) is None


def test_a_finished_refresh_uses_up_the_day(repo):
    done = job(repo, minutes_ago=60)
    assert refresh_used_today(repo, now=NOW)["id"] == done["id"]
    assert jobs.used_message(done) == "Refreshed manually today at 13:00. Next manual refresh available tomorrow."


def test_day_resets_at_midnight_south_african_time(repo):
    job(repo, minutes_ago=14 * 60 + 30)                      # 23:30 SAST on the 11th: yesterday
    assert refresh_used_today(repo, now=NOW) is None
    # 00:30 SAST today is 22:30 UTC on the 11th: a different UTC date, but the same SAST day.
    early = job(repo, minutes_ago=13 * 60 + 30)
    assert refresh_used_today(repo, now=NOW)["id"] == early["id"]


def test_failed_refresh_does_not_count(repo):
    job(repo, minutes_ago=10, status="failed")
    assert refresh_used_today(repo, now=NOW) is None


def test_running_refresh_counts_but_a_stuck_one_does_not(repo):
    job(repo, minutes_ago=45, status="queued")              # never started
    assert refresh_used_today(repo, now=NOW) is None
    running = job(repo, minutes_ago=2, status="running")
    assert refresh_used_today(repo, now=NOW)["id"] == running["id"]


def test_store_retries_are_counted_per_store_and_apart_from_the_full_refresh(repo):
    retry = job(repo, minutes_ago=5, store_id="clicks")
    assert refresh_used_today(repo, now=NOW) is None                             # full refresh still available
    assert refresh_used_today(repo, store_id="clicks", now=NOW)["id"] == retry["id"]
    assert refresh_used_today(repo, store_id="dischem", now=NOW) is None
    job(repo, minutes_ago=1)                                                     # now the full refresh
    assert refresh_used_today(repo, now=NOW) is not None
    assert refresh_used_today(repo, store_id="dischem", now=NOW) is None         # retry for another store still open


def test_match_jobs_are_never_limited(repo):
    row = repo.insert_job("match", {"url": "https://clicks.test/x"})
    repo.update_job(row["id"], status="done")
    assert refresh_used_today(repo) is None


def test_start_job_refuses_a_second_refresh(repo, monkeypatch):
    started = []
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda cmd: started.append(cmd))
    monkeypatch.setenv("GITHUB_TOKEN", "")
    first = start_job(repo, "check_now", {})
    repo.update_job(first["id"], status="done")
    with pytest.raises(JobError, match="Next manual refresh available tomorrow"):
        start_job(repo, "check_now", {})
    assert len(started) == 1 and len(repo.list_jobs("check_now", NOW - timedelta(days=400))) == 1
    start_job(repo, "check_now", {"store_id": "clicks"})                         # a store retry is still allowed
    start_job(repo, "match", {"url": "https://clicks.test/x"})                   # and so is adding an item
    assert len(started) == 3
