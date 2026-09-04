"""Orchestrator.

    newsletter --issue auto [--config PATH] [--notes FILE] [--skip ID]
               [--fresh] [--demo] [--deliver]

Stages: gather (parallel, cached per issue) -> synthesize -> lint -> render.
Delivery is a separate opt-in flag, and no adapter in this repo can send.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from .assemble import assemble
from .common import (
    ROOT,
    cached,
    commit_issue_number,
    issue_dir,
    log,
    next_issue_number,
    save,
)
from .config import Config, load_config
from .editor import lint, sources_manifest, synthesize
from .gather import get as get_source
from .render import render_body, render_preview
from .schema import build_issue_model

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DEMO_DIR = ROOT / "examples" / "demo"


def next_send_date(today: date, day_name: str) -> date:
    """The next occurrence of the configured send day, never today."""
    try:
        target = DAYS.index(day_name.capitalize())
    except ValueError:
        return today + timedelta(days=1)
    ahead = (target - today.weekday()) % 7
    return today + timedelta(days=ahead or 7)


def run_gathers(cfg: Config, issue_no: int, skip: list, fresh: bool,
                demo: bool) -> Dict[str, Any]:
    """Each stage caches to output/issue-NNN/<id>.json; reruns reuse it."""
    if demo:
        raw = json.loads((DEMO_DIR / "fixtures" / "gathers.json").read_text())
        # Keys starting with _ are notes in the fixture file, not gather output.
        data = {k: v for k, v in raw.items() if not k.startswith("_")}
        log("gather", f"demo fixtures: {', '.join(data)}")
        return data

    results: Dict[str, Any] = {}
    pending = []
    for spec in cfg.gather:
        if not spec.enabled or spec.id in skip:
            log("gather", f"skipping {spec.id}")
            continue
        hit = cached(issue_no, f"{spec.id}.json", fresh)
        if hit is not None:
            results[spec.id] = hit
        else:
            pending.append(spec)

    if pending:
        with ThreadPoolExecutor(max_workers=min(4, len(pending))) as pool:
            futures = {
                pool.submit(get_source(s.source), **s.options()): s for s in pending
            }
            for future, spec in futures.items():
                try:
                    data = future.result()
                except Exception as e:  # noqa: BLE001 - one bad source is not fatal
                    log("gather", f"{spec.id} raised: {e}")
                    data = {"stub": True, "source": spec.source, "reason": str(e)}
                results[spec.id] = data
                save(issue_no, f"{spec.id}.json", data)
    return results


def fill_tables(cfg: Config, issue, gathers: Dict[str, Any]) -> None:
    """Table rows come from gathered data, never from the model.

    The model writes the caption and nothing else, so a figure in a table
    cannot be an invention.
    """
    for spec in cfg.sections:
        if spec.type != "table":
            continue
        section = getattr(issue, spec.id, None)
        if section is None:
            continue
        rows = (gathers.get(spec.rows_from) or {}).get("rows", [])
        section.rows = rows
        log("render", f"{spec.id}: filled {len(rows)} rows from {spec.rows_from}")


def load_demo_issue(cfg: Config):
    """A canned draft so the pipeline runs end to end with no API key."""
    model = build_issue_model(cfg.sections)
    data = json.loads((DEMO_DIR / "fixtures" / "draft.json").read_text())
    return model(**data)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="newsletter", description=__doc__.split("\n")[0])
    ap.add_argument("--issue", default="auto", help="issue number, or 'auto' to increment")
    ap.add_argument("--config", type=Path, default=None, help="path to newsletter.yaml")
    ap.add_argument("--notes", type=Path, default=None,
                    help="file of human notes for human-sourced sections")
    ap.add_argument("--skip", action="append", default=[], metavar="ID",
                    help="skip a gather stage by id (repeatable)")
    ap.add_argument("--fresh", action="store_true", help="ignore cached gather output")
    ap.add_argument("--demo", action="store_true",
                    help="run on bundled fixtures with no API keys at all")
    ap.add_argument("--deliver", action="store_true",
                    help="stage a draft with the configured adapter (never sends)")
    ap.add_argument("--send-date", default=None, metavar="YYYY-MM-DD")
    return ap


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(args.config or (DEMO_DIR / "newsletter.yaml" if args.demo else None))

    issue_no = next_issue_number() if args.issue == "auto" else int(args.issue)
    send_date = (
        date.fromisoformat(args.send_date)
        if args.send_date
        else next_send_date(date.today(), cfg.send_day)
    )
    log("run", f"{cfg.brand.name} issue {issue_no:03d}, send date {send_date.isoformat()}")

    gathers = run_gathers(cfg, issue_no, args.skip, args.fresh, args.demo)

    notes = None
    if args.notes:
        if args.notes.exists():
            notes = args.notes.read_text()
        else:
            log("run", f"WARNING: notes file {args.notes} not found")

    if args.demo:
        log("editor", "demo mode: using the bundled draft, no API call")
        issue = load_demo_issue(cfg)
    else:
        issue = synthesize(cfg, issue_no, send_date, gathers, notes)

    fill_tables(cfg, issue, gathers)
    lint(cfg, issue)

    save(issue_no, "draft.json", {**issue.model_dump(), "send_date": send_date.isoformat()})
    save(issue_no, "sources.json", sources_manifest(cfg, issue))

    date_str = send_date.strftime("%A, %B %d, %Y")
    body = render_body(cfg, issue, issue_no, date_str)
    email = assemble(cfg, body, issue.preview_text)
    d = issue_dir(issue_no)
    (d / "body.html").write_text(body)
    (d / "preview.html").write_text(render_preview(cfg, body, issue.subject))
    (d / "email.html").write_text(email)
    log("render", f"body {len(body)}b, email {len(email)}b")

    location = str(d / "email.html")
    if args.deliver:
        from .deliver import get as get_adapter

        location = get_adapter(cfg.delivery)(
            cfg, issue_no, email, {"subject": issue.subject, "preview_text": issue.preview_text}
        )

    commit_issue_number(issue_no)
    print(str(d))
    print(f"SUBJECT: {issue.subject}")
    print(f"PREVIEW: {issue.preview_text}")
    print(f"REVIEW:  {location}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
