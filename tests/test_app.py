"""Smoke tests: every page renders against seeded local data, and the password gates access."""
from datetime import timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from core.repo import MemoryBackend, Repo, iso, now_utc
from scraper.adapters import store_rows

HOME = str(Path(__file__).resolve().parent.parent / "app" / "Home.py")
PAGES = [None, "pages/1_Item.py", "pages/2_Add_item.py", "pages/3_Alerts.py"]


def open_app(page=None, **state):
    app = AppTest.from_file(HOME, default_timeout=30)
    for key, value in state.items():
        app.session_state[key] = value
    app.run()
    if page:
        app.switch_page(page).run()
    return app


@pytest.fixture
def local_db(tmp_path, monkeypatch):
    import streamlit as st

    path = tmp_path / "db.json"
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "GITHUB_TOKEN", "APP_PASSWORD"):
        # Set to blank rather than removed, so values in a local .env are not picked up.
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("LOCAL_DB_PATH", str(path))
    monkeypatch.setenv("AUTH_BYPASS", "1")
    st.cache_resource.clear()
    repo = Repo(MemoryBackend(str(path)))
    repo.ensure_stores(store_rows())
    product = repo.insert_product({"name": "Pampers Premium Care", "brand": "Pampers", "category": "nappies",
                                   "size": "3", "target_unit_price": 3.5})
    for store_id, price in (("clicks", 219.99), ("dischem", 269.99)):
        listing = repo.insert_listing({"product_id": product["id"], "store_id": store_id,
                                       "url": f"https://{store_id}.test/p", "units_per_pack": 60})
        for days_back in (8, 1, 0):
            repo.insert_price_check({"listing_id": listing["id"], "ok": True, "price": price + days_back,
                                     "unit_price": round((price + days_back) / 60, 4), "on_special": days_back == 0,
                                     "checked_at": iso(now_utc() - timedelta(days=days_back))})
    repo.insert_alert({"listing_id": listing["id"], "store_id": "dischem", "rule": "on_special",
                       "channel": "push", "status": "sent", "price": 269.99, "unit_price": 4.5})
    yield repo, product
    st.cache_resource.clear()


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(local_db, page):
    repo, product = local_db
    app = open_app(page, product_id=product["id"])
    assert not app.exception, app.exception
    assert app.title


def test_dashboard_toggle_switches_alerts_off(local_db):
    repo, product = local_db
    app = open_app()
    app.toggle(key=f"alert_{product['id']}").set_value(False).run()
    assert not app.exception
    assert repo.get_product(product["id"])["alert_enabled"] is False


def test_visitor_without_the_password_sees_only_the_sign_in_form(local_db, monkeypatch):
    monkeypatch.delenv("AUTH_BYPASS")
    monkeypatch.setenv("APP_PASSWORD", "correct horse battery")
    app = open_app()
    assert [b.label for b in app.button] == ["Sign in"]
    assert not app.toggle and not app.header


def test_wrong_password_is_refused_and_right_one_opens_the_dashboard(local_db, monkeypatch):
    monkeypatch.delenv("AUTH_BYPASS")
    monkeypatch.setenv("APP_PASSWORD", "correct horse battery")
    monkeypatch.setattr("time.sleep", lambda s: None)
    app = open_app()
    app.text_input[0].set_value("guess")
    app.button[0].click().run()
    assert [e.value for e in app.error] == ["Wrong password."]
    assert not app.toggle

    app.text_input[0].set_value("correct horse battery")
    app.button[0].click().run()
    assert not app.error and app.toggle                     # dashboard is showing
    cookie = next(h.body for h in app.get("html") if "document.cookie" in h.body)
    assert "npw_auth=" in cookie and "correct horse battery" not in cookie   # a token, never the password
    app.switch_page("pages/3_Alerts.py").run()              # and stays unlocked on other pages
    assert app.title[0].value == "Alerts and health"


def test_no_password_configured_lets_nobody_in(local_db, monkeypatch):
    monkeypatch.delenv("AUTH_BYPASS")
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    app = open_app()
    assert "No password is set" in app.error[0].value
    assert not app.button and not app.toggle


