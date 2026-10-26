"""Decide the card. Gemma runs only when the node is showing something that is not already a heading."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from houdini_wizard.card import card_from_heading, match_error, match_parameter
from houdini_wizard.help_file import Section
from houdini_wizard.usage import from_ollama, skipped

DEFAULT_MODEL = "gemma3:4b"
_NONE = "none"
_RECENT: dict = {}


def last_usage() -> dict:
    """The model report from the latest heading pick in this process."""
    return dict(_RECENT)


def decide(sections: tuple[Section, ...] | list[Section], parm_name: str, parm_label: str, error_text: str) -> dict:
    """Return the workflow request. A parameter match or a status that names a heading skips Gemma."""
    payload = [section.as_dict() for section in sections]
    # A selected parameter wins. What the node is showing is next: an error, a warning, or a message.
    matched = ""
    chosen = None
    if parm_name or parm_label:
        chosen = match_parameter(sections, parm_name, parm_label)
        if chosen is not None:
            matched = "parameter"
    if chosen is None and error_text.strip():
        chosen = match_error(sections, error_text)
        if chosen is not None:
            matched = "status"
    needs_model = chosen is None and bool(error_text.strip())
    return {
        "sections": payload,
        "headings": [section.heading for section in sections],
        "error_text": error_text.strip(),
        "known_heading": chosen.heading if chosen is not None else "",
        "needs_model": needs_model,
        "matched": matched,
    }


def finish(request: dict, heading: str | None = None) -> dict:
    chosen = heading if heading is not None else request.get("known_heading") or _NONE
    if request.get("needs_model") and heading is None:
        chosen = _NONE
    return card_from_heading(request["sections"], chosen)


def pick_heading(headings: list[str], error_text: str) -> str:
    """Ask local Gemma for one heading. The skill file is the system message."""
    if not headings:
        _remember(skipped("pick a heading", "This file has no headings, so Gemma was not asked."))
        return _NONE
    schema = {
        "type": "object",
        "properties": {
            "heading": {"type": "string", "enum": [*headings, _NONE]},
        },
        "required": ["heading"],
    }
    user = "Headings:\n" + "\n".join(f"- {heading}" for heading in headings)
    user += "\n\nWhat this node is showing:\n" + error_text.strip()
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
    model_name = payload["model"]
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        _remember(skipped("pick a heading", "Gemma did not answer."))
        raise RuntimeError(
            f"Ollama did not answer at {url}. Pull {model_name} and leave Ollama running."
        ) from exc
    _remember(from_ollama(body, model=model_name, skill="houdini-section", task="pick a heading"))
    content = body.get("message", {}).get("content", "")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemma did not return the heading JSON.") from exc
    heading = str(parsed.get("heading", _NONE)).strip()
    if heading not in headings:
        return _NONE
    return heading


def _remember(usage: dict) -> None:
    global _RECENT
    _RECENT = dict(usage)


def explain_context(error_text: str, heading: str, wires: list[str]) -> str:
    """A short note for a cook error that named no heading. The skill forbids invented values."""
    user = f"Cook error:\n{error_text.strip()}\n\nHeading:\n{heading}\n\nWires:\n" + "\n".join(wires)
    payload = {
        "model": os.environ.get("HOUDINI_WIZARD_MODEL", DEFAULT_MODEL),
        "stream": False,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": _skill("houdini-context")},
            {"role": "user", "content": user},
        ],
    }
    url = os.environ.get("HOUDINI_WIZARD_OLLAMA", "http://127.0.0.1:11434").rstrip("/") + "/api/chat"
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=90) as response:
        body = json.loads(response.read().decode("utf-8"))
    text = str(body.get("message", {}).get("content", "")).strip()
    parts = [part.strip() for part in text.replace("\n", " ").split(". ") if part.strip()]
    return ". ".join(parts[:3]).rstrip(".") + ("." if parts else "")


def skill_text() -> str:
    return _skill("houdini-section")


def _skill(name: str) -> str:
    override = os.environ.get("HOUDINI_WIZARD_SKILL")
    if override and name == "houdini-section":
        return Path(override).read_text(encoding="utf-8")
    root = Path(__file__).resolve().parents[2]
    path = root / "skills" / name / "SKILL.md"
    if not path.is_file():
        raise FileNotFoundError(f"skills/{name}/SKILL.md is missing. That file is an instruction Gemma receives.")
    return path.read_text(encoding="utf-8")
