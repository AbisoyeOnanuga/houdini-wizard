"""Headings already chosen for a cook error.

One small file on this computer. A node click that only quotes installed
help never writes here, and it never starts a workflow. The file keeps the
newest model picks and drops the older ones.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

KEEP = 64


def uses_workflow(request: dict) -> bool:
    """True only when Gemma has to choose a heading."""
    return bool(request.get("needs_model")) and not request.get("known_heading")


def heading_of(card: dict) -> str:
    recorded = card.get("heading")
    if isinstance(recorded, str) and recorded:
        return recorded
    if card.get("kind") == "quote" and card.get("title"):
        return str(card["title"])
    return "none"


def recall(card_id: str) -> str | None:
    heading = _read()["headings"].get(card_id)
    if isinstance(heading, str) and heading:
        return heading
    return None


def remember(card_id: str, heading: str) -> bool:
    """Keep this heading and forget the ones past the newest window."""
    data = _read()
    order = [item for item in data["order"] if item != card_id]
    order.append(card_id)
    data["headings"][card_id] = heading or "none"
    while len(order) > KEEP:
        dropped = order.pop(0)
        data["headings"].pop(dropped, None)
    data["order"] = order
    return _write(data)


def _path() -> Path:
    root = os.environ.get("HOUDINI_USER_PREF_DIR")
    if root:
        return Path(root) / "houdini_wizard" / "cards.json"
    return Path(__file__).resolve().parents[2] / ".temporal" / "cards.json"


def _read() -> dict:
    path = _path()
    if not path.is_file():
        return {"order": [], "headings": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"order": [], "headings": {}}
    order = data.get("order") if isinstance(data, dict) else None
    headings = data.get("headings") if isinstance(data, dict) else None
    if not isinstance(order, list) or not isinstance(headings, dict):
        return {"order": [], "headings": {}}
    return {"order": [item for item in order if isinstance(item, str)], "headings": headings}


def _write(data: dict) -> bool:
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return False
    return True
