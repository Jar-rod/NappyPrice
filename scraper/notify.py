"""Push (ntfy) and email (Resend). Each send is tried twice before it counts as failed."""
from __future__ import annotations

import httpx

from core import config

SENT, FAILED = "sent", "failed"


class Notifier:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.topic = config.get("NTFY_TOPIC")
        self.server = (config.get("NTFY_SERVER") or "https://ntfy.sh").rstrip("/")
        self.resend_key = config.get("RESEND_API_KEY")
        self.email_from = config.get("EMAIL_FROM") or "Nappy Price Watch <onboarding@resend.dev>"
        self.email_to = config.get_list("ALERT_EMAILS")

    def channels(self) -> list[str]:
        found = []
        if self.topic:
            found.append("push")
        if self.resend_key and self.email_to:
            found.append("email")
        return found

    @staticmethod
    def _twice(send) -> str:
        for _ in range(2):
            try:
                response = send()
                if response.status_code < 300:
                    return SENT
                print(f"notify: HTTP {response.status_code} {response.text[:200]}")
            except httpx.HTTPError as exc:
                print(f"notify: {type(exc).__name__}: {exc}")
        return FAILED

    def push(self, title: str, body: str, click: str | None = None, quiet: bool = False) -> str:
        payload = {"topic": self.topic, "title": title, "message": body,
                   "priority": 2 if quiet else 4, "tags": ["baby"]}
        if click:
            payload["click"] = click
        return self._twice(lambda: httpx.post(self.server, json=payload, timeout=20))

    def email(self, subject: str, text: str, html: str) -> str:
        payload = {"from": self.email_from, "to": self.email_to, "subject": subject,
                   "text": text, "html": html}
        return self._twice(lambda: httpx.post(
            "https://api.resend.com/emails", json=payload, timeout=20,
            headers={"Authorization": f"Bearer {self.resend_key}"}))

    def send(self, title: str, text: str, html: str, click: str | None = None,
             quiet: bool = False) -> dict[str, str]:
        """Send on every configured channel. Returns {channel: 'sent' | 'failed'}."""
        if self.dry_run:
            print(f"--- dry run, not sent ---\n{title}\n{text}\n")
            return {}
        results = {}
        if "push" in self.channels():
            results["push"] = self.push(title, text, click, quiet)
        if "email" in self.channels():
            results["email"] = self.email(title, text, html)
        if not results:
            print(f"notify: no channel configured, message dropped:\n{title}\n{text}")
        return results
