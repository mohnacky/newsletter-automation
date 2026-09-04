"""Section types, and the dynamic Issue model built from a newsletter's config.

A newsletter is a list of sections. Each section has a *type* that fixes its
shape, so the editorial model is constrained by a real schema rather than by
prose asking it nicely. Adding a section to config/newsletter.yaml changes the
schema, the prompt, and the rendered output together.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, Field, create_model


class Story(BaseModel):
    """One lead item, told at length."""

    headline: str
    what_happened: str
    why_it_matters: str
    url: str
    # The case the item's framing leaves out. Required when a section sets
    # `both_sides: true`, so a lead can never run one-sided.
    other_side: Optional[str] = None


class Item(BaseModel):
    """One entry in a list section (a paper, a tool, a link)."""

    headline: str
    whats_new: str
    why_it_matters: str
    url: str


class Position(BaseModel):
    name: str
    position: str
    url: Optional[str] = None


class Debate(BaseModel):
    """Who is arguing what, and where it lands."""

    positions: List[Position]
    # The quote itself, with no surrounding quotation marks and no attribution
    # inside it. The renderer owns the punctuation, so a model that supplies
    # its own produces doubled quote marks.
    pull_quote: str
    pull_quote_attribution: Optional[str] = None
    bottom_line: str


class Bullet(BaseModel):
    """A short fact with a consequence. `label` groups them (Federal, Tools...)."""

    label: str
    fact: str
    implication: str
    url: Optional[str] = None


class Note(BaseModel):
    """Human-supplied colour. The model may only reformat what it is given."""

    scene: str
    why_it_matters: str


class Table(BaseModel):
    """A caption written by the model over rows it never sees.

    Rows are filled from gathered data after synthesis, so a number in a table
    cannot be invented.
    """

    caption: str
    rows: List[Dict[str, Any]] = Field(default_factory=list)


SECTION_TYPES: Dict[str, Tuple[Type[BaseModel], bool]] = {
    # type -> (item model, is_list)
    "story": (Story, False),
    "items": (Item, True),
    "debate": (Debate, False),
    "bullets": (Bullet, True),
    "note": (Note, False),
    "table": (Table, False),
}


class SectionSpec(BaseModel):
    """One section as declared in config."""

    id: str
    type: str
    title: str = ""
    kicker: str = ""
    framing: str = ""
    guidance: str = ""
    required: bool = False
    min: Optional[int] = None
    max: Optional[int] = None
    labels: List[str] = Field(default_factory=list)
    both_sides: bool = False
    source: str = "model"          # "model" | "human" | "gather"
    rows_from: Optional[str] = None  # for type: table
    columns: List[Dict[str, str]] = Field(default_factory=list)

    def field(self) -> Tuple[Any, Any]:
        """The (annotation, default) pair this section contributes to Issue."""
        model, is_list = SECTION_TYPES[self.type]
        if is_list:
            return (List[model], ... if self.required else [])  # type: ignore[valid-type]
        if self.required:
            return (model, ...)
        return (Optional[model], None)  # type: ignore[valid-type]


def build_issue_model(sections: List[SectionSpec]) -> Type[BaseModel]:
    """Compose the Issue schema the editorial model must fill in."""
    fields: Dict[str, Any] = {
        "subject": (str, ...),
        "preview_text": (str, ...),
        "headline": (str, ...),
        "thesis": (str, ...),
        "read_minutes": (int, ...),
    }
    for spec in sections:
        if spec.type not in SECTION_TYPES:
            raise ValueError(
                f"section {spec.id!r}: unknown type {spec.type!r}; "
                f"expected one of {sorted(SECTION_TYPES)}"
            )
        fields[spec.id] = spec.field()
    return create_model("Issue", **fields)
