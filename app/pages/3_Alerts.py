"""Alert log and store health."""
import _bootstrap  # noqa: F401

import streamlit as st

from app import ui
from scraper.alerts import RULE_LABELS

repo, user = ui.setup("Alerts and health")
ui.nav(ui.ALERTS)
st.title("Alerts and health")

stores = {s["id"]: s for s in repo.list_stores()}
listings = {l["id"]: l for l in repo.list_listings(active_only=False)}
products = {p["id"]: p for p in repo.list_products(active=None)}

# ---- Store health
st.header("Store health", divider="gray")
finished = ui.wait_for(repo, "retry_job", "Retrying the store.")
if finished:
    result = finished.get("result") or {}
    if finished["status"] == "done":
        st.toast(f"Retry finished: {result.get('checked', 0)} read, {result.get('failed', 0)} failed.")
    else:
        st.error(f"The retry failed: {result.get('error', 'unknown error')}")
    del st.session_state["retry_job"]

listing_counts: dict[str, int] = {}
for listing in listings.values():
    if listing.get("active"):
        listing_counts[listing["store_id"]] = listing_counts.get(listing["store_id"], 0) + 1

for store in stores.values():
    failures = store.get("consecutive_failures") or 0
    with st.container(border=True):
        with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
            st.markdown(f"**{store['name']}**")
            if not store.get("active"):
                st.badge("Switched off", color="gray", icon=":material/block:")
            elif failures >= 3:
                st.badge(f"Failing, {failures} days", color="red", icon=":material/error:")
            elif failures:
                st.badge(f"{failures} failed day{'s' if failures > 1 else ''}", color="orange", icon=":material/warning:")
            else:
                st.badge("OK", color="green", icon=":material/check_circle:")
        if not store.get("active"):
            st.caption(store.get("note") or "Not in use.")
            continue
        st.caption(f"Last success {ui.when(store.get('last_success_at'))} · "
                   f"{listing_counts.get(store['id'], 0)} listings · {failures} consecutive failed days")
        with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
            muted = st.toggle("Mute health alerts", value=bool(store.get("muted")), key=f"mute_{store['id']}")
            if muted != bool(store.get("muted")):
                repo.update_store(store["id"], muted=muted)
                st.toast(f"{store['name']} {'muted' if muted else 'unmuted'}")
            if st.button("Retry", key=f"retry_{store['id']}", icon=":material/refresh:",
                         disabled="retry_job" in st.session_state or not listing_counts.get(store["id"])):
                ui.launch(repo, "check_now", {"store_id": store["id"]}, "retry_job")
                st.rerun()

# ---- Alert log
st.header("Alert log", divider="gray")
# One line per alert: the push and email rows of the same alert are folded together.
grouped: dict[tuple, dict] = {}
for row in repo.list_alerts(limit=400):
    key = (row["sent_at"][:16], row.get("listing_id"), row.get("store_id"), row["rule"])
    entry = grouped.setdefault(key, {"row": row, "channels": []})
    entry["channels"].append(f"{row.get('channel')} {'sent' if row.get('status') == 'sent' else 'FAILED'}")

log = []
for entry in grouped.values():
    row = entry["row"]
    listing = listings.get(row.get("listing_id"))
    product = products.get(listing["product_id"]) if listing else None
    log.append({
        "Date": ui.when(row["sent_at"], "%d %b %H:%M"),
        "Item": ui.product_title(product) if product else "–",
        "Store": stores.get(row.get("store_id"), {}).get("name", "–"),
        "Rule": RULE_LABELS.get(row["rule"], row["rule"]),
        "Price": float(row["price"]) if row.get("price") is not None else None,
        "Per unit": float(row["unit_price"]) if row.get("unit_price") is not None else None,
        "Delivery": ", ".join(sorted(entry["channels"])),
    })
if log:
    st.dataframe(log, hide_index=True, column_config={
        "Price": st.column_config.NumberColumn(format="R%.2f"),
        "Per unit": st.column_config.NumberColumn(format="R%.2f"),
    })
else:
    st.caption("No alerts sent yet.")
