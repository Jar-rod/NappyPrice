"""Dashboard: every watched item, cheapest price per unit first."""
import _bootstrap  # noqa: F401

import html

import streamlit as st

from app import ui
from core.jobs import refresh_used_today, used_message
from core.models import CATEGORIES
from core.views import OTHER_BRANDS, dashboard_rows

repo, user = ui.setup("Dashboard")
ui.nav(ui.HOME)
st.title("Nappy Price Watch")

CARD_CSS = """
<style>
.npw-card { display: flex; gap: 12px; align-items: flex-start; }
.npw-card > img { width: 56px; height: 56px; object-fit: contain; border-radius: 8px; background: #fff; flex: none; }
.npw-card .npw-noimg { width: 56px; height: 56px; border-radius: 8px; background: #e6f4fd; flex: none; }
.npw-name { font-weight: 600; line-height: 1.25; }
.npw-price { font-size: 1.35rem; font-weight: 700; line-height: 1.3; }
.npw-price small { font-size: .85rem; font-weight: 400; opacity: .8; }
.npw-sub { font-size: .85rem; opacity: .8; }
.npw-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
</style>
"""


def card_html(row: dict) -> str:
    product, check, listing = row["product"], row["check"], row["listing"]
    unit = product.get("unit_label") or "unit"
    image = (f'<img src="{html.escape(product["image_url"])}" alt="">' if product.get("image_url")
             else '<div class="npw-noimg"></div>')
    if check:
        others = row["store_count"] - 1
        average = (f'<div class="npw-sub">Average {ui.rand(row["average"])} per {unit}</div>'
                   if row["average"] is not None else "")
        price = (f'<div class="npw-price">{ui.rand(check["unit_price"])} <small>per {unit}</small>{ui.STAR}</div>'
                 f'<div class="npw-sub">{ui.store_html(row["store"])} · {ui.rand(check["price"])} for '
                 f'{listing["units_per_pack"]}' + (" · out of stock" if check.get("in_stock") is False else "")
                 + "</div>" + average +
                 f'<div class="npw-sub">Updated {ui.when(check["checked_at"], "%d %b, %H:%M")}'
                 + (f' · {others} other store{"s" if others != 1 else ""}' if others > 0 else "") + "</div>")
    else:
        price = '<div class="npw-sub">No price yet. It will appear after the next check.</div>'
    tags = []
    if row["any_special"]:
        tags.append('<span class="npw-tag npw-special">On special</span>')
    if row["below_target"]:
        tags.append('<span class="npw-tag npw-target">At target</span>')
    if row["change"] is not None:
        pct = row["change"] * 100
        if abs(pct) < 0.5:
            tags.append('<span class="npw-tag npw-flat">Same as last week</span>')
        else:
            arrow, cls = ("▼", "npw-target") if pct < 0 else ("▲", "npw-flat")
            tags.append(f'<span class="npw-tag {cls}">{arrow} {abs(pct):.0f}% vs last week</span>')
    return (f'<div class="npw-card">{image}<div><div class="npw-name">{html.escape(ui.product_title(product))}</div>'
            f'{price}<div class="npw-tags">{"".join(tags)}</div></div></div>')


def item_card(row: dict) -> None:
    product = row["product"]
    with st.container(border=True):
        st.html(card_html(row))
        with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
            enabled = st.toggle("Alerts", value=bool(product.get("alert_enabled")), key=f"alert_{product['id']}")
            if enabled != bool(product.get("alert_enabled")):
                repo.update_product(product["id"], alert_enabled=enabled)
                st.toast(f"Alerts {'on' if enabled else 'off'} for {ui.product_title(product)}")
            if st.button("All prices", key=f"open_{product['id']}", icon=":material/storefront:"):
                ui.open_item(product["id"])


# ---- "Check now" and the last-updated stamp
finished = ui.wait_for(repo, "check_job", "Checking prices now.")
if finished:
    result = finished.get("result") or {}
    if finished["status"] == "done":
        st.toast(f"Checked {result.get('checked', 0)} listings, {result.get('failed', 0)} failed, "
                 f"{result.get('alerts', 0)} alerts sent.")
    else:
        st.error(f"The check failed: {result.get('error', 'unknown error')}")
    del st.session_state["check_job"]

used_today = refresh_used_today(repo)
with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
    st.markdown(f"**Last updated** {ui.when(repo.last_checked_at(), '%a %d %b %Y, %H:%M')}")
    if st.button("Check now", icon=":material/refresh:",
                 disabled="check_job" in st.session_state or used_today is not None):
        ui.launch(repo, "check_now", {}, "check_job")
        st.rerun()
if used_today and "check_job" not in st.session_state:
    st.caption(used_message(used_today) + " Prices also refresh automatically every morning.")

# ---- Filters
products = repo.list_products(active=True)
listed_stores = {l["store_id"] for l in repo.list_listings()}
store_names = {s["id"]: s["name"] for s in repo.list_stores() if s["id"] in listed_stores}
brand_options = sorted({p.get("brand") or OTHER_BRANDS for p in products}, key=str.lower)
with st.container(horizontal=True, gap="small"):
    brand_filter = st.multiselect("Brand", brand_options, key="filter_brand", placeholder="All brands")
    store_filter = st.multiselect("Store", sorted(store_names, key=store_names.get), key="filter_store",
                                  format_func=store_names.get, placeholder="All stores")
alerts_only = st.toggle("Alerts on only", key="alerts_only")

rows = dashboard_rows(repo, store_ids=store_filter or None, brands=brand_filter or None)
if alerts_only:
    rows = [r for r in rows if r["product"].get("alert_enabled")]
if store_filter:
    st.caption("Showing the best price among the selected stores only.")

if not rows:
    if not products:
        st.info("Nothing is being watched yet.")
        st.page_link(ui.ADD, label="Add your first item", icon=":material/add:")
    else:
        st.info("No items match these filters.")

st.html(CARD_CSS)

# Category (collapsible) -> brand -> items. Rows arrive sorted in that order.
by_category: dict[str, dict[str, list[dict]]] = {}
for row in rows:
    brand = row["product"].get("brand") or OTHER_BRANDS
    by_category.setdefault(row["product"]["category"], {}).setdefault(brand, []).append(row)

for category, brands in by_category.items():
    count = sum(len(items) for items in brands.values())
    label = f"{CATEGORIES.get(category, category.title())} · {count} item{'s' if count != 1 else ''}"
    with st.expander(label, expanded=True, key=f"cat_{category}"):
        for brand, items in brands.items():
            st.subheader(brand)
            for row in items:
                item_card(row)

# ---- Archived
archived = repo.list_products(active=False)
if archived:
    with st.expander(f"Archived ({len(archived)})"):
        st.caption("Removed items keep their price history. Restore one to start tracking it again.")
        for product in archived:
            with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
                st.write(ui.product_title(product))
                if st.button("Restore", key=f"restore_{product['id']}"):
                    repo.update_product(product["id"], active=True)
                    st.rerun()

ui.sign_out_button()
