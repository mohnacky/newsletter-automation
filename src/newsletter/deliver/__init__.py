"""Delivery adapters.

An adapter is a module with `deliver(cfg, issue_no, email_html, meta) -> str`
returning a human-readable location (a file path, a draft URL).

**No adapter in this repo sends mail.** They stage a draft that a person opens,
reads, and sends. That is a deliberate design constraint, not a missing
feature: an automated pipeline that can send is one bad gather away from
mailing your whole list something wrong.
"""

from __future__ import annotations

from typing import Callable, Dict

from . import file_draft, sendgrid_draft

REGISTRY: Dict[str, Callable[..., str]] = {
    "file": file_draft.deliver,
    "sendgrid": sendgrid_draft.deliver,
}


def get(name: str) -> Callable[..., str]:
    if name not in REGISTRY:
        raise ValueError(
            f"unknown delivery adapter {name!r}; available: {sorted(REGISTRY)}"
        )
    return REGISTRY[name]
