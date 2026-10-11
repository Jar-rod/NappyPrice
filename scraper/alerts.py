"""Alert rules, once-per-episode dedupe and message building."""
from __future__ import annotations

import html as html_lib
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from core.models import size_word
from core.repo import Repo, parse_ts
from scraper.notify import SENT, Notifier

BELOW_TARGET, ON_SPECIAL = "below_target", "on_special"
STORE_HEALTH, MASS_FAILURE = "store_health", "mass_failure"
RULE_LABELS = {BELOW_TARGET: "Below target", ON_SPECIAL: "On special",
               STORE_HEALTH: "Store failing", MASS_FAILURE: "Scraper may be broken"}
SAST = ZoneInfo("Africa/Johannesburg")


@dataclass
class Hit:
    product: dict
    listing: dict
    store_name: str
    check: dict
    rules: list[str] = field(default_factory=list)

    @property
    def unit_price(self) -> float:
        return float(self.check["unit_price"])


def is_quiet_time(now: datetime) -> bool:
    """Night in South Africa: pushes go out silently."""
    hour = now.astimezone(SAST).hour
    return hour >= 21 or hour < 6


def conditions(product: dict, check: dict) -> dict[str, bool]:
    """Which rules hold for this reading. Out-of-stock listings never qualify."""
    available = check.get("in_stock") is not False
    target, unit = product.get("target_unit_price"), check.get("unit_price")
    return {
        BELOW_TARGET: bool(available and target is not None and unit is not None
                           and float(unit) <= float(target)),
        ON_SPECIAL: bool(available and check.get("on_special")),
    }


def evaluate(repo: Repo, since: datetime) -> list[Hit]:
    """Compare this run's readings with open episodes.

    A rule that holds with no open episode fires. A rule that no longer holds
    closes its episode, so the next special on that listing alerts again.
    Listings whose check failed this run are left as they were.
    """
    products = {p["id"]: p for p in repo.list_products(active=None)}
    stores = {s["id"]: s["name"] for s in repo.list_stores()}
    latest = repo.latest_prices()
    open_now = {(e["listing_id"], e["rule"]) for e in repo.open_episodes() if e.get("listing_id")}
    hits = []
    for listing in repo.list_listings():
        check = latest.get(listing["id"])
        product = products.get(listing["product_id"])
        if not check or not product or parse_ts(check["checked_at"]) < since:
            continue
        fired = []
        for rule, holds in conditions(product, check).items():
            is_open = (listing["id"], rule) in open_now
            if holds and not is_open and product.get("alert_enabled") and product.get("active"):
                fired.append(rule)
            elif not holds and is_open:
                repo.close_episode(rule, listing_id=listing["id"])
        if fired:
            hits.append(Hit(product, listing, stores.get(listing["store_id"], listing["store_id"]), check, fired))
    return sorted(hits, key=lambda h: h.unit_price)


def _rand(value) -> str:
    return f"R{float(value):,.2f}"


def describe(hit: Hit) -> tuple[str, list[str]]:
    """Heading and detail lines for one hit."""
    p, c = hit.product, hit.check
    unit = p.get("unit_label") or "unit"
    size = f"{size_word(p.get('category'))} {p['size']}" if p.get("size") else ""
    name = p["name"] + (f" {size}" if size and size.lower() not in p["name"].lower() else "")
    price_line = f"{_rand(c['price'])} for {hit.listing['units_per_pack']} ({_rand(hit.unit_price)} per {unit})"
    if c.get("was_price"):
        price_line += f", was {_rand(c['was_price'])}"
    rules = []
    for rule in hit.rules:
        label = RULE_LABELS[rule]
        if rule == BELOW_TARGET:
            label += f" of {_rand(p['target_unit_price'])}"
        rules.append(label)
    return f"{name} at {hit.store_name}", [price_line, " and ".join(rules), hit.listing["url"]]


def build_message(hits: list[Hit]) -> tuple[str, str, str]:
    """Title, plain text and HTML for one bundled message, cheapest first."""
    first_heading, _ = describe(hits[0])
    if len(hits) == 1:
        title = f"{first_heading}: {_rand(hits[0].unit_price)} each"
    else:
        title = f"{len(hits)} nappy deals, cheapest {_rand(hits[0].unit_price)} each"
    blocks, rows = [], []
    for hit in hits:
        heading, lines = describe(hit)
        blocks.append("\n".join([heading] + lines))
        esc = html_lib.escape
        rows.append(
            f"<p><strong>{esc(heading)}</strong><br>{esc(lines[0])}<br>{esc(lines[1])}<br>"
            f"<a href=\"{esc(lines[2])}\">Open at {esc(hit.store_name)}</a></p>")
    return title, "\n\n".join(blocks), "\n".join(rows)


def record(repo: Repo, results: dict[str, str], rule: str, listing_id: str | None = None,
           store_id: str | None = None, price=None, unit_price=None) -> None:
    """Log one row per channel. The episode opens only if something was delivered,
    so a run where every send failed tries again next time."""
    delivered = SENT in results.values()
    for channel, status in results.items():
        repo.insert_alert({"listing_id": listing_id, "store_id": store_id, "rule": rule,
                           "channel": channel, "status": status, "episode_open": delivered,
                           "price": price, "unit_price": unit_price})


def send_price_alerts(repo: Repo, notifier: Notifier, since: datetime, now: datetime) -> list[Hit]:
    hits = evaluate(repo, since)
    if not hits:
        return []
    title, text, html = build_message(hits)
    results = notifier.send(title, text, html, click=hits[0].listing["url"], quiet=is_quiet_time(now))
    for hit in hits:
        for rule in hit.rules:
            record(repo, results, rule, listing_id=hit.listing["id"], store_id=hit.listing["store_id"],
                   price=hit.check["price"], unit_price=hit.check["unit_price"])
    return hits
