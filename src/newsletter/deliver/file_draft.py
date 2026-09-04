"""The default adapter: write the assembled email to disk and stop.

Paste it into whatever your provider's HTML editor is. Works with every ESP,
needs no credentials, and is the right default for a first run.
"""

from __future__ import annotations

from ..common import issue_dir, log


def deliver(cfg, issue_no: int, email_html: str, meta: dict) -> str:
    path = issue_dir(issue_no) / "email.html"
    path.write_text(email_html)
    log("deliver", f"wrote {path} ({len(email_html)} bytes)")
    return str(path)
