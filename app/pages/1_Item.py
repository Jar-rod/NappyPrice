"""Item detail: price history, current listings, and editing."""
import importlib

import _bootstrap

importlib.reload(_bootstrap).refresh()   # pick up newly deployed code without a restart

import html

import streamlit as st

from app import ui
from app.charts import history_chart
from core.models import CATEGORIES, SIZES, UNIT_CHOICES, size_word
from core.views import average, history, item_prices
from scraper.adapters import adapter_for_url

repo, user = ui.setup("Item")
ui.nav(ui.ITEM)

product_id = st.query_params.get("id") or st.session_state.get("product_id")
product = repo.get_product(product_id) if product_id else None
if not product:
    st.info("Pick an item on the dashboard to see its price history.")
    st.stop()
st.session_state["product_id"] = product["id"]
st.query_params["id"] = product["id"]

unit = product.get("unit_label") or "unit"
stores = {s["id"]: s for s in repo.list_stores()}
listings = repo.list_listings(product["id"])
prices = item_prices(repo, product["id"])

st.title(ui.product_title(product))
if not product.get("active"):
    st.warning("This item is not tracked, so it is not being checked. Its price history is kept.")
    if st.button("Track again", icon=":material/visibility:"):
        repo.update_product(product["id"], active=True)
        st.rerun()

# ---- Every store, best price first
PRICES_CSS = """
<style>
.npw-row { display: flex; justify-content: space-between; gap: 12px; padding: 10px 2px; border-bottom: 1px solid #d9eefb; }
.npw-row:last-child { border-bottom: none; }
.npw-row .npw-left { min-width: 0; }
.npw-row .npw-storeline { font-weight: 600; }
.npw-row .npw-sub { font-size: .82rem; opacity: .8; overflow-wrap: anywhere; }
.npw-row .npw-right { text-align: right; flex: none; }
.npw-row .npw-unit { font-size: 1.15rem; font-weight: 700; white-space: nowrap; }
.npw-row .npw-unit small { font-size: .75rem; font-weight: 400; opacity: .8; }
.npw-row a { font-size: .82rem; }
.npw-row.npw-out { opacity: .55; }
</style>
"""


def price_row(rank: int, row: dict) -> str:
    listing, check = row["listing"], row["check"]
    esc = html.escape
    tags = []
    star = ui.STAR if rank == 0 and row["unit_price"] is not None and not row["stale"] else ""
    if row["stale"]:
        tags.append('<span class="npw-tag npw-flat">Not refreshed recently</span>')
    if check and check.get("on_special"):
        tags.append('<span class="npw-tag npw-special">On special</span>')
    if check and check.get("in_stock") is False:
        tags.append('<span class="npw-tag npw-flat">Out of stock</span>')
    if check:
        right = (f'<div class="npw-unit">{ui.rand(row["unit_price"])} <small>per {esc(unit)}</small></div>'
                 f'<div class="npw-sub">{ui.rand(check["price"])} for {listing["units_per_pack"]}'
                 + (f' · was {ui.rand(check["was_price"])}' if check.get("was_price") else "") + "</div>")
        updated = f'Updated {ui.when(check["checked_at"], "%d %b, %H:%M")}'
    else:
        right = '<div class="npw-sub">No price yet</div>'
        updated = "Not checked yet"
    out = " npw-out" if (check and check.get("in_stock") is False) or row["stale"] else ""
    return (f'<div class="npw-row{out}"><div class="npw-left">'
            f'<div class="npw-storeline">{ui.store_html(row["store"])}{star} {" ".join(tags)}</div>'
            f'<div class="npw-sub">{esc(listing.get("title") or "")}</div>'
            f'<div class="npw-sub">{updated} · <a href="{esc(listing["url"])}" target="_blank">Open at store</a></div>'
            f'</div><div class="npw-right">{right}</div></div>')


checked = [r["check"]["checked_at"] for r in prices if r["check"]]
st.subheader(f"Prices at {len({r['store']['id'] for r in prices})} stores, best first")
in_stock_units = [r["unit_price"] for r in prices
                  if r["unit_price"] is not None and not r["stale"] and r["check"].get("in_stock") is not False]
if len(in_stock_units) > 1:
    best, mean = min(in_stock_units), average(in_stock_units)
    # One compact line: three large tiles would push the price list off a phone screen.
    st.html('<div class="npw-summary">'
            f'<div><span>Cheapest</span><b>{ui.rand(best)}{ui.STAR}</b></div>'
            f'<div><span>Average</span><b>{ui.rand(mean)}</b></div>'
            f'<div><span>Saving</span><b>{(1 - best / mean) * 100:.0f}%</b></div></div>')
if checked:
    st.caption(f"Last updated {ui.when(max(checked), '%a %d %b %Y, %H:%M')}"
               + (" · average is across every in-stock listing" if len(in_stock_units) > 1 else ""))
if prices:
    with st.container(border=True):
        st.html(PRICES_CSS + "".join(price_row(i, r) for i, r in enumerate(prices)))
else:
    st.caption("No store listings yet. Add one below.")