def test_bypass_is_ignored_once_supabase_is_configured(local_db, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")   # AUTH_BYPASS is still 1
    monkeypatch.setenv("APP_PASSWORD", "correct horse battery")
    app = open_app()
    assert [b.label for b in app.button] == ["Sign in"]
    assert not app.toggle


def test_item_page_shows_chart_and_listings(local_db):
    repo, product = local_db
    app = open_app("pages/1_Item.py", product_id=product["id"])
    assert not app.exception
    assert app.title[0].value == "Pampers Premium Care · size 3"
    assert "Prices at 2 stores, best first" in [h.value for h in app.subheader]
    listing = next(h.body for h in app.get("html") if "npw-row" in h.body)
    assert listing.index("Clicks") < listing.index("Dis-Chem")          # cheapest store listed first
    assert listing.count("npw-star") == 1 and "google.com/s2/favicons?domain=clicks.co.za" in listing
    assert listing.index("npw-star") < listing.index("Dis-Chem")        # the gold star is on the cheapest store
    summary = next(h.body for h in app.get("html") if "npw-summary" in h.body)
    assert "<span>Cheapest</span><b>R3.67" in summary and "<span>Average</span><b>R4.08" in summary
    assert "<span>Saving</span><b>10%" in summary


def test_dashboard_groups_by_category_then_brand(local_db):
    repo, product = local_db
    repo.insert_product({"name": "Huggies Extra Care", "brand": "Huggies", "category": "nappies", "size": "2"})
    repo.insert_product({"name": "Pampers Sensitive wipes", "brand": "Pampers", "category": "wipes"})
    app = open_app()
    assert [e.label for e in app.expander] == ["Nappies · 2 items", "Wipes · 1 item"]
    assert [h.value for h in app.subheader] == ["Huggies", "Pampers", "Pampers"]


def test_remembered_device_skips_the_password(local_db, monkeypatch):
    from app import ui

    monkeypatch.delenv("AUTH_BYPASS")
    monkeypatch.setenv("APP_PASSWORD", "correct horse battery")
    monkeypatch.setattr(ui, "_remembered", lambda password: password == "correct horse battery")
    app = open_app()
    assert not app.text_input and app.toggle                # straight to the dashboard


def test_remember_token_changes_with_the_password():
    from app import ui

    assert ui._remember_token("one") != ui._remember_token("two")
    assert "one" not in ui._remember_token("one")


def test_sign_out_returns_to_the_password_page_even_with_the_cookie(local_db, monkeypatch):
    from app import ui

    monkeypatch.delenv("AUTH_BYPASS")
    monkeypatch.setenv("APP_PASSWORD", "correct horse battery")
    monkeypatch.setattr(ui, "_remembered", lambda password: True)
    app = open_app()
    next(b for b in app.button if b.label == "Sign out").click().run()
    assert [b.label for b in app.button] == ["Sign in"]
    assert any("max-age=0" in h.body for h in app.get("html"))      # cookie cleared in the browser


def test_dashboard_filters_by_brand_and_store(local_db):
    repo, product = local_db
    huggies = repo.insert_product({"name": "Huggies Extra Care", "brand": "Huggies", "category": "nappies", "size": "2"})
    listing = repo.insert_listing({"product_id": huggies["id"], "store_id": "makro", "url": "https://makro.test/h", "units_per_pack": 94})
    repo.insert_price_check({"listing_id": listing["id"], "ok": True, "price": 188.0, "unit_price": 2.0})
    app = open_app()
    brand, store = app.multiselect(key="filter_brand"), app.multiselect(key="filter_store")
    assert brand.options == ["Huggies", "Pampers"]
    assert sorted(store.options) == ["Clicks", "Dis-Chem", "Makro"]          # only stores with listings

    brand.set_value(["Huggies"]).run()
    assert [e.label for e in app.expander] == ["Nappies · 1 item"]
    assert [h.value for h in app.subheader] == ["Huggies"]

    app.multiselect(key="filter_brand").set_value([])
    app.multiselect(key="filter_store").set_value(["dischem"]).run()
    assert [h.value for h in app.subheader] == ["Pampers"]                   # Huggies is not sold at Dis-Chem
    card = next(h.body for h in app.get("html") if "npw-card" in h.body)
    assert "Dis-Chem" in card and "Clicks" not in card                       # Clicks is cheaper but filtered out

    app.multiselect(key="filter_brand").set_value(["Huggies"]).run()
    assert "No items match these filters." in [i.value for i in app.info]
