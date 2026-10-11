"""Settings from the environment, falling back to Streamlit secrets."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def get(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return default


def get_list(name: str) -> list[str]:
    raw = get(name) or ""
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def flag(name: str) -> bool:
    return (get(name) or "").lower() in ("1", "true", "yes")
