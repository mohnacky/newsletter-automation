"""Wrap the rendered body in the email chrome and required footer."""

from __future__ import annotations

from .common import TEMPLATES_DIR
from .config import Config

# Placeholders the delivery layer substitutes. SendGrid resolves triple-brace
# handlebars to raw URLs; other providers use their own tokens, which is why
# they are configurable rather than baked in.
DEFAULT_TOKENS = {
    "unsubscribe_url": "{{{unsubscribe}}}",
    "preferences_url": "{{{unsubscribe_preferences}}}",
}


def preheader(preview_text: str) -> str:
    """Hidden preview text.

    The trailing padding stops mail clients pulling body copy into the inbox
    snippet after a short preview line.
    """
    pad = "&nbsp;&zwnj;" * 90
    return (
        '<div style="display:none;font-size:1px;line-height:1px;max-height:0;'
        f'max-width:0;opacity:0;overflow:hidden;">{preview_text}{pad}</div>'
    )


def assemble(cfg: Config, body: str, preview_text: str, tokens: dict = None) -> str:
    """Chrome + preheader + body + footer, ready to paste or upload."""
    if not cfg.brand.address:
        raise ValueError(
            "brand.address is empty. A physical mailing address is legally "
            "required in commercial email (CAN-SPAM); set it in config."
        )
    tokens = {**DEFAULT_TOKENS, **(tokens or {})}
    template = (TEMPLATES_DIR / "email.html").read_text()
    c = cfg.brand.colors
    return (
        template.replace("{{ preheader }}", preheader(preview_text))
        .replace("{{ content }}", body)
        .replace("{{ brand_name }}", cfg.brand.name)
        .replace("{{ tagline }}", cfg.brand.tagline)
        .replace("{{ address }}", cfg.brand.address)
        .replace("{{ site_url }}", cfg.brand.site_url)
        .replace("{{ font_stack }}", cfg.brand.font_stack)
        .replace("{{ color_ink }}", c.ink)
        .replace("{{ color_muted }}", c.muted)
        .replace("{{ color_accent }}", c.accent)
        .replace("{{ color_rule }}", c.rule)
        .replace("{{ color_page }}", c.page)
        .replace("{{ unsubscribe_url }}", tokens["unsubscribe_url"])
        .replace("{{ preferences_url }}", tokens["preferences_url"])
    )
