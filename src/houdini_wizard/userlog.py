"""A readable session log for the person using the tool.

The Temporal monitor stays the developer view. This file keeps the same
updates in plain language: which node, which heading, and whether it was
saved, restored, or not saved. Workflow ids and Python errors are left out.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

PAGE_PORT = 8244
KEEP = 200
_TITLES = {"Saving", "Saved", "Restored", "Not saved", "From this install"}
_STATES = {"working", "online", "restored", "offline", "error", "local"}


def record(event: dict) -> None:
    """Append one sanitized update. The newest entries are kept."""
    clean = sanitize(event)
    if clean is None:
        return
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        if path.is_file():
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        lines.append(json.dumps(clean, ensure_ascii=False))
        path.write_text("\n".join(lines[-KEEP:]) + "\n", encoding="utf-8")
    except OSError:
        return


def read_events() -> list[dict]:
    path = _path()
    if not path.is_file():
        return []
    found: list[dict] = []
    try:
        raw = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in raw:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            clean = sanitize(item, stamped=True)
            if clean is not None:
                found.append(clean)
    return found


def sanitize(event: dict, stamped: bool = False) -> dict | None:
    title = str(event.get("title") or "").strip()
    state = str(event.get("state") or "").strip()
    if title not in _TITLES or state not in _STATES:
        return None
    when = str(event.get("time") or "").strip() if stamped else ""
    if not when:
        when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "time": when,
        "state": state,
        "title": title,
        "detail": _sentence(event.get("detail")),
        "node": _plain(event.get("node"), 160),
        "node_label": _plain(event.get("node_label"), 80),
        "heading": _plain(event.get("heading"), 80),
        "source": "From this install" if event.get("source") == "From this install" else "",
    }


def _sentence(value) -> str:
    text = _plain(value, 240)
    lowered = text.lower()
    if "traceback" in lowered or '.py", line' in lowered or "exception" in lowered:
        return "This step could not be saved."
    return text


def _plain(value, limit: int) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _path() -> Path:
    override = os.environ.get("HOUDINI_WIZARD_USERLOG")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / ".temporal" / "user-log.jsonl"
