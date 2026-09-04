"""Paths, env, logging, and the per-issue output cache."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is convenience, not a hard requirement
    def load_dotenv(*_a, **_k):  # type: ignore[misc]
        return False

# Repo root when running from a checkout; overridable so a user can keep their
# config and output outside the package directory.
ROOT = Path(os.environ.get("NEWSLETTER_HOME", Path(__file__).resolve().parents[2]))
OUTPUT_DIR = ROOT / "output"
CONFIG_DIR = ROOT / "config"
PROMPTS_DIR = ROOT / "prompts"
TEMPLATES_DIR = ROOT / "templates"

load_dotenv(ROOT / ".env")


def log(stage: str, msg: str) -> None:
    """Progress goes to stderr so stdout stays a clean machine-readable contract."""
    print(f"[{time.strftime('%H:%M:%S')}] [{stage}] {msg}", file=sys.stderr)


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def issue_dir(issue: int) -> Path:
    d = OUTPUT_DIR / f"issue-{issue:03d}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def next_issue_number() -> int:
    counter = OUTPUT_DIR / "ISSUE_COUNTER"
    if counter.exists():
        return int(counter.read_text().strip()) + 1
    return 1


def commit_issue_number(issue: int) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "ISSUE_COUNTER").write_text(str(issue))


def cached(issue: int, name: str, fresh: bool) -> Optional[Any]:
    """Return a stage's cached JSON, or None. Reruns are cheap by default:
    gather stages cost money, so they are only re-fetched with --fresh."""
    path = issue_dir(issue) / name
    if path.exists() and not fresh:
        log("cache", f"reusing {path.name}")
        return json.loads(path.read_text())
    return None


def save(issue: int, name: str, data: Any) -> Path:
    path = issue_dir(issue) / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    log("save", str(path))
    return path


def stub(source: str, reason: str) -> dict:
    """Written when a gather stage fails or has no key.

    A stub is not an error: the run continues and the editorial prompt is told
    the section is thin, which is better than a crashed pipeline on send day.
    """
    return {"stub": True, "source": source, "reason": reason, "items": []}
