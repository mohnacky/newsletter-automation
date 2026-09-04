"""Feeds. The only source that needs no API key, so it is the default one.

Give it a list of feed URLs and it returns recent entries with a summary. Good
for trade press, company blogs, release notes, and government feeds.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from ..common import log, stub

USER_AGENT = "newsletter-automation/0.1 (+https://github.com/mohnacky/newsletter-automation)"


def _clean(text: str, limit: int = 800) -> str:
    """Strip tags and collapse whitespace: feed summaries are often raw HTML."""
    stripped = re.sub(r"<[^>]+>", " ", text or "").replace("&nbsp;", " ")
    return " ".join(stripped.split())[:limit]


def _published(entry) -> Optional[datetime]:
    for key in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, key, None)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None


def run(feeds: Optional[List[str]] = None, days: int = 7, per_feed: int = 5,
        **_ignored) -> dict:
    import feedparser
    import requests

    feeds = feeds or []
    if not feeds:
        return stub("rss", "no feeds configured")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items: List[dict] = []
    failures: List[str] = []

    for url in feeds:
        try:
            resp = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
            kept = 0
            for entry in parsed.entries:
                when = _published(entry)
                if when and when < cutoff:
                    continue
                items.append(
                    {
                        "title": " ".join((entry.get("title") or "").split()),
                        "url": entry.get("link"),
                        "published": when.isoformat() if when else None,
                        "summary": _clean(entry.get("summary", "")),
                        "feed": parsed.feed.get("title") or url,
                    }
                )
                kept += 1
                if kept >= per_feed:
                    break
        except Exception as e:  # noqa: BLE001 - a dead feed must not stop the run
            failures.append(f"{url}: {e}")
            log("rss", f"failed {url}: {e}")

    if not items:
        return stub("rss", f"no entries in {days} days" + (f"; {failures}" if failures else ""))
    log("rss", f"{len(items)} entries from {len(feeds) - len(failures)}/{len(feeds)} feeds")
    return {"items": items, "failed_feeds": failures}
