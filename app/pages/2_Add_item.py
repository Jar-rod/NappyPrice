"""Add an item: paste one link, confirm the matches found at other stores."""
import importlib

import _bootstrap

importlib.reload(_bootstrap).refresh()   # pick up newly deployed code without a restart

import streamlit as st

from app import ui
from core.items import save_item
from core.models import CATEGORIES, SIZES, UNIT_CHOICES, UNIT_LABELS, size_word
from scraper.adapters import adapter_for_url
from scraper.match import PRETICK_SCORE
from scraper.parse import unit_price

repo, user = ui.setup("Add item")
ui.nav(ui.ADD)
st.title("Add item")

stores = {s["id"]: s for s in repo.list_stores()}
JOB = "match_job"


def start_over():
    st.session_state.pop(JOB, None)


# ---- Step 1: paste a link
if JOB not in st.session_state:
    with st.form("link_form"):
        url = st.text_input("Product link", placeholder="https://clicks.co.za/...")
        category = st.selectbox("Category", list(CATEGORIES), format_func=CATEGORIES.get)
        submitted = st.form_submit_button("Find it", type="primary")
    supported = ", ".join(s["name"] for s in stores.values() if s.get("active"))
    st.caption(f"Supported stores: {supported}.")
    if submitted:
        adapter = adapter_for_url(url.strip())
        store = stores.get(adapter.store_id) if adapter else None
        if not adapter or not store:
            st.error("That link is not from a supported store.")
        elif not store.get("active"):
            st.error(f"{store['name']} is switched off: {store.get('note') or 'no reason recorded'}")
        elif repo.get_listing_by_url(adapter(None).clean_url(url.strip())):
            st.error("That link is already being tracked.")
        else:
            ui.launch(repo, "match", {"url": url.strip(), "category": category}, JOB)
            st.rerun()
    st.stop()

# ---- Step 2: wait for the scraper
job = ui.wait_for(repo, JOB, "Reading the page and searching the other stores.")
if job is None:
    st.button("Cancel", on_click=start_over)
    st.stop()
result = job.get("result") or {}
if job["status"] == "failed":
    st.error(result.get("error") or "The search failed.")
    st.button("Try another link", on_click=start_over)
    st.stop()

# ---- Step 3: check the fields, tick the matches
page = result.get("page") or {}
candidates = result.get("candidates") or {}
job_id = job["id"]
source_store = stores.get(page.get("store_id"), {}).get("name", page.get("store_id"))
category_default = page.get("category") or (job.get("input") or {}).get("category") or "nappies"

if page.get("error"):
    st.warning(f"Could not read that page ({page['error']}). Fill in the details by hand.")
elif page.get("price"):
    st.success(f"Found at {source_store}: {ui.rand(page['price'])}"
               + (f", was {ui.rand(page['was_price'])}" if page.get("was_price") else ""))

with st.form(f"confirm_{job_id}"):
    if page.get("image_url"):
        st.image(page["image_url"], width=96)
    if page.get("title"):
        st.caption(page["title"])
    default_name = " ".join(p for p in (page.get("brand"), page.get("range_name")) if p) or page.get("title") or ""
    name = st.text_input("Name", value=page.get("name") or default_name)
    brand = st.text_input("Brand", value=page.get("brand") or "")
    range_name = st.text_input("Range", value=page.get("range_name") or "")
    category = st.selectbox("Category", list(CATEGORIES), format_func=CATEGORIES.get,
                            index=list(CATEGORIES).index(category_default))
    size_options = [""] + SIZES
    size = st.selectbox(size_word(category_default).title(), size_options, format_func=lambda s: s or "None",
                        index=size_options.index(page.get("size") if page.get("size") in SIZES else ""))
    unit_default = page.get("unit_label") or UNIT_LABELS.get(category_default, "unit")
    unit_options = UNIT_CHOICES if unit_default in UNIT_CHOICES else UNIT_CHOICES + [unit_default]
    unit_label = st.selectbox("Priced per", unit_options, index=unit_options.index(unit_default),
                              help="What one unit is: a nappy, a wipe, a bottle, 100ml of fluid.")
    units = st.number_input(f"How many of those in the pack at {source_store}", min_value=0, step=1,
                            value=int(page.get("units_per_pack") or 0),
                            help="60 nappies is 60. A 500ml bottle priced per 100ml is 5.")

    picks = {}
    for store_id, found in candidates.items():
        if not found:
            continue
        st.subheader(stores.get(store_id, {}).get("name", store_id))
        for i, cand in enumerate(found):
            key = f"{job_id}_{store_id}_{i}"
            per_unit = unit_price(cand.get("price"), cand.get("units_per_pack"))
            label = f"{cand.get('title') or cand['url']}"
            detail = (f"Match {cand['score']} · {ui.rand(cand.get('price'))}"
                      + (f" · {ui.rand(per_unit)} each" if per_unit else "")
                      + (" · on special" if cand.get("on_special") else "")
                      + (" · out of stock" if cand.get("in_stock") is False else ""))
            ticked = st.checkbox(label, key=f"tick_{key}",
                                 value=cand["score"] >= PRETICK_SCORE and bool(cand.get("units_per_pack")))
            with st.container(horizontal=True, vertical_alignment="center"):
                st.caption(f"{detail} · [open]({cand['url']})")
                cand_units = st.number_input("Pack count", min_value=0, step=1, key=f"units_{key}",
                                             value=int(cand.get("units_per_pack") or 0), width=140)
            picks[key] = (ticked, cand_units, cand)
    for store_id, error in (result.get("errors") or {}).items():
        st.caption(f"{stores.get(store_id, {}).get('name', store_id)}: {error}")
    if not any(candidates.values()):
        st.caption("No matches found at other stores. You can add store listings later from the item page.")

    save = st.form_submit_button("Save item", type="primary")
    again = st.form_submit_button("Search again with these details")

st.button("Start over", on_click=start_over)

corrected = {**page, "title": page.get("title") or name, "name": name.strip(), "brand": brand.strip() or None,
             "range_name": range_name.strip() or None, "size": size or None, "category": category,
             "units_per_pack": int(units) or None, "unit_label": unit_label}
corrected.pop("error", None)

if again:
    if not (corrected["title"] or "").strip():
        st.error("Give the item a name to search for.")
    else:
        ui.launch(repo, "match", {"fields": corrected}, JOB)
        st.rerun()

if save:
    chosen = [(u, c) for ticked, u, c in picks.values() if ticked]
    if not name.strip():
        st.error("Name cannot be empty.")
    elif not units:
        st.error(f"Enter the pack count at {source_store}.")
    elif any(not u for u, _ in chosen):
        st.error("Every ticked match needs a pack count. Untick it or fill the count in.")
    else:
        entries = [{**page, "units_per_pack": int(units), "score": None}] \
            + [{**c, "units_per_pack": int(u)} for u, c in chosen]
        product = save_item(repo, corrected, entries, created_by=user)
        start_over()
        ui.open_item(product["id"])
