"""Cloud and home runners: which stores each reads, how jobs are routed, and the Mac worker."""
from datetime import datetime, timedelta, timezone

import pytest

from core import jobs
from core.jobs import HEARTBEAT_KIND, HOME_DAILY_KIND, home_runner_online, start_job
from core.repo import iso
from scraper import run as run_module
from scraper import worker
from scraper.adapters import ADAPTERS, home_only_stores, reachable
from scraper.adapters.amazon import Amazon
from scraper.adapters.base import ExtractError
from tests.conftest import add_product

# 08:00 South African time on 12 October 2026
NOW = datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setenv("RUNNER", "cloud")


def everywhere(repo, stores):
    """One product listed at two cloud-reachable stores (clicks, makro) and a home-only one (dischem)."""
    _, listings = add_product(repo, store_ids=("clicks", "dischem", "makro"), target=1.0)
    for listing in listings:
        stores.set(listing["url"], 200.0)
    return {l["store_id"]: l for l in listings}


# ---- which stores each runner reads

def test_the_stores_that_refuse_cloud_servers():
    assert home_only_stores() == {"dischem", "checkers", "amazon"}


def test_home_runner_reaches_everything_and_cloud_does_not(monkeypatch):
    assert all(reachable(s) for s in ADAPTERS)
    monkeypatch.setenv("RUNNER", "cloud")
    assert {s for s in ADAPTERS if not reachable(s)} == home_only_stores()


def test_cloud_daily_run_skips_blocked_stores_without_counting_failures(repo, stores, notifier, cloud):
    everywhere(repo, stores)
    listings = run_module.daily_listings(repo)
    assert [l["store_id"] for l in listings] == ["clicks", "makro"]
    summary = run_module.run_checks(repo, None, notifier, listings, daily=True, sleep=lambda s: None)
    assert (summary["checked"], summary["failed"], summary["health"]) == (2, 0, [])
    assert all(s["consecutive_failures"] == 0 for s in repo.list_stores())


def test_cloud_check_now_reports_the_stores_it_could_not_read(repo, stores, notifier, cloud):
    everywhere(repo, stores)
    job = repo.insert_job("check_now", {})
    run_module.run_job(repo, None, notifier, job["id"])
    result = repo.get_job(job["id"])["result"]
    assert (result["checked"], result["failed"]) == (2, 0)
    assert result["skipped_stores"] == ["Dischem"]


def test_cloud_cannot_add_from_a_blocked_stores_link(repo, cloud):
    with pytest.raises(ValueError, match="can only be read by the Mac runner"):
        run_module.run_match(repo, None, {"url": "https://www.dischem.co.za/some-product-123"})


def test_cloud_search_says_which_stores_were_not_searched(repo, cloud, monkeypatch):
    from scraper import match

    class NoHits:
        def __init__(self, fetcher):
            pass

        def search(self, query):
            return []

    monkeypatch.setattr(match, "ADAPTERS", {s: NoHits for s in ("clicks", "dischem", "babycity", "makro")})
    candidates, errors = match.find_matches(repo, None, {"title": "Pampers Premium Care Size 2", "brand": "Pampers"})
    assert set(candidates) == {"clicks", "babycity", "makro"}
    assert set(errors) == {"dischem"} and "Mac runner" in errors["dischem"]


# ---- Amazon

def test_amazon_waits_longer_than_other_stores():
    assert Amazon.min_gap == 6.0 and ADAPTERS["clicks"].min_gap == 3.0


def test_amazon_block_pages_are_named():
    with pytest.raises(ExtractError, match="throttled by Amazon"):
        Amazon(None).parse_search("<html><title>503 - Service Unavailable Error</title></html>")
    with pytest.raises(ExtractError, match="CAPTCHA"):
        Amazon(None).parse_product('<form action="/errors/validateCaptcha"></form>', "https://www.amazon.co.za/dp/B000000000")


