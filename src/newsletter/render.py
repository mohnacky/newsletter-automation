"""Deterministic HTML rendering. The model writes copy; this module owns layout.

Email clients need inline styles and table-free-ish simple markup, so every
style here is inline and derived from the brand block in config. Nothing about
any particular newsletter is hardcoded.
"""

from __future__ import annotations

import html
from typing import Any, List, Optional
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

from pydantic import BaseModel

from .config import Config
from .schema import SectionSpec


def esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=True)


def tag_url(url: str, campaign: str, source: str) -> str:
    """Add UTM parameters so the destination can identify the traffic.

    Worth doing even if you never look at your ESP's numbers -- especially
    then. Provider click counts are heavily inflated by email security
    scanners; the destination side is where real visits can be counted.
    """
    if not url or not url.startswith(("http://", "https://")):
        return url
    parts = urlparse(url)
    query = dict(parse_qsl(parts.query))
    query.setdefault("utm_source", source)
    query.setdefault("utm_medium", "email")
    query.setdefault("utm_campaign", campaign)
    return urlunparse(parts._replace(query=urlencode(query)))


class Renderer:
    def __init__(self, cfg: Config, issue_no: int, date_str: str):
        self.cfg = cfg
        self.issue_no = issue_no
        self.date_str = date_str
        c = cfg.brand.colors
        f = cfg.brand.font_stack
        self.campaign = f"issue-{issue_no:03d}"
        self.utm_source = (cfg.brand.name or "newsletter").lower().replace(" ", "-")
        self.body = f"font-family:{f};font-size:17px;line-height:1.6;color:{c.ink};margin:0 0 16px 0;"
        self.muted = f"font-family:{f};font-size:14px;line-height:1.5;color:{c.muted};margin:0 0 14px 0;"
        self.kicker = (
            f"font-family:{f};font-size:11px;font-weight:700;letter-spacing:2px;"
            f"text-transform:uppercase;color:{c.accent};margin:0 0 6px 0;"
        )
        self.h2 = f"font-family:{f};font-size:24px;line-height:1.25;color:{c.ink};margin:0 0 10px 0;"
        self.h3 = f"font-family:{f};font-size:19px;line-height:1.3;color:{c.ink};margin:0 0 8px 0;"
        self.link = f"color:{c.accent};text-decoration:underline;"
        self.rule = f'<hr style="border:none;border-top:1px solid {c.rule};margin:32px 0;">'

    # -- helpers ---------------------------------------------------------
    def a(self, url: str, text: str) -> str:
        return f'<a href="{esc(tag_url(url, self.campaign, self.utm_source))}" style="{self.link}">{esc(text)}</a>'

    def p(self, text: str, style: Optional[str] = None) -> str:
        return f'<p style="{style or self.body}">{esc(text)}</p>'

    def header(self, spec: SectionSpec) -> str:
        out = []
        if spec.kicker:
            out.append(f'<p style="{self.kicker}">{esc(spec.kicker)}</p>')
        if spec.title:
            out.append(f'<h2 style="{self.h2}">{esc(spec.title)}</h2>')
        if spec.framing:
            out.append(self.p(spec.framing, self.muted))
        return "\n".join(out)

    def signpost(self, label: str, text: str) -> str:
        return (
            f'<p style="{self.body}"><strong>{esc(label)}</strong> {esc(text)}</p>'
        )

    # -- section types ---------------------------------------------------
    def story(self, spec: SectionSpec, v: Any) -> str:
        out = [self.header(spec), f'<h3 style="{self.h3}">{esc(v.headline)}</h3>']
        out.append(self.signpost("What happened.", v.what_happened))
        out.append(self.signpost("Why it matters.", v.why_it_matters))
        if v.other_side:
            out.append(self.signpost("The other side.", v.other_side))
        out.append(self.p_raw(self.a(v.url, "Read the source")))
        return "\n".join(out)

    def items(self, spec: SectionSpec, v: List[Any]) -> str:
        out = [self.header(spec)]
        for item in v:
            out.append(f'<h3 style="{self.h3}">{esc(item.headline)}</h3>')
            out.append(self.signpost("What's new.", item.whats_new))
            out.append(self.signpost("Why it matters.", item.why_it_matters))
            out.append(self.p_raw(self.a(item.url, "Read it")))
        return "\n".join(out)

    def debate(self, spec: SectionSpec, v: Any) -> str:
        out = [self.header(spec)]
        for pos in v.positions:
            name = self.a(pos.url, pos.name) if pos.url else esc(pos.name)
            out.append(
                f'<p style="{self.body}"><strong>{name}</strong> {esc(pos.position)}</p>'
            )
        c = self.cfg.brand.colors
        out.append(
            f'<blockquote style="margin:20px 0;padding:12px 18px;'
            f'border-left:3px solid {c.accent};font-family:{self.cfg.brand.font_stack};'
            f'font-size:18px;line-height:1.5;color:{c.ink};font-style:italic;">'
            f"{esc(v.pull_quote)}</blockquote>"
        )
        out.append(self.signpost("Bottom line.", v.bottom_line))
        return "\n".join(out)

    def bullets(self, spec: SectionSpec, v: List[Any]) -> str:
        out = [self.header(spec)]
        for b in v:
            link = f' {self.a(b.url, "Source")}' if b.url else ""
            out.append(
                f'<p style="{self.body}"><strong>{esc(b.label)}.</strong> '
                f"{esc(b.fact)} <span style=\"color:{self.cfg.brand.colors.muted};\">"
                f"{esc(b.implication)}</span>{link}</p>"
            )
        return "\n".join(out)

    def note(self, spec: SectionSpec, v: Any) -> str:
        return "\n".join(
            [self.header(spec), self.p(v.scene), self.signpost("Why it matters.", v.why_it_matters)]
        )

    def table(self, spec: SectionSpec, v: Any) -> str:
        c = self.cfg.brand.colors
        f = self.cfg.brand.font_stack
        cols = spec.columns or [
            {"key": k, "label": k.title()} for k in (v.rows[0].keys() if v.rows else [])
        ]
        head = "".join(
            f'<th style="font-family:{f};font-size:12px;text-transform:uppercase;'
            f'letter-spacing:1px;color:{c.muted};text-align:left;padding:8px 10px;'
            f'border-bottom:1px solid {c.rule};">{esc(col["label"])}</th>'
            for col in cols
        )
        rows = []
        for row in v.rows:
            cells = "".join(
                f'<td style="font-family:{f};font-size:15px;color:{c.ink};'
                f'padding:8px 10px;border-bottom:1px solid {c.rule};">'
                f'{esc(row.get(col["key"], ""))}</td>'
                for col in cols
            )
            rows.append(f"<tr>{cells}</tr>")
        table = (
            f'<table role="presentation" cellpadding="0" cellspacing="0" '
            f'style="width:100%;border-collapse:collapse;margin:0 0 14px 0;">'
            f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        )
        return "\n".join([self.header(spec), table, self.p(v.caption, self.muted)])

    def p_raw(self, inner: str) -> str:
        return f'<p style="{self.muted}">{inner}</p>'

    # -- top level -------------------------------------------------------
    def masthead(self, issue: BaseModel) -> str:
        c = self.cfg.brand.colors
        f = self.cfg.brand.font_stack
        return "\n".join(
            [
                f'<p style="font-family:{f};font-size:13px;color:{c.muted};margin:0 0 18px 0;">'
                f"Issue {self.issue_no:03d} &middot; {esc(self.date_str)} &middot; "
                f"{esc(issue.read_minutes)} min read</p>",
                f'<h1 style="font-family:{f};font-size:30px;line-height:1.2;'
                f'color:{c.ink};margin:0 0 12px 0;">{esc(issue.headline)}</h1>',
                self.p(issue.thesis),
            ]
        )

    def render(self, issue: BaseModel) -> str:
        blocks = [self.masthead(issue)]
        for spec in self.cfg.sections:
            value = getattr(issue, spec.id, None)
            if value in (None, []):
                continue
            fn = getattr(self, spec.type)
            blocks.append(fn(spec, value))
        return f"\n{self.rule}\n".join(blocks)


def render_body(cfg: Config, issue: BaseModel, issue_no: int, date_str: str) -> str:
    return Renderer(cfg, issue_no, date_str).render(issue)


def render_preview(cfg: Config, body: str, subject: str) -> str:
    """A full HTML page for eyeballing the issue in a browser before delivery."""
    c = cfg.brand.colors
    return (
        "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
        f"<title>{esc(subject)}</title>"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"</head><body style=\"margin:0;background:#F3F4F6;\">"
        f'<div style="max-width:600px;margin:0 auto;background:{c.page};'
        f'padding:32px 24px;">{body}</div></body></html>'
    )