# ---- History
st.subheader("Price history")
RANGES = {"30 days": 30, "90 days": 90, "All": None}
choice = st.segmented_control("Period", list(RANGES), default="30 days", label_visibility="collapsed") or "30 days"
points = history(repo, product["id"], RANGES[choice])
if points:
    target = float(product["target_unit_price"]) if product.get("target_unit_price") is not None else None
    st.plotly_chart(history_chart(points, unit, target, dark=False), theme=None,
                    config={"displayModeBar": False, "scrollZoom": False},
                    alt=f"Cheapest price per {unit} at each store over time, one coloured line per store")
    st.caption("One line per store, showing its cheapest pack that day.")
else:
    st.info("No prices in this period yet.")

# ---- Alerts and target
st.subheader("Alert")
with st.form("alert_form"):
    enabled = st.toggle("Alerts on", value=bool(product.get("alert_enabled")))
    target_value = st.number_input(f"Target price per {unit} (R)", min_value=0.0, step=0.05, format="%.2f",
                                   value=float(product.get("target_unit_price") or 0.0),
                                   help="You are alerted when any store is at or below this. Set 0 for no target.")
    if st.form_submit_button("Save alert", type="primary"):
        repo.update_product(product["id"], alert_enabled=enabled, target_unit_price=target_value or None)
        st.toast("Alert saved")
        st.rerun()

# ---- Edit details
with st.expander("Edit details"):
    with st.form("details_form"):
        name = st.text_input("Name", value=product["name"])
        brand = st.text_input("Brand", value=product.get("brand") or "")
        range_name = st.text_input("Range", value=product.get("range_name") or "")
        category = st.selectbox("Category", list(CATEGORIES), format_func=CATEGORIES.get,
                                index=list(CATEGORIES).index(product["category"]))
        size_options = [""] + SIZES
        size = st.selectbox(size_word(product["category"]).title(), size_options, format_func=lambda s: s or "None",
                            index=size_options.index(product.get("size") if product.get("size") in SIZES else ""))
        units_list = UNIT_CHOICES if unit in UNIT_CHOICES else UNIT_CHOICES + [unit]
        unit_choice = st.selectbox("Priced per", units_list, index=units_list.index(unit),
                                   help="What one unit is: a nappy, a wipe, a bottle, 100ml of fluid.")
        st.caption("Pack count per store. Price per unit is the pack price divided by this.")
        packs = {l["id"]: st.number_input(stores.get(l["store_id"], {}).get("name", l["store_id"]),
                                          min_value=1, step=1, value=int(l["units_per_pack"]), key=f"units_{l['id']}")
                 for l in listings}
        if st.form_submit_button("Save details"):
            if not name.strip():
                st.error("Name cannot be empty.")
            else:
                repo.update_product(product["id"], name=name.strip(), brand=brand.strip() or None,
                                    range_name=range_name.strip() or None, category=category,
                                    size=size or None, unit_label=unit_choice)
                for listing in listings:
                    if packs[listing["id"]] != listing["units_per_pack"]:
                        repo.update_listing(listing["id"], units_per_pack=int(packs[listing["id"]]))
                st.toast("Details saved")
                st.rerun()

# ---- Store listings
with st.expander("Add or remove a store listing"):
    for listing in listings:
        with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
            st.write(f"{stores.get(listing['store_id'], {}).get('name', listing['store_id'])} · "
                     f"pack of {listing['units_per_pack']}")
            if st.button("Remove", key=f"rm_{listing['id']}"):
                repo.update_listing(listing["id"], active=False)
                st.rerun()
    with st.form("add_listing", clear_on_submit=True):
        url = st.text_input("Product link from a supported store")
        units = st.number_input(f"Pack count ({unit}s in the pack)", min_value=1, step=1, value=1)
        if st.form_submit_button("Add listing"):
            adapter = adapter_for_url(url.strip())
            store = stores.get(adapter.store_id) if adapter else None
            if not adapter or not store:
                st.error("That link is not from a supported store.")
            elif not store.get("active"):
                st.error(f"{store['name']} is switched off: {store.get('note') or 'no reason recorded'}")
            else:
                clean = adapter(None).clean_url(url.strip())
                existing = repo.get_listing_by_url(clean)
                if existing and existing["product_id"] != product["id"]:
                    st.error("That link is already tracked under another item.")
                elif existing:
                    repo.update_listing(existing["id"], active=True, units_per_pack=int(units))
                    st.rerun()
                else:
                    repo.insert_listing({"product_id": product["id"], "store_id": adapter.store_id, "url": clean,
                                         "units_per_pack": int(units)})
                    st.toast("Listing added. Its price appears after the next check.")
                    st.rerun()

# ---- Stop tracking
@st.dialog("Stop tracking this item?")
def confirm_remove():
    st.write(f"**{ui.product_title(product)}** will stop being checked. Its price history is kept, "
             "and you can track it again from Not tracked on the dashboard.")
    with st.container(horizontal=True):
        if st.button("Stop tracking", type="primary", key="confirm_stop"):
            repo.update_product(product["id"], active=False)
            st.session_state.pop("product_id", None)
            st.switch_page(ui.HOME)
        if st.button("Cancel"):
            st.rerun()


if product.get("active") and st.button("Stop tracking", icon=":material/visibility_off:"):
    confirm_remove()
