"""Web search via Exa, scoped into buckets.

Each bucket is a named search with its own query and domain allow-list, which
is how a section like "policy: federal / state / global" gets one item per
bucket. No key means a stub, not a crash.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from ..common import env, log, stub

SEARCH_URL = "https://api.exa.ai/search"
CONTENTS_URL = "https://api.exa.ai/contents"


def _search(key: str, query: str, domains: List[str], start: str, n: int) -> list:
    import requests

    payload = {"query": query, "type": "auto", "numResults": n, "startPublishedDate": start}
    if domains:
        payload["includeDomains"] = domains
    resp = requests.post(
        SEARCH_URL,
        headers={"x-api-key": key, "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def _contents(key: str, ids: List[str], max_chars: int) -> Dict[str, str]:
    import requests

    if not ids:
        return {}
    resp = requests.post(
        CONTENTS_URL,
        headers={"x-api-key": key, "Content-Type": "application/json"},
        json={"ids": ids, "text": {"maxCharacters": max_chars}},
        timeout=60,
    )
    resp.raise_for_status()
    return {r["id"]: r.get("text", "") for r in resp.json().get("results", [])}


def run(buckets: Optional[Dict[str, dict]] = None, days: int = 7, per_bucket: int = 2,
        max_chars: int = 4000, **_ignored) -> dict:
    key = env("EXA_API_KEY")
    if not key:
        return stub("web_search", "EXA_API_KEY not configured")
    if not buckets:
        return stub("web_search", "no buckets configured")

    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    out: Dict[str, list] = {}
    for name, spec in buckets.items():
        try:
            results = _search(
                key, spec.get("query", name), spec.get("domains", []), start, per_bucket + 3
            )
            top = results[:per_bucket]
            texts = _contents(key, [r["id"] for r in top], max_chars)
            out[name] = [
                {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "published": r.get("publishedDate"),
                    "text": texts.get(r["id"], "")[:max_chars],
                }
                for r in top
            ]
            log("web_search", f"{name}: {len(out[name])} results")
        except Exception as e:  # noqa: BLE001
            log("web_search", f"{name} failed: {e}")
            out[name] = []

    if not any(out.values()):
        return stub("web_search", "every bucket came back empty")
    return {"buckets": out}
