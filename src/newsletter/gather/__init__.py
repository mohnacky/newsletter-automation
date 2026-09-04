"""Gather sources.

A source is a module with `run(**options) -> dict`. Options come from the
gather entry in config, so adding a source means writing one function and
naming it in YAML.

Every source must degrade instead of raising: no key, a dead endpoint, or an
empty week returns `stub(...)`. A newsletter pipeline that crashes on send
morning is worse than one that reports a thin section.
"""

from __future__ import annotations

from typing import Callable, Dict

from . import arxiv, rows, rss, web_search, x_search

REGISTRY: Dict[str, Callable[..., dict]] = {
    "rss": rss.run,
    "arxiv": arxiv.run,
    "rows": rows.run,
    "web_search": web_search.run,
    "x_search": x_search.run,
}


def get(name: str) -> Callable[..., dict]:
    if name not in REGISTRY:
        raise ValueError(
            f"unknown gather source {name!r}; available: {sorted(REGISTRY)}"
        )
    return REGISTRY[name]
