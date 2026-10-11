from scraper import alerts
from scraper.run import run_checks
from tests.conftest import FakeNotifier, add_product, day


def run(repo, notifier, n, daily=True):
    return run_checks(repo, None, notifier, repo.scrapable_listings(), daily=daily, now=day(n),
                      sleep=lambda s: None)


def test_below_target_fires_once_then_stays_quiet(repo, stores, notifier):
    _, [listing] = add_product(repo, target=3.0, units=50)
    stores.set(listing["url"], 140.0)                       # R2.80 each, under the R3.00 target
    assert run(repo, notifier, 0)["alerts"] == 1
    assert len(notifier.sent) == 1                          # one bundled message...
    rows = repo.list_alerts()
    assert sorted(r["channel"] for r in rows) == ["email", "push"]   # ...logged once per channel
    assert all(r["rule"] == "below_target" and r["status"] == "sent" for r in rows)

    assert run(repo, notifier, 1)["alerts"] == 0            # still cheap next day: no repeat
    assert len(notifier.sent) == 1


def test_new_episode_alerts_again_after_condition_clears(repo, stores, notifier):
    _, [listing] = add_product(repo, target=3.0, units=50)
    stores.set(listing["url"], 140.0)
    run(repo, notifier, 0)
    stores.set(listing["url"], 200.0)                       # back to R4.00: episode ends
    assert run(repo, notifier, 1)["alerts"] == 0
    assert repo.open_episodes() == []
    stores.set(listing["url"], 140.0)                       # next special
    assert run(repo, notifier, 2)["alerts"] == 1
    assert len(notifier.sent) == 2


def test_on_special_fires_even_above_target(repo, stores, notifier):
    _, [listing] = add_product(repo, target=1.0, units=50)
    stores.set(listing["url"], 200.0, was_price=250.0, on_special=True)
    run(repo, notifier, 0)
    assert [r["rule"] for r in repo.list_alerts() if r["channel"] == "push"] == ["on_special"]
    assert "was R250.00" in notifier.sent[0]["text"]


def test_both_rules_on_one_listing_make_one_entry(repo, stores, notifier):
    _, [listing] = add_product(repo, target=3.0, units=50)
    stores.set(listing["url"], 140.0, was_price=200.0, on_special=True)
    assert run(repo, notifier, 0)["alerts"] == 1
    assert {r["rule"] for r in repo.list_alerts()} == {"below_target", "on_special"}
    assert "Below target of R3.00 and On special" in notifier.sent[0]["text"]
    # The special ends but the price stays under target: only that episode closes.
    stores.set(listing["url"], 140.0)
    assert run(repo, notifier, 1)["alerts"] == 0
    assert {e["rule"] for e in repo.open_episodes()} == {"below_target"}


def test_bigger_pack_that_hits_the_unit_target_counts(repo, stores, notifier):
    product = repo.insert_product({"name": "Pampers", "category": "nappies", "target_unit_price": 3.0})
    small = repo.insert_listing({"product_id": product["id"], "store_id": "clicks", "url": "https://clicks.test/s", "units_per_pack": 50})
    big = repo.insert_listing({"product_id": product["id"], "store_id": "dischem", "url": "https://dischem.test/b", "units_per_pack": 100})
    stores.set(small["url"], 200.0)     # R4.00 each
    stores.set(big["url"], 290.0)       # R2.90 each
    run(repo, notifier, 0)
    assert [r["listing_id"] for r in repo.list_alerts() if r["channel"] == "push"] == [big["id"]]


def test_several_hits_are_bundled_cheapest_first(repo, stores, notifier):
    _, listings = add_product(repo, store_ids=("clicks", "dischem", "babycity"), target=3.0, units=50)
    for listing, price in zip(listings, (145.0, 125.0, 135.0)):
        stores.set(listing["url"], price)
    assert run(repo, notifier, 0)["alerts"] == 3
    assert len(notifier.sent) == 1
    text = notifier.sent[0]["text"]
    assert text.index("Dischem") < text.index("Babycity") < text.index("Clicks")
    assert notifier.sent[0]["title"].startswith("3 nappy deals, cheapest R2.50")


