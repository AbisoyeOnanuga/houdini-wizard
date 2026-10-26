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
_TITLES = {"Saving", "Saved", "Restored", "Not saved", "From this install", "Model"}
_STATES = {"working", "online", "restored", "offline", "error", "local"}


def record(event: dict) -> None:
    """Keep one line per node. Saving becomes Saved on that same line."""
    clean = sanitize(event)
    if clean is None:
        return
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = _stored(path)
        folded = _fold(existing + [clean])
        body = "\n".join(json.dumps(item, ensure_ascii=False) for item in folded[-KEEP:])
        path.write_text(body + "\n", encoding="utf-8")
    except OSError:
        return


def read_events() -> list[dict]:
    path = _path()
    if not path.is_file():
        return []
    try:
        return _fold(_stored(path))
    except OSError:
        return []


def _stored(path: Path) -> list[dict]:
    found: list[dict] = []
    raw = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
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


def _fold(events: list[dict]) -> list[dict]:
    """One card per open. A later Saved, Restored, or Not saved replaces Saving."""
    folded: list[dict] = []
    for item in events:
        if item.get("title") == "Model" or item.get("state") == "working" or not item.get("node"):
            folded.append(item)
            continue
        for index in range(len(folded) - 1, -1, -1):
            prior = folded[index]
            if prior.get("node") != item["node"]:
                continue
            if prior.get("title") == "Model":
                continue
            if prior.get("state") == "working":
                folded[index] = item
                break
            folded.append(item)
            break
        else:
            folded.append(item)
    return folded


def sanitize(event: dict, stamped: bool = False) -> dict | None:
    title = str(event.get("title") or "").strip()
    state = str(event.get("state") or "").strip()
    if title not in _TITLES or state not in _STATES:
        return None
    when = str(event.get("time") or "").strip() if stamped else ""
    if not when:
        when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    clean = {
        "time": when,
        "state": state,
        "title": title,
        "detail": _sentence(event.get("detail")),
        "node": _plain(event.get("node"), 160),
        "node_label": _plain(event.get("node_label"), 80),
        "heading": "" if _plain(event.get("heading"), 80) == "none" else _plain(event.get("heading"), 80),
        "parameter": _plain(event.get("parameter"), 80),
        "situation": _plain(event.get("situation"), 80),
        "quote": _excerpt(event.get("quote")),
        "error": _sentence(event.get("error")),
        "status_label": _plain(event.get("status_label"), 80),
        "headings": _names(event.get("headings")),
        "source": "From this install" if event.get("source") == "From this install" else "",
    }
    usage = _usage(event.get("usage"))
    if usage:
        clean["usage"] = usage
    return clean


def _usage(value) -> dict:
    if not isinstance(value, dict):
        return {}
    pending = bool(value.get("pending"))
    used = value.get("used")
    if used not in (True, False) and not pending:
        return {}
    clean: dict = {}
    if pending:
        clean["pending"] = True
    elif used is True:
        clean["used"] = True
    else:
        clean["used"] = False
    for key, limit in (("model", 40), ("skill", 40), ("task", 80)):
        text = _plain(value.get(key), limit)
        if text:
            clean[key] = text
    reason = _sentence(value.get("reason"))
    if reason:
        clean["reason"] = reason
    for key in ("prompt_tokens", "answer_tokens", "attempt", "load_ms", "prompt_ms", "answer_ms", "total_ms", "save_ms"):
        number = value.get(key)
        if isinstance(number, bool) or not isinstance(number, int):
            continue
        if 0 <= number <= 10_000_000:
            clean[key] = number
    return clean


def _excerpt(value) -> str:
    text = str(value or "").strip()
    paragraph = re.split(r"\n\s*\n", text, maxsplit=1)[0]
    lowered = paragraph.lower()
    if "traceback" in lowered or '.py", line' in lowered:
        return ""
    return _plain(paragraph, 360)


def _names(value) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        name = _plain(item, 80)
        if not name or name in names or name.startswith("wizard-"):
            continue
        names.append(name)
        if len(names) == 24:
            break
    return names


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
