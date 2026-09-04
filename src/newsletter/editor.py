"""Synthesis: one structured Claude call turns gathered material into an issue.

The section list in config drives three things at once -- the response schema,
the brief handed to the model, and the lint that runs afterwards. Keeping them
generated from one source is what stops a newsletter's structure drifting away
from what its prompt claims.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel

from .common import log
from .config import Config
from .schema import SectionSpec, build_issue_model

SHAPES = {
    "story": "one object: headline, what_happened, why_it_matters, url"
             " (add other_side when required)",
    "items": "a list of objects: headline, whats_new, why_it_matters, url",
    "debate": "one object: positions (name, position, url), pull_quote, "
              "pull_quote_attribution (who said it, name only), bottom_line. "
              "Put no quotation marks around pull_quote and no attribution "
              "inside it: both are added when the issue is rendered",
    "bullets": "a list of objects: label, fact, implication, url",
    "note": "one object: scene, why_it_matters",
    "table": "one object: caption only -- the rows are filled in from data "
             "after you write, so never state a number from the table",
}


def section_brief(spec: SectionSpec) -> str:
    """The instructions for one section, assembled from its config."""
    parts = [f"### {spec.id}"]
    if spec.title:
        parts.append(f"Rendered title: {spec.title}")
    parts.append(f"Shape: {SHAPES[spec.type]}")
    if spec.min or spec.max:
        lo = spec.min if spec.min is not None else 0
        hi = spec.max if spec.max is not None else "any number of"
        parts.append(f"Count: {lo} to {hi} entries.")
    if spec.labels:
        parts.append(
            "Labels, in this exact order, one entry each: " + ", ".join(spec.labels)
        )
    if spec.both_sides:
        parts.append(
            "other_side is required: state the strongest case against this "
            "item's framing, in one sentence."
        )
    if spec.source == "human":
        parts.append(
            "Human-supplied only. Use the supplied note verbatim in substance; "
            "if no note is supplied, set this section to null. Never invent it."
        )
    if spec.source == "gather":
        parts.append("Filled from gathered data, not by you.")
    if spec.framing:
        parts.append(f"Framing shown to the reader: {spec.framing}")
    if spec.guidance:
        parts.append(f"Editorial guidance: {spec.guidance}")
    return "\n".join(parts)


def build_system_prompt(cfg: Config) -> str:
    """House prompt + the section briefs generated from config."""
    base = cfg.prompt_path().read_text()
    briefs = "\n\n".join(section_brief(s) for s in cfg.sections)
    rules = []
    if cfg.style.banned_characters:
        rules.append(
            "Never use these characters anywhere in your output: "
            + " ".join(cfg.style.banned_characters)
        )
    if cfg.style.banned_phrases:
        rules.append(
            "Never use these phrases: "
            + "; ".join(f'"{p}"' for p in cfg.style.banned_phrases)
        )
    if cfg.style.max_subject_chars:
        rules.append(f"Subject line: at most {cfg.style.max_subject_chars} characters.")
    if cfg.style.require_urls:
        rules.append(
            "Every factual claim carries the source URL it came from. Never "
            "write a URL that did not appear in the material you were given."
        )
    rules_block = "\n".join(f"- {r}" for r in rules)

    return (
        f"{base}\n\n"
        f"# Newsletter\n\n"
        f"You are writing {cfg.brand.name}"
        + (f", {cfg.brand.tagline}" if cfg.brand.tagline else "")
        + ".\n\n"
        f"# Sections\n\nWrite exactly these sections, in this order.\n\n{briefs}\n\n"
        f"# Hard rules\n\n{rules_block}\n"
    )


def build_user_message(
    cfg: Config,
    issue_no: int,
    issue_date: date,
    gathers: Dict[str, Any],
    notes: Optional[str],
) -> str:
    parts = [
        f"Issue number: {issue_no}",
        f"Issue date: {issue_date.strftime('%A, %B %d, %Y')}",
    ]
    human_sections = [s.id for s in cfg.sections if s.source == "human"]
    if human_sections:
        if notes:
            parts.append(
                "HUMAN NOTE (the only permitted source for "
                f"{', '.join(human_sections)}):\n{notes}"
            )
        else:
            parts.append(
                "HUMAN NOTE: none supplied. Set "
                f"{', '.join(human_sections)} to null."
            )
    for key, data in gathers.items():
        label = key.upper().replace("_", " ")
        if isinstance(data, dict) and data.get("stub"):
            parts.append(
                f"{label}: unavailable this week ({data.get('reason')}). "
                "Do not invent material for it; lean on what you do have."
            )
            continue
        parts.append(f"{label} JSON:\n{json.dumps(data, ensure_ascii=False)}")
    return "\n\n".join(parts)


def synthesize(
    cfg: Config,
    issue_no: int,
    issue_date: date,
    gathers: Dict[str, Any],
    notes: Optional[str] = None,
) -> BaseModel:
    """One structured call. Returns a validated Issue instance."""
    import anthropic

    issue_model: Type[BaseModel] = build_issue_model(cfg.sections)
    client = anthropic.Anthropic()

    log("editor", f"synthesizing with {cfg.model}")
    response = client.messages.parse(
        model=cfg.model,
        max_tokens=cfg.max_tokens,
        thinking={"type": "adaptive"},
        system=build_system_prompt(cfg),
        messages=[
            {
                "role": "user",
                "content": build_user_message(cfg, issue_no, issue_date, gathers, notes),
            }
        ],
        output_format=issue_model,
    )
    if response.stop_reason == "refusal":
        detail = getattr(response.stop_details, "explanation", "") or ""
        raise RuntimeError(f"synthesis refused: {detail}")
    issue = response.parsed_output
    log(
        "editor",
        f"tokens in={response.usage.input_tokens} out={response.usage.output_tokens}",
    )
    return issue


def lint(cfg: Config, issue: BaseModel) -> None:
    """House rules the prompt is not trusted to hold on its own."""
    blob = issue.model_dump_json()
    for ch in cfg.style.banned_characters:
        if ch in blob:
            raise ValueError(f"banned character {ch!r} in issue copy")
    lowered = blob.lower()
    for phrase in cfg.style.banned_phrases:
        if phrase.lower() in lowered:
            raise ValueError(f"banned phrase {phrase!r} in issue copy")
    if cfg.style.max_subject_chars and len(issue.subject) > cfg.style.max_subject_chars:
        raise ValueError(
            f"subject is {len(issue.subject)} chars, "
            f"limit is {cfg.style.max_subject_chars}"
        )

    for spec in cfg.sections:
        value = getattr(issue, spec.id, None)
        if spec.required and value in (None, [], ""):
            raise ValueError(f"section {spec.id!r} is required but empty")
        if value is None:
            continue
        if isinstance(value, list):
            if spec.min is not None and len(value) < spec.min:
                raise ValueError(
                    f"section {spec.id!r}: {len(value)} entries, minimum {spec.min}"
                )
            if spec.max is not None and len(value) > spec.max:
                raise ValueError(
                    f"section {spec.id!r}: {len(value)} entries, maximum {spec.max}"
                )
            if spec.labels:
                got = [getattr(v, "label", None) for v in value]
                if got != spec.labels:
                    raise ValueError(
                        f"section {spec.id!r} labels {got} != configured {spec.labels}"
                    )
        if spec.both_sides and not (getattr(value, "other_side", "") or "").strip():
            raise ValueError(f"section {spec.id!r}: other_side is required")
        if cfg.style.require_urls:
            for entry in value if isinstance(value, list) else [value]:
                if hasattr(entry, "url") and entry.url is not None:
                    if not str(entry.url).startswith(("http://", "https://")):
                        raise ValueError(
                            f"section {spec.id!r}: {entry.url!r} is not a URL"
                        )


def sources_manifest(cfg: Config, issue: BaseModel) -> dict:
    """Every claim mapped to the URL behind it, for the human reviewer.

    This is the artefact that makes review possible in minutes instead of an
    hour: open it beside the draft and check the copy against the sources.
    """
    entries: List[dict] = []

    def add(section_id: str, claim: str, url: Optional[str]) -> None:
        entries.append({"section": section_id, "claim": claim, "url": url})

    for spec in cfg.sections:
        value = getattr(issue, spec.id, None)
        if value is None:
            continue
        if spec.type == "story":
            add(spec.id, value.headline, value.url)
        elif spec.type == "items":
            for item in value:
                add(spec.id, item.headline, item.url)
        elif spec.type == "debate":
            for pos in value.positions:
                add(spec.id, f"{pos.name}: {pos.position}", pos.url)
        elif spec.type == "bullets":
            for bullet in value:
                add(f"{spec.id}/{bullet.label.lower()}", bullet.fact, bullet.url)
    return {"sources": entries}
