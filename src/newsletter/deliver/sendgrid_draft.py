"""SendGrid: create a DRAFT Single Send. Never sends, never schedules.

Needs SENDGRID_API_KEY plus the three ids that `python -m newsletter.setup_sendgrid`
writes into .env. A person opens the draft in SendGrid and presses send.
"""

from __future__ import annotations

from ..common import env, log

BASE = "https://api.sendgrid.com/v3"


def _key() -> str:
    key = env("SENDGRID_API_KEY")
    if not key:
        raise SystemExit("SENDGRID_API_KEY missing from .env")
    return key


def sg(method: str, path: str, json=None, params=None, timeout: int = 60):
    """One SendGrid call. Errors carry the response body, which is the only
    useful diagnostic SendGrid gives you."""
    import requests

    r = requests.request(
        method,
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {_key()}"},
        json=json,
        params=params,
        timeout=timeout,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:2000]}")
    return r.json() if r.text.strip() else {}


def required_id(name: str) -> str:
    value = env(name)
    if not value:
        raise SystemExit(
            f"{name} missing from .env - run `python -m newsletter.setup_sendgrid` first"
        )
    return value


def deliver(cfg, issue_no: int, email_html: str, meta: dict) -> str:
    resp = sg(
        "POST",
        "/marketing/singlesends",
        json={
            "name": f"{cfg.brand.name} - Issue {issue_no:03d}",
            "send_to": {"list_ids": [required_id("SENDGRID_LIST_ID")]},
            "email_config": {
                "subject": meta["subject"],
                "html_content": email_html,
                "generate_plain_content": True,
                "sender_id": int(required_id("SENDGRID_SENDER_ID")),
                "suppression_group_id": int(required_id("SENDGRID_UNSUB_GROUP_ID")),
            },
        },
    )
    log("deliver", f"draft single send {resp['id']} (status {resp.get('status')})")
    return f"https://mc.sendgrid.com/single-sends/{resp['id']}/editor"
