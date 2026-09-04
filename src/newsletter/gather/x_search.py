"""X/Twitter discourse via xAI's Responses API with the server-side x_search tool.

Optional, and the most expensive source here: tool invocations bill on top of
tokens, so set a spend limit in the xAI console before enabling it.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import List, Optional

from ..common import env, log, stub

RESPONSES_URL = "https://api.x.ai/v1/responses"

SYSTEM = (
    "You are a research assistant for a newsletter. Search X for posts from the "
    "window given. Prioritise the watchlist handles, but include other accounts "
    "if they drove a major discussion. Identify the {n} most consequential "
    "discussions. For each: who said what (name, handle, direct link to the "
    "post), the opposing or complicating view, and why a reader should care. "
    'Return strict JSON only, no markdown fences: {{"debates": [{{"topic": str, '
    '"positions": [{{"who": str, "handle": str, "summary": str, "post_url": '
    'str}}], "takeaway": str}}]}}. Facts only from actual posts, and a post URL '
    "for every claim."
)


def _final_text(payload: dict) -> str:
    """The last message item holds the answer.

    Grok interleaves narration between tool-call rounds, so concatenating every
    text part buries the JSON behind prose and breaks parsing.
    """
    texts = []
    for item in payload.get("output", []):
        if item.get("type") not in (None, "message"):
            continue
        parts = [
            part["text"]
            for part in item.get("content", []) or []
            if part.get("type") == "output_text" and part.get("text")
        ]
        if parts:
            texts.append("\n".join(parts))
    return texts[-1] if texts else (payload.get("output_text", "") or "")


def run(handles: Optional[List[str]] = None, days: int = 7, topics: int = 3,
        **_ignored) -> dict:
    import requests

    key = env("XAI_API_KEY")
    if not key:
        return stub("x_search", "XAI_API_KEY not configured")

    model = env("XAI_MODEL", "grok-4.5")
    today = date.today()
    body = {
        "model": model,
        "input": [
            {"role": "system", "content": SYSTEM.format(n=topics)},
            {
                "role": "user",
                "content": "Watchlist handles: "
                + ", ".join("@" + h for h in (handles or []) if h),
            },
        ],
        "tools": [
            {
                "type": "x_search",
                "from_date": (today - timedelta(days=days)).isoformat(),
                "to_date": today.isoformat(),
            }
        ],
    }

    last_error = None
    for attempt in (1, 2):
        try:
            resp = requests.post(
                RESPONSES_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=body,
                timeout=300,
            )
            resp.raise_for_status()
            text = _final_text(resp.json()).strip()
            if text.startswith("```"):
                text = text.strip("`").lstrip("json").strip()
            data = json.loads(text)
            data["model"] = model
            log("x_search", f"got {len(data.get('debates', []))} debates")
            return data
        except Exception as e:  # noqa: BLE001
            last_error = e
            log("x_search", f"attempt {attempt} failed: {e}")
    return stub("x_search", f"xAI call failed twice: {last_error}")