def test_fetcher_pauses_per_store(monkeypatch):
    from scraper import fetch

    clock, sleeps = [1000.0], []
    monkeypatch.setattr(fetch.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(fetch.time, "sleep", lambda s: (sleeps.append(round(s, 1)), clock.__setitem__(0, clock[0] + s)))
    fetcher = fetch.Fetcher()
    Amazon(fetcher)                       # registers its 6-second pause
    ADAPTERS["clicks"](fetcher)
    for url in ("https://www.amazon.co.za/a", "https://www.amazon.co.za/b", "https://clicks.co.za/a", "https://clicks.co.za/b"):
        fetcher._wait(url)
    assert sleeps == [6.0, 3.0]
    fetcher.close()


def test_browser_session_is_reused_and_home_page_visited_once():
    pytest.importorskip("playwright")
    from scraper.fetch import Fetcher

    visits, contexts = [], []

    class Page:
        def goto(self, url, **kw):
            visits.append(url)

        def wait_for_timeout(self, ms):
            pass

        def wait_for_selector(self, selector, **kw):
            pass

        def content(self):
            return "<html></html>"

        def close(self):
            pass

    class Context:
        def new_page(self):
            return Page()

    class Browser:
        def new_context(self, **kw):
            contexts.append(kw)
            return Context()

        def close(self):
            pass

    class Driver:
        def stop(self):
            pass

    fetcher = Fetcher(min_gap=0)
    fetcher._browser, fetcher._playwright = Browser(), Driver()
    home = "https://www.amazon.co.za"
    fetcher.render(f"{home}/dp/A", "#x", warm_up=home)
    fetcher.render(f"{home}/dp/B", "#x", warm_up=home)
    assert len(contexts) == 1                                         # one session for the whole run
    assert visits == [home, f"{home}/dp/A", f"{home}/dp/B"]           # home page first, once
    fetcher.close()


# ---- routing jobs to a runner

def heartbeat(repo, minutes_ago):
    row = repo.insert_job(HEARTBEAT_KIND, {})
    repo.update_job(row["id"], status="done", created_at=iso(jobs.now_utc() - timedelta(minutes=minutes_ago)))


def test_job_goes_to_the_mac_when_it_is_online(repo, monkeypatch):
    started = []
    monkeypatch.setattr(jobs.subprocess, "Popen", lambda cmd, **kw: started.append(cmd))
    monkeypatch.setattr(jobs.httpx, "post", lambda *a, **kw: started.append("github"))
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    heartbeat(repo, minutes_ago=1)
    assert home_runner_online(repo)
    job = start_job(repo, "match", {"url": "https://clicks.test/x"})
    assert job["input"]["runner"] == "home" and job["status"] == "queued"
    assert started == []                                              # neither GitHub nor a subprocess


def test_job_falls_back_to_github_when_the_mac_is_offline(repo, monkeypatch):
    calls = []

    class Accepted:
        status_code = 204

    monkeypatch.setattr(jobs.httpx, "post", lambda url, **kw: (calls.append(kw["json"]["inputs"]), Accepted())[1])
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPO", "someone/repo")
    heartbeat(repo, minutes_ago=30)                                   # stale
    assert not home_runner_online(repo)
    job = start_job(repo, "match", {"url": "https://clicks.test/x"})
    assert job["input"]["runner"] == "cloud"
    assert calls == [{"mode": "match", "job_id": job["id"]}]


# ---- the Mac worker

def test_worker_reports_in_with_a_single_row(repo, stores, notifier):
    worker.one_pass(repo, None, notifier, now=NOW - timedelta(hours=3))        # 05:00, before the daily time
    worker.one_pass(repo, None, notifier, now=NOW - timedelta(hours=3) + timedelta(minutes=1))
    assert len(repo.list_jobs(HEARTBEAT_KIND, NOW - timedelta(days=1))) == 1
    assert repo.list_jobs(HOME_DAILY_KIND, NOW - timedelta(days=1)) == []


def test_worker_runs_jobs_addressed_to_it_and_leaves_the_rest(repo, stores, notifier):
    listings = everywhere(repo, stores)
    early = NOW - timedelta(hours=3)

    def queue(runner, minutes_ago):
        row = repo.insert_job("check_now", {"runner": runner})
        repo.update_job(row["id"], created_at=iso(early - timedelta(minutes=minutes_ago)))
        return row["id"]

    mine, clouds, stale = queue("home", 1), queue("cloud", 1), queue("home", 90)
    assert worker.one_pass(repo, None, notifier, now=early)["jobs"] == 1
    assert repo.get_job(mine)["status"] == "done" and repo.get_job(mine)["result"]["checked"] == 3
    assert repo.get_job(clouds)["status"] == "queued" and repo.get_job(stale)["status"] == "queued"
    assert set(repo.latest_prices()) == {l["id"] for l in listings.values()}  # the Mac reads every store


def test_worker_daily_check_covers_home_only_stores_once_a_day(repo, stores, notifier):
    listings = everywhere(repo, stores)
    assert not worker.daily_due(repo, NOW.replace(hour=4, minute=30))          # 06:30 SAST: too early
    done = worker.one_pass(repo, None, notifier, now=NOW)                      # 08:00 SAST: catches up
    assert done["daily"]["checked"] == 1
    assert set(repo.latest_prices()) == {listings["dischem"]["id"]}
    assert worker.one_pass(repo, None, notifier, now=NOW + timedelta(minutes=1))["daily"] is None
    assert worker.daily_due(repo, NOW + timedelta(days=1))                     # due again tomorrow


def test_worker_daily_failures_count_towards_store_health(repo, stores, notifier, monkeypatch):
    monkeypatch.setattr(run_module.time, "sleep", lambda s: None)     # skip the retry back-off
    listings = everywhere(repo, stores)
    stores.set(listings["dischem"]["url"], None)
    for day in range(3):
        worker.one_pass(repo, None, notifier, now=NOW + timedelta(days=day))
    dischem = next(s for s in repo.list_stores() if s["id"] == "dischem")
    assert dischem["consecutive_failures"] == 3
    assert any("Dischem has failed 3 days running" in m["title"] for m in notifier.sent)
