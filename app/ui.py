"""Shared pieces for every page: the password gate, the repo, formatting, job polling."""
from __future__ import annotations

import hashlib
import hmac
import html
import time
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import streamlit as st

from core import config
from core.jobs import JobError, start_job
from core.models import size_word
from core.repo import Repo, get_repo, parse_ts
from scraper.adapters import store_rows

SAST = ZoneInfo("Africa/Johannesburg")
HOME, ITEM, ADD, ALERTS = "Home.py", "pages/1_Item.py", "pages/2_Add_item.py", "pages/3_Alerts.py"


@st.cache_resource
def _repo() -> Repo:
    repo = get_repo()
    repo.ensure_stores(store_rows())
    return repo


COOKIE = "npw_auth"
REMEMBER_DAYS = 180


def _remember_token(password: str) -> str:
    """What the remember-me cookie holds: derived from the password, so changing
    the password signs every remembered device out. The password itself is never stored."""
    return hmac.new(password.encode(), b"nappy-price-watch remember v1", hashlib.sha256).hexdigest()


def _cookie_script(value: str, max_age: int) -> None:
    """Set (or with max_age 0, clear) the remember-me cookie in the browser."""
    st.html(
        "<script>document.cookie = '%s=%s; path=/; max-age=%d; SameSite=Lax'"
        " + (location.protocol === 'https:' ? '; Secure' : '');</script>" % (COOKIE, value, max_age),
        unsafe_allow_javascript=True)


def _remembered(password: str) -> bool:
    try:
        cookie = st.context.cookies.get(COOKIE) or ""
    except Exception:
        return False
    if not isinstance(cookie, str):
        return False
    return hmac.compare_digest(cookie.encode(), _remember_token(password).encode())


def require_login() -> str:
    """Stop the page unless the shared password has been entered. Returns a label for who is using the app."""
    # The bypass is for local development and never applies once Supabase is configured.
    if config.flag("AUTH_BYPASS") and not config.get("SUPABASE_URL"):
        return "local"
    password = config.get("APP_PASSWORD")
    if st.session_state.get("signed_in"):
        if st.session_state.pop("remember_pending", False) and password:
            _cookie_script(_remember_token(password), REMEMBER_DAYS * 86400)
        return "shared"
    if st.session_state.pop("forget_pending", False):
        _cookie_script("", 0)
    st.title("Nappy Price Watch")
    if not password:
        # No password configured means nobody gets in, rather than everybody.
        st.error("No password is set. Add APP_PASSWORD to the app secrets (see README).")
        st.stop()
    if _remembered(password) and not st.session_state.get("signed_out"):
        st.session_state["signed_in"] = True
        st.rerun()
    with st.form("sign_in"):
        entered = st.text_input("Password", type="password", autocomplete="current-password")
        remember = st.checkbox("Remember me on this device", value=True)
        submitted = st.form_submit_button("Sign in", type="primary")
    if submitted:
        if hmac.compare_digest(entered.encode(), password.encode()):
            st.session_state["signed_in"] = True
            st.session_state["remember_pending"] = remember
            st.rerun()
        time.sleep(1.5)  # slows down guessing
        st.error("Wrong password.")
    st.stop()


def sign_out_button() -> None:
    """Forget this device and return to the password page."""
    if st.session_state.get("signed_in") and st.button("Sign out", icon=":material/logout:"):
        st.session_state["signed_in"] = False
        st.session_state["signed_out"] = True      # ignore the cookie until the browser has dropped it
        st.session_state["forget_pending"] = True
        st.rerun()


