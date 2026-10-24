"""Decide the card. Gemma runs only when a cook error names no heading."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from houdini_wizard.card import card_from_heading, match_error, match_parameter
from houdini_wizard.help_file import Section

DEFAULT_MODEL = "gemma3:4b"
_NONE = "none"


def decide(sections: tuple[Section, ...] | list[Section], parm_name: str, parm_label: str, error_text: str) -> dict:
    """Return the workflow request. Exact matches set known_heading and skip Gemma."""
    payload = [section.as_dict() for section in sections]
    # A selected parameter wins. If that name is not a heading, the cook error is next.
    if parm_name or parm_label:
        chosen = match_parameter(sections, parm_name, parm_label)
        if chosen is None:
            chosen = match_error(sections, error_text)
    else:
        chosen = match_error(sections, error_text)
    needs_model = chosen is None and bool(error_text.strip())
    return {
        "sections": payload,
        "headings": [section.heading for section in sections],
        "error_text": error_text.strip(),
        "known_heading": chosen.heading if chosen is not None else "",
        "needs_model": needs_model,
    }


def finish(request: dict, heading: str | None = None) -> dict:
    chosen = heading if heading is not None else request.get("known_heading") or _NONE
    if request.get("needs_model") and heading is None:
        chosen = _NONE
    return card_from_heading(request["sections"], chosen)


def pick_heading(headings: list[str], error_text: str) -> str:
    """Ask local Gemma for one heading. The skill file is the system message."""
    if not headings:
        return _NONE
    schema = {
        "type": "object",
        "properties": {
            "heading": {"type": "string", "enum": [*headings, _NONE]},
        },
        "required": ["heading"],
    }
    user = "Headings:\n" + "\n".join(f"- {heading}" for heading in headings)
    user += "\n\nCook error:\n" + error_text.strip()
    payload = {
        "model": os.environ.get("HOUDINI_WIZARD_MODEL", DEFAULT_MODEL),
        "stream": False,
        "format": schema,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": skill_text()},
            {"role": "user", "content": user},
        ],
    }
    url = os.environ.get("HOUDINI_WIZARD_OLLAMA", "http://127.0.0.1:11434").rstrip("/") + "/api/chat"
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Ollama did not answer at {url}. Pull {payload['model']} and leave Ollama running."
        ) from exc
    content = body.get("message", {}).get("content", "")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemma did not return the heading JSON.") from exc
    heading = str(parsed.get("heading", _NONE)).strip()
    if heading not in headings:
        return _NONE
    return heading


def skill_text() -> str:
    override = os.environ.get("HOUDINI_WIZARD_SKILL")
    if override:
        return Path(override).read_text(encoding="utf-8")
    root = Path(__file__).resolve().parents[2]
    path = root / "skills" / "houdini-section" / "SKILL.md"
    if not path.is_file():
        raise FileNotFoundError(
            "skills/houdini-section/SKILL.md is missing. That file is the instruction Gemma receives."
        )
    return path.read_text(encoding="utf-8")
