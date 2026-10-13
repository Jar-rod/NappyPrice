"""Run first by every page: make `core` and `scraper` importable, and drop stale code.

A hosted Streamlit app keeps running when new code is pushed. It re-reads the
page files but keeps modules it has already imported, so a page can end up
calling a function that the old in-memory copy of a module does not have.
`refresh()` notices that the project's files have changed and forgets the old
copies, so the page imports the current ones. Pages reload this module on
every run, which is what lets it take effect without restarting the app.
"""
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PACKAGES = ("app", "core", "scraper")


def fingerprint() -> float:
    """Latest modification time across the project's Python files."""
    return max((p.stat().st_mtime for package in PACKAGES for p in Path(ROOT, package).rglob("*.py")), default=0.0)


def refresh() -> bool:
    """Forget project modules loaded from older files. Returns True if anything was dropped."""
    current = fingerprint()
    if getattr(sys, "_npw_fingerprint", None) == current:
        return False
    sys._npw_fingerprint = current
    stale = [name for name in sys.modules
             if name.split(".")[0] in PACKAGES and name != "app._bootstrap"]
    for name in stale:
        del sys.modules[name]
    if stale:
        try:
            import streamlit as st

            st.cache_resource.clear()   # cached objects were built from the old classes
        except Exception:
            pass
    return bool(stale)