STYLE = """
<style>
.stMainBlockContainer { padding-top: 2.5rem; }
h1 { font-size: 1.8rem !important; }
h2 { font-size: 1.35rem !important; }
h3 { font-size: 1.05rem !important; color: #2f6f9f; }
/* baby blue surfaces on white */
[data-testid="stExpander"] details { border: 1px solid #bfe3f8; border-radius: 12px; background: #ffffff; }
[data-testid="stExpander"] summary { background: #e6f4fd; border-radius: 11px; font-weight: 600; }
[data-testid="stVerticalBlockBorderWrapper"] { border-color: #bfe3f8 !important; }
.npw-logo { width: 18px; height: 18px; border-radius: 4px; vertical-align: -3px; margin-right: 5px; background: #fff; }
.npw-store { white-space: nowrap; }
.npw-tag { font-size: .75rem; font-weight: 600; padding: 1px 8px; border-radius: 999px; white-space: nowrap; }
.npw-special { background: rgba(208,59,59,.12); color: #c23030; }
.npw-target { background: rgba(12,163,12,.14); color: #0a7d0a; }
.npw-flat { background: #e6f4fd; color: #2f6f9f; }
<<<<<<< HEAD
.npw-summary { display: flex; gap: 8px; }
.npw-summary > div { flex: 1; background: #e6f4fd; border-radius: 10px; padding: 8px 10px; }
.npw-summary span { display: block; font-size: .75rem; opacity: .8; }
.npw-summary b { font-size: 1.1rem; white-space: nowrap; }
.npw-star { color: #f2b01e; font-size: 1.15em; margin-left: 4px; text-shadow: 0 0 1px #b07a00; }
=======
.npw-best { background: #89cff0; color: #123a57; }
>>>>>>> 56b44108f4cf891888894d2a762a896877c970a1
</style>
"""


def setup(title: str) -> tuple[Repo, str]:
    """Call first on every page."""
    st.set_page_config(page_title=f"{title} · Nappy Price Watch", page_icon="🍼", layout="centered")
    st.html(STYLE)
    user = require_login()
    return _repo(), user


def logo_url(store: dict) -> str:
    """The store's own site icon, fetched by the viewer's browser."""
    host = urlparse(store.get("base_url") or "").netloc or f"{store.get('id', '')}.co.za"
    return f"https://www.google.com/s2/favicons?domain={host}&sz=64"


<<<<<<< HEAD
STAR = '<span class="npw-star" title="Cheapest price" aria-label="Cheapest price">★</span>'


=======
>>>>>>> 56b44108f4cf891888894d2a762a896877c970a1
def store_html(store: dict | None) -> str:
    """Store logo and name, for use inside HTML blocks."""
    if not store:
        return ""
    return (f'<span class="npw-store"><img class="npw-logo" src="{html.escape(logo_url(store))}" alt="">'
            f'{html.escape(store.get("name") or "")}</span>')


def nav(current: str) -> None:
    """One-tap links between pages, shown at the top so the sidebar is never needed on a phone."""
    with st.container(horizontal=True, gap="small"):
        for path, label, icon in ((HOME, "Dashboard", ":material/home:"), (ADD, "Add", ":material/add:"),
                                  (ALERTS, "Alerts", ":material/notifications:")):
            st.page_link(path, label=label, icon=icon, disabled=path == current)


def rand(value, decimals: int = 2) -> str:
    return "–" if value is None else f"R{float(value):,.{decimals}f}"


def when(value: str | datetime | None, fmt: str = "%a %d %b, %H:%M") -> str:
    ts = parse_ts(value)
    return ts.astimezone(SAST).strftime(fmt) if ts else "never"


def product_title(product: dict) -> str:
    size = product.get("size")
    return product["name"] + (f" · {size_word(product.get('category'))} {size}" if size else "")


def open_item(product_id: str) -> None:
    st.session_state["product_id"] = product_id
    st.switch_page(ITEM)


def launch(repo: Repo, kind: str, job_input: dict | None, state_key: str) -> None:
    """Start a job and remember its id under `state_key`."""
    try:
        st.session_state[state_key] = start_job(repo, kind, job_input)["id"]
    except JobError as exc:
        st.error(str(exc))


def wait_for(repo: Repo, state_key: str, message: str) -> dict | None:
    """Show progress for the job stored under `state_key`; return it once it has finished.

    Polls every three seconds from a fragment, so the rest of the page stays usable.
    """
    job_id = st.session_state.get(state_key)
    if not job_id:
        return None
    job = repo.get_job(job_id)
    if job is None:
        st.session_state.pop(state_key, None)
        return None
    if job["status"] in ("done", "failed"):
        return job

    @st.fragment(run_every=3)
    def poll():
        current = repo.get_job(job_id)
        if current and current["status"] in ("done", "failed"):
            st.rerun()
        st.info(f"{message} This usually takes one to two minutes.", icon=":material/hourglass_top:")

    poll()
    return None
