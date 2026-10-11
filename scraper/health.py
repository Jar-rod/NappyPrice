"""Store health: count failed days, alert after three, and catch mass breakage."""
from __future__ import annotations

from datetime import datetime

from core.repo import Repo, iso
from scraper import alerts
from scraper.notify import Notifier

FAIL_DAYS = 3        # consecutive failed days before a store-health alert
MASS_THRESHOLD = 3   # stores failing on one day that suggest our scraper broke


def update(repo: Repo, notifier: Notifier, results: dict[str, list[int]], now: datetime,
           count_failures: bool = True) -> list[str]:
    """`results` maps store id to [ok count, failed count] for this run.

    Returns the alerts raised. `count_failures` is False for on-demand runs so
    pressing "Check now" several times never counts as several failed days.
    """
    stores = {s["id"]: s for s in repo.list_stores()}
    open_now = {(e.get("store_id"), e["rule"]) for e in repo.open_episodes()
                if e["rule"] in (alerts.STORE_HEALTH, alerts.MASS_FAILURE)}
    failed = []
    for store_id, (ok, bad) in results.items():
        store = stores.get(store_id)
        if not store:
            continue
        if ok:
            repo.update_store(store_id, consecutive_failures=0, last_success_at=iso(now))
            repo.close_episode(alerts.STORE_HEALTH, store_id=store_id)
        elif bad and count_failures:
            store["consecutive_failures"] = (store.get("consecutive_failures") or 0) + 1
            repo.update_store(store_id, consecutive_failures=store["consecutive_failures"])
            failed.append(store)
    if not count_failures:
        return []

    raised = []
    quiet = alerts.is_quiet_time(now)
    if len(failed) >= MASS_THRESHOLD:
        # Several stores at once points at us, not them: one alert, not one per store.
        if (None, alerts.MASS_FAILURE) not in open_now:
            names = ", ".join(sorted(s["name"] for s in failed))
            title = "Nappy Price Watch: scraper may be broken"
            text = f"{len(failed)} stores returned no prices today: {names}."
            sent = notifier.send(title, text, f"<p>{text}</p>", quiet=quiet)
            alerts.record(repo, sent, alerts.MASS_FAILURE)
            raised.append(alerts.MASS_FAILURE)
        return raised

    repo.close_episode(alerts.MASS_FAILURE)
    for store in failed:
        days = store["consecutive_failures"]
        if days < FAIL_DAYS or store.get("muted") or (store["id"], alerts.STORE_HEALTH) in open_now:
            continue
        title = f"Nappy Price Watch: {store['name']} has failed {days} days running"
        text = f"No prices from {store['name']} for {days} days. Its page layout may have changed."
        sent = notifier.send(title, text, f"<p>{text}</p>", quiet=quiet)
        alerts.record(repo, sent, alerts.STORE_HEALTH, store_id=store["id"])
        raised.append(f"{alerts.STORE_HEALTH}:{store['id']}")
    return raised
