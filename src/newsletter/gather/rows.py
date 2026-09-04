"""Tabular rows from a local file you maintain (CSV or JSON).

The point of this source is that a table's numbers never pass through the
model: it writes the caption, this reads the figures. Point it at whatever you
export each week.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Optional

from ..common import ROOT, log, stub


def run(path: Optional[str] = None, **_ignored) -> dict:
    if not path:
        return stub("rows", "no path configured")
    target = Path(path)
    if not target.is_absolute():
        target = ROOT / target
    if not target.exists():
        return stub("rows", f"{target} not found")

    text = target.read_text()
    if target.suffix.lower() == ".json":
        data = json.loads(text)
        rows = data.get("rows", data) if isinstance(data, dict) else data
    else:
        rows = list(csv.DictReader(io.StringIO(text)))
    log("rows", f"{len(rows)} rows from {target.name}")
    return {"rows": rows}
