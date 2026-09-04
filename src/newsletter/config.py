"""Load and validate a newsletter definition.

Everything that makes a newsletter *yours* -- name, colours, sections, sources,
house style -- lives in YAML. The code below is the only place that knows how
those files are shaped.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

from .common import CONFIG_DIR, PROMPTS_DIR
from .schema import SectionSpec


class Colors(BaseModel):
    ink: str = "#1F2430"
    muted: str = "#6B7280"
    accent: str = "#2563EB"
    rule: str = "#E5E7EB"
    page: str = "#FFFFFF"


class Brand(BaseModel):
    name: str
    tagline: str = ""
    from_name: str = ""
    from_email: str = ""
    site_url: str = ""
    # Physical mailing address. CAN-SPAM requires one in every commercial email;
    # the default template refuses to render without it.
    address: str = ""
    font_stack: str = "Helvetica,Arial,sans-serif"
    colors: Colors = Field(default_factory=Colors)


class GatherSpec(BaseModel):
    """One gather stage. Extra keys are passed through to the source module."""

    model_config = {"extra": "allow"}

    id: str
    source: str
    enabled: bool = True

    def options(self) -> Dict[str, Any]:
        known = {"id", "source", "enabled"}
        return {k: v for k, v in self.model_dump().items() if k not in known}


class Style(BaseModel):
    """House rules enforced mechanically after synthesis.

    A prompt asks; a lint rule guarantees. Anything here that the model gets
    wrong fails the run loudly instead of shipping.
    """

    banned_characters: List[str] = Field(default_factory=list)
    banned_phrases: List[str] = Field(default_factory=list)
    max_subject_chars: Optional[int] = None
    require_urls: bool = True


class Config(BaseModel):
    brand: Brand
    sections: List[SectionSpec]
    gather: List[GatherSpec] = Field(default_factory=list)
    style: Style = Field(default_factory=Style)
    model: str = "claude-opus-5"
    max_tokens: int = 16000
    prompt: str = "editorial.md"
    delivery: str = "file"
    send_day: str = "Wednesday"

    def section(self, section_id: str) -> Optional[SectionSpec]:
        return next((s for s in self.sections if s.id == section_id), None)

    def prompt_path(self) -> Path:
        p = Path(self.prompt)
        return p if p.is_absolute() else PROMPTS_DIR / p


def load_config(path: Optional[Path] = None) -> Config:
    """Read a newsletter definition. Defaults to config/newsletter.yaml."""
    path = Path(path) if path else CONFIG_DIR / "newsletter.yaml"
    if not path.exists():
        raise SystemExit(
            f"no newsletter config at {path}\n"
            "Copy examples/demo/newsletter.yaml to config/newsletter.yaml to start."
        )
    data = yaml.safe_load(path.read_text()) or {}
    cfg = Config(**data)
    ids = [s.id for s in cfg.sections]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate section ids in {path}: {sorted(dupes)}")
    for spec in cfg.sections:
        if spec.type == "table" and not spec.rows_from:
            raise ValueError(f"section {spec.id!r} is a table and needs rows_from")
    return cfg
