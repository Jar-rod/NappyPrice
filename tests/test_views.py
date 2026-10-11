from datetime import timedelta

from core.repo import iso
from core.views import dashboard_rows, history, suggested_target
from tests.conftest import add_product, day


def check(repo, listing, when, price, **extra):
    repo.insert_price_check({"listing_id": listing["id"], "ok": True, "checked_at": iso(when), "price": price,
                             "unit_price": round(price / listing["units_per_pack"], 4), **extra})


def test_dashboard_shows_cheapest_in_stock_listing_and_weekly_change(repo):
    product, (clicks, dischem) = add_product(repo, store_ids=("clicks", "dischem"), target=3.0, units=50)
    check(repo, clicks, day(0), 200.0)                       # R4.00 a week ago
    check(repo, dischem, day(0), 210.0)
    check(repo, clicks, day(7), 150.0, on_special=True)      # R3.00 today
    check(repo, dischem, day(7), 100.0, in_stock=False)      # cheaper but out of stock
    [row] = dashboard_rows(repo, now=day(7) + timedelta(hours=1))
    assert row["store_name"] == "Clicks"
    assert float(row["check"]["unit_price"]) == 3.0
    assert row["any_special"] and row["below_target"]
    assert round(row["change"], 2) == -0.25


def test_dashboard_orders_by_category_then_brand_then_size(repo):
    add_product(repo, name="Refill", category="bin_refills", size=None, brand="Angelcare")
    add_product(repo, name="Size four", size="4")
    add_product(repo, name="Newborn", size="NB")
    add_product(repo, name="Huggies two", size="2", brand="Huggies")
    add_product(repo, name="Wipes", category="wipes", size=None)
    add_product(repo, name="Gone", size="1", active=False)
    assert [r["product"]["name"] for r in dashboard_rows(repo)] \
        == ["Huggies two", "Newborn", "Size four", "Wipes", "Refill"]


def test_item_without_a_price_still_appears(repo):
    add_product(repo)
    [row] = dashboard_rows(repo)
    assert row["check"] is None and row["change"] is None


def test_history_keeps_readings_after_a_listing_is_removed(repo):
    product, (clicks, dischem) = add_product(repo, store_ids=("clicks", "dischem"), units=50)
    check(repo, clicks, day(0), 200.0)
    check(repo, dischem, day(0), 210.0)
    repo.insert_price_check({"listing_id": clicks["id"], "ok": False, "error": "down"})
    repo.update_listing(dischem["id"], active=False)
    points = history(repo, product["id"], None)
    assert sorted(p["series"] for p in points) == ["Clicks", "Dischem"]


def test_history_is_one_line_per_store_using_its_cheapest_pack(repo):
    product = repo.insert_product({"name": "Wipes", "category": "wipes"})
    small = repo.insert_listing({"product_id": product["id"], "store_id": "clicks", "url": "https://clicks.test/1", "units_per_pack": 56})
    big = repo.insert_listing({"product_id": product["id"], "store_id": "clicks", "url": "https://clicks.test/2", "units_per_pack": 224})
    check(repo, small, day(0), 56.0)     # R1.00 a wipe
    check(repo, big, day(0), 112.0)      # R0.50 a wipe
    check(repo, big, day(1), 134.4)      # R0.60 a wipe
    points = history(repo, product["id"], None)
    assert [(p["series"], p["unit_price"], p["units"]) for p in points] == [("Clicks", 0.5, 224), ("Clicks", 0.6, 224)]


def test_item_prices_are_best_first_with_out_of_stock_last(repo):
    from core.views import item_prices

    product, (clicks, dischem, babycity) = add_product(repo, store_ids=("clicks", "dischem", "babycity"), units=50)
    makro = repo.insert_listing({"product_id": product["id"], "store_id": "makro", "url": "https://makro.test/x", "units_per_pack": 50})
    check(repo, clicks, day(0), 200.0)
    check(repo, dischem, day(0), 150.0)
    check(repo, babycity, day(0), 100.0, in_stock=False)     # cheapest, but cannot be bought
    rows = item_prices(repo, product["id"])
    assert [r["store"]["id"] for r in rows] == ["dischem", "clicks", "babycity", "makro"]
    assert rows[-1]["unit_price"] is None                    # no price yet goes last


def test_suggested_target_is_15_percent_under_cheapest():
    assert suggested_target([4.0, 3.0, None]) == 2.55
    assert suggested_target([]) is None


def test_store_filter_gives_the_best_price_among_those_stores_only(repo):
    product, (clicks, dischem) = add_product(repo, store_ids=("clicks", "dischem"), units=50)
    add_product(repo, store_ids=("makro",), name="Only at Makro")
    check(repo, clicks, day(0), 100.0, on_special=True)      # cheapest overall
    check(repo, dischem, day(0), 150.0)
    [row] = dashboard_rows(repo, store_ids=["dischem"])
    assert row["store_name"] == "Dischem" and float(row["check"]["unit_price"]) == 3.0
    assert not row["any_special"] and row["store_count"] == 1          # the Clicks special does not count here
    assert len(dashboard_rows(repo, store_ids=["clicks", "dischem"])) == 1   # the Makro-only item is left out
    assert len(dashboard_rows(repo)) == 2


def test_brand_filter(repo):
    add_product(repo, name="Pampers one")
    add_product(repo, name="Huggies one", brand="Huggies")
    add_product(repo, name="No brand", brand=None)
    names = lambda **kw: [r["product"]["name"] for r in dashboard_rows(repo, **kw)]
    assert names(brands=["Huggies"]) == ["Huggies one"]
    assert names(brands=["Huggies", "Other brands"]) == ["Huggies one", "No brand"]
    assert len(names()) == 3
