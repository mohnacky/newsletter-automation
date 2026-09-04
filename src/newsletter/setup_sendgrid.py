"""Idempotent SendGrid provisioning: sender, contact list, unsubscribe group.

    python -m newsletter.setup_sendgrid

Prints the three ids to put in .env. Safe to re-run: it reuses anything that
already exists by name rather than creating duplicates.
"""

from __future__ import annotations

from .common import log
from .config import load_config
from .deliver.sendgrid_draft import sg


def _find(items, name_key: str, name: str):
    return next((i for i in items if i.get(name_key) == name), None)


def main() -> int:
    cfg = load_config()
    brand = cfg.brand

    senders = sg("GET", "/marketing/senders").get("results", [])
    sender = _find(senders, "nickname", brand.name)
    if not sender:
        if not (brand.from_email and brand.address):
            raise SystemExit("brand.from_email and brand.address are required to create a sender")
        sender = sg("POST", "/marketing/senders", json={
            "nickname": brand.name,
            "from": {"email": brand.from_email, "name": brand.from_name or brand.name},
            "reply_to": {"email": brand.from_email},
            "address": brand.address,
            "city": "", "country": "",
        })
    log("setup", f"sender {sender['id']}")

    lists = sg("GET", "/marketing/lists").get("result", [])
    contact_list = _find(lists, "name", brand.name)
    if not contact_list:
        contact_list = sg("POST", "/marketing/lists", json={"name": brand.name})
    log("setup", f"list {contact_list['id']}")

    groups = sg("GET", "/asm/groups")
    group = _find(groups if isinstance(groups, list) else [], "name", brand.name)
    if not group:
        group = sg("POST", "/asm/groups", json={
            "name": brand.name,
            "description": f"Unsubscribe from {brand.name}",
            "is_default": True,
        })
    log("setup", f"unsubscribe group {group['id']}")

    print("Add these to .env:\n")
    print(f"SENDGRID_SENDER_ID={sender['id']}")
    print(f"SENDGRID_LIST_ID={contact_list['id']}")
    print(f"SENDGRID_UNSUB_GROUP_ID={group['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