def test_alerts_off_means_no_alert(repo, stores, notifier):
    _, [listing] = add_product(repo, target=3.0, units=50, alert_enabled=False)
    stores.set(listing["url"], 140.0)
    assert run(repo, notifier, 0)["alerts"] == 0
    assert notifier.sent == []


def test_out_of_stock_does_not_alert_until_back(repo, stores, notifier):
    _, [listing] = add_product(repo, target=3.0, units=50)
    stores.set(listing["url"], 140.0, in_stock=False)
    assert run(repo, notifier, 0)["alerts"] == 0
    stores.set(listing["url"], 140.0, in_stock=True)
    assert run(repo, notifier, 1)["alerts"] == 1


def test_failed_scrape_leaves_the_episode_open(repo, stores, notifier):
    _, [listing] = add_product(repo, target=3.0, units=50)
    stores.set(listing["url"], 140.0)
    run(repo, notifier, 0)
    stores.set(listing["url"], None)                        # store down for a day
    assert run(repo, notifier, 1) | {"health": []} == {"checked": 0, "failed": 1, "alerts": 0, "health": []}
    stores.set(listing["url"], 140.0)                       # same special, still running
    assert run(repo, notifier, 2)["alerts"] == 0
    assert len(notifier.sent) == 1


def test_if_every_send_fails_the_alert_is_retried_next_run(repo, stores):
    _, [listing] = add_product(repo, target=3.0, units=50)
    stores.set(listing["url"], 140.0)
    broken = FakeNotifier({"push": "failed", "email": "failed"})
    run(repo, broken, 0)
    assert {r["status"] for r in repo.list_alerts()} == {"failed"}
    working = FakeNotifier()
    assert run(repo, working, 1)["alerts"] == 1
    assert len(working.sent) == 1


def test_removed_item_is_not_scraped(repo, stores, notifier):
    product, [listing] = add_product(repo, target=3.0, units=50)
    stores.set(listing["url"], 140.0)
    repo.update_product(product["id"], active=False)
    assert run(repo, notifier, 0) == {"checked": 0, "failed": 0, "alerts": 0, "health": []}


def test_night_time_check_pushes_quietly(repo, stores, notifier):
    assert not alerts.is_quiet_time(day(0))                 # 06:45 SAST
    assert alerts.is_quiet_time(day(0).replace(hour=0))     # 02:45 SAST
    assert alerts.is_quiet_time(day(0).replace(hour=20))    # 22:45 SAST


def test_retries_twice_with_backoff_before_failing(repo, stores):
    from scraper.run import check_listing

    _, [listing] = add_product(repo)
    waits, calls = [], []

    class Flaky:
        def extract(self, url):
            calls.append(url)
            raise RuntimeError("timeout")

    row = check_listing(Flaky(), listing, sleep=waits.append)
    assert (len(calls), waits) == (3, [5, 20])
    assert row["ok"] is False and "timeout" in row["error"]


def test_manual_only_store_is_skipped_daily_but_read_on_check_now(repo, stores, notifier, monkeypatch):
    from scraper import run as run_module

    _, [clicks] = add_product(repo, store_ids=("clicks",), name="A")
    _, [makro] = add_product(repo, store_ids=("makro",), name="B")
    stores.set(clicks["url"], 200.0)
    stores.set(makro["url"], 200.0)
    monkeypatch.setattr(run_module.ADAPTERS["makro"], "manual_only", True, raising=False)

    assert [l["store_id"] for l in run_module.daily_listings(repo)] == ["clicks"]
    # "Check now" goes through run_job, which takes every scrapable listing.
    job = repo.insert_job("check_now", {})
    run_module.run_job(repo, None, notifier, job["id"])
    assert repo.get_job(job["id"])["result"]["checked"] == 2
    assert set(repo.latest_prices()) == {clicks["id"], makro["id"]}
