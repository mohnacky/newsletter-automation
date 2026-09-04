"""arXiv: fetch a category window, then optionally rank it with Claude.

Fetching needs no key. Ranking does; without one you get the newest papers
unranked, which is still material the editor can work with.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from pydantic import BaseModel

from ..common import env, log, stub

ARXIV_URL = "http://export.arxiv.org/api/query"
USER_AGENT = "newsletter-automation/0.1"


class RankedPaper(BaseModel):
    id: str
    title: str
    url: str
    whats_new: str
    why_it_matters: str
    score: int


class Ranking(BaseModel):
    papers: List[RankedPaper]


def _pages(comment: str) -> Optional[int]:
    m = re.search(r"(\d{1,3})\s*pages", comment or "", re.IGNORECASE)
    return int(m.group(1)) if m else None


def fetch(categories: List[str], days: int, max_results: int) -> List[dict]:
    import feedparser
    import requests

    query = "+OR+".join(f"cat:{c}" for c in categories)
    url = (
        f"{ARXIV_URL}?search_query={query}&sortBy=submittedDate"
        f"&sortOrder=descending&max_results={max_results}"
    )
    log("arxiv", f"fetching {max_results} newest across {','.join(categories)}")
    resp = requests.get(url, timeout=60, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    time.sleep(3)  # arXiv asks for one request per three seconds
    feed = feedparser.parse(resp.text)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    papers = []
    for e in feed.entries:
        published = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
        if published < cutoff:
            continue
        papers.append(
            {
                "id": e.id.split("/abs/")[-1],
                "title": " ".join(e.title.split()),
                "abstract": " ".join(e.summary.split())[:1200],
                "url": e.link,
                "published": published.isoformat(),
                "pages": _pages(getattr(e, "arxiv_comment", "")),
            }
        )
    log("arxiv", f"{len(papers)} papers in the {days}-day window")
    return papers


def rank(papers: List[dict], themes: str, model: str, keep: int) -> dict:
    if not env("ANTHROPIC_API_KEY"):
        return {"papers": papers[:keep], "unranked": True, "reason": "no ANTHROPIC_API_KEY"}

    import anthropic

    client = anthropic.Anthropic()
    batch = [
        {"id": p["id"], "title": p["title"], "abstract": p["abstract"], "url": p["url"]}
        for p in papers
    ]
    prompt = (
        "You rank arXiv papers for a newsletter. The audience cares about: "
        f"{themes}.\n\nScore each paper 0-100 for relevance and consequence to "
        f"that audience and return the top {keep}. For each: whats_new (one "
        "sentence, what the paper found) and why_it_matters (one sentence, what "
        "a reader should do or watch). Copy id, title and url exactly from the "
        "input. Never invent a number.\n\nPapers:\n"
        f"{json.dumps(batch, ensure_ascii=False)}"
    )
    response = client.messages.parse(
        model=model,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
        output_format=Ranking,
    )
    ranked = response.parsed_output
    log("arxiv", f"ranked; top {len(ranked.papers)} returned")
    return {"papers": [p.model_dump() for p in ranked.papers]}


def run(categories: Optional[List[str]] = None, days: int = 7, max_results: int = 150,
        themes: str = "practical consequence for practitioners",
        rank_model: str = "claude-opus-5", keep: int = 6, **_ignored) -> dict:
    categories = categories or ["cs.AI"]
    try:
        papers = fetch(categories, days, max_results)
    except Exception as e:  # noqa: BLE001
        return stub("arxiv", f"fetch failed: {e}")
    if not papers:
        return stub("arxiv", f"no papers in the last {days} days")
    try:
        return rank(papers, themes, rank_model, keep)
    except Exception as e:  # noqa: BLE001
        log("arxiv", f"ranking failed, falling back to newest: {e}")
        return {"papers": papers[:keep], "unranked": True, "reason": str(e)}
