"""Value lines for number parameters.

The help sentence is used as written when it already says what changing the
value does. Gemma rewrites only the short lines, one batch per node type,
and the result is kept for the rest of the session.
"""

from __future__ import annotations

import json
import os
import re
import threading
import urllib.request

from houdini_wizard.context import _effect_clause, _value_guide, plain
from houdini_wizard.pick import DEFAULT_MODEL, _skill

_CACHE: dict[tuple, str] = {}
_SKIP: set[tuple] = set()
_JOB = {"running": False}


def attach_guides(scene: dict, sections, allow_model: bool) -> None:
    ranges = scene.get("ranges") or {}
    tooltips = scene.get("tooltips") or {}
    guides: dict[str, str] = {}
    pending: list[dict] = []
    for section in sections:
        if getattr(section, "role", "") != "parameter" or section.options:
            continue
        span = ranges.get(section.heading)
        if not span:
            continue
        meaning = _meaning(section, tooltips)
        key = _key(section.heading, meaning, span)
        cached = _CACHE.get(key)
        guides[section.heading] = cached or _value_guide(section.heading, meaning, span)
        if cached or key in _SKIP or not allow_model or _effect_clause(meaning) or len(meaning) > 140:
            continue
        pending.append(
            {
                "name": section.heading,
                "help": meaning,
                "low": span.get("low"),
                "high": span.get("high"),
                "low_strict": bool(span.get("low_strict")),
                "high_strict": bool(span.get("high_strict")),
                "key": key,
            }
        )
    scene["guides"] = guides
    if pending:
        _schedule(pending[:12])


def _meaning(section, tooltips: dict) -> str:
    tooltip = plain(str(tooltips.get(section.heading, "") or ""))
    body = plain(section.body)
    return tooltip if len(tooltip) > len(body) else body


def _key(name: str, meaning: str, span: dict) -> tuple:
    return (
        name,
        meaning,
        span.get("low"),
        span.get("high"),
        bool(span.get("low_strict")),
        bool(span.get("high_strict")),
    )


def _schedule(pending: list[dict]) -> None:
    if _JOB["running"]:
        return
    _JOB["running"] = True

    def work() -> None:
        written: dict[str, str] = {}
        try:
            written = _ask(pending)
        except Exception:
            written = {}
        finally:
            _JOB["running"] = False
        changed = False
        for item in pending:
            text = written.get(item["name"], "")
            if text and _acceptable(text, item):
                _CACHE[item["key"]] = text
                changed = True
            else:
                _SKIP.add(item["key"])
        if changed:
            from houdini_wizard.shelf import note_guides_ready

            note_guides_ready()

    threading.Thread(target=work, name="houdini-wizard-values", daemon=True).start()


def _ask(pending: list[dict]) -> dict[str, str]:
    payload = {
        "model": os.environ.get("HOUDINI_WIZARD_MODEL", DEFAULT_MODEL),
        "stream": False,
        "format": {
            "type": "object",
            "properties": {
                "guides": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}, "text": {"type": "string"}},
                        "required": ["name", "text"],
                    },
                }
            },
            "required": ["guides"],
        },
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": _skill("houdini-values")},
            {"role": "user", "content": json.dumps([
                {
                    "name": item["name"],
                    "help": item["help"],
                    "low": item["low"],
                    "high": item["high"],
                    "outside_slider": not item["low_strict"] or not item["high_strict"],
                }
                for item in pending
            ])},
        ],
    }
    url = os.environ.get("HOUDINI_WIZARD_OLLAMA", "http://127.0.0.1:11434").rstrip("/") + "/api/chat"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = str(body.get("message", {}).get("content", "")).strip()
    parsed = json.loads(content)
    found: dict[str, str] = {}
    for item in parsed.get("guides") or []:
        name = str(item.get("name", "")).strip()
        text = " ".join(str(item.get("text", "")).split())
        if name and text:
            found[name] = text
    return found


def _acceptable(text: str, item: dict) -> bool:
    if "line above" in text.lower() or len(text) < 20 or len(text) > 420:
        return False
    allowed = {_fmt_number(item["low"]), _fmt_number(item["high"]), "0"}
    allowed.update(re.findall(r"\d+(?:\.\d+)?", item["help"]))
    for number in re.findall(r"\d+(?:\.\d+)?", text):
        if number not in allowed:
            return False
    return True


def _fmt_number(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.4f}".rstrip("0").rstrip(".")
