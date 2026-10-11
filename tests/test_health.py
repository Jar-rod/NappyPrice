from tests.conftest import add_product, day
from tests.test_alerts import run


def setup_stores(repo, stores, ids):
    listings = {}
    for store_id in ids:
        _, [listing] = add_product(repo, store_ids=(store_id,), target=1.0, name=f"Item {store_id}")
        stores.set(listing["url"], 200.0)
        listings[store_id] = listing
    return listings


def health_alerts(repo):
    return [r for r in repo.list_alerts() if r["rule"] in ("store_health", "mass_failure") and r["channel"] == "push"]


def test_one_alert_after_three_failed_days_then_quiet_until_recovery(repo, stores, notifier):
    listings = setup_stores(repo, stores, ["clicks", "dischem"])
    stores.set(listings["dischem"]["url"], None)
    assert run(repo, notifier, 0)["health"] == []
    assert run(repo, notifier, 1)["health"] == []
    assert run(repo, notifier, 2)["health"] == ["store_health:dischem"]
    assert "Dischem has failed 3 days running" in notifier.sent[-1]["title"]
    assert run(repo, notifier, 3)["health"] == []           # day 4: no repeat
    assert len(health_alerts(repo)) == 1

    stores.set(listings["dischem"]["url"], 200.0)           # recovers
    run(repo, notifier, 4)
    dischem = next(s for s in repo.list_stores() if s["id"] == "dischem")
    assert dischem["consecutive_failures"] == 0 and dischem["last_success_at"]
    stores.set(listings["dischem"]["url"], None)            # breaks again later
    for n in (5, 6, 7):
        run(repo, notifier, n)
    assert len(health_alerts(repo)) == 2


def test_one_failed_store_does_not_stop_the_others(repo, stores, notifier):
    listings = setup_stores(repo, stores, ["clicks", "dischem"])
    stores.set(listings["clicks"]["url"], None)
    summary = run(repo, notifier, 0)
    assert (summary["checked"], summary["failed"]) == (1, 1)
    assert set(repo.latest_prices()) == {listings["dischem"]["id"]}


def test_three_stores_failing_on_one_day_send_a_single_alert(repo, stores, notifier):
    listings = setup_stores(repo, stores, ["clicks", "dischem", "babycity", "makro"])
    for store_id in ("clicks", "dischem", "babycity"):
        stores.set(listings[store_id]["url"], None)
    assert run(repo, notifier, 0)["health"] == ["mass_failure"]
    assert "scraper may be broken" in notifier.sent[-1]["title"]
    # Still broken on days 2 and 3: no per-store alerts, no repeat of the mass alert.
    assert run(repo, notifier, 1)["health"] == []
    assert run(repo, notifier, 2)["health"] == []
    assert len(health_alerts(repo)) == 1


def test_muted_store_raises_no_alert(repo, stores, notifier):
    listings = setup_stores(repo, stores, ["clicks", "dischem"])
    repo.update_store("dischem", muted=True)
    stores.set(listings["dischem"]["url"], None)
    for n in range(4):
        assert run(repo, notifier, n)["health"] == []


def test_check_now_does_not_count_as_a_failed_day(repo, stores, notifier):
    listings = setup_stores(repo, stores, ["clicks", "dischem"])
    stores.set(listings["dischem"]["url"], None)
    for n in range(5):
        run(repo, notifier, 0, daily=False)
    assert next(s for s in repo.list_stores() if s["id"] == "dischem")["consecutive_failures"] == 0
    assert health_alerts(repo) == []
