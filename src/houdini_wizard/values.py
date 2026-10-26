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
from pathlib import Path

from houdini_wizard.context import _effect_clause, _value_guide, plain
from houdini_wizard.pick import DEFAULT_MODEL, _skill

_CACHE: dict[tuple, str] = {}
_SKIP: set[tuple] = set()
_JOB = {"running": False}
_LOADED = False


def _cache_path() -> Path:
    root = os.environ.get("HOUDINI_USER_PREF_DIR")
    if root:
        return Path(root) / "houdini_wizard" / "guides.json"
    return Path(__file__).resolve().parents[2] / ".temporal" / "guides.json"


def _load_cache() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    path = _cache_path()
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    for token, text in data.items():
        try:
            key = tuple(json.loads(token))
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(text, str) and text:
            _CACHE[key] = text


def _save_cache() -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {json.dumps(list(key), ensure_ascii=False): text for key, text in _CACHE.items()}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return


def attach_guides(scene: dict, sections, allow_model: bool) -> None:
    _load_cache()
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
        if cached or key in _SKIP or not allow_model or not _needs_model(meaning):
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
        _schedule(pending[:12], scene.get("path") or "", scene.get("type_label") or "")


def _meaning(section, tooltips: dict) -> str:
    tooltip = plain(str(tooltips.get(section.heading, "") or ""))
    body = plain(section.body)
    return tooltip if len(tooltip) > len(body) else body


def _needs_model(meaning: str) -> bool:
    """Gemma only when the tip is a short label and does not already say what the value does."""
    if _effect_clause(meaning):
        return False
    words = re.findall(r"[A-Za-z0-9']+", meaning)
    return len(words) <= 6


def _key(name: str, meaning: str, span: dict) -> tuple:
    return (
        name,
        meaning,
        span.get("low"),
        span.get("high"),
        bool(span.get("low_strict")),
        bool(span.get("high_strict")),
    )


def _schedule(pending: list[dict], node_path: str, type_label: str) -> None:
    if _JOB["running"]:
        return
    _JOB["running"] = True

    def work() -> None:
        written: dict[str, str] = {}
        try:
            written = _ask(pending, node_path, type_label)
        except Exception:
            written = {}
            from houdini_wizard.usage import skipped

            _note_model(
                skipped("write value lines", "Gemma did not answer."),
                node_path,
                type_label,
                {},
            )
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
            _save_cache()
            from houdini_wizard.shelf import note_guides_ready

            note_guides_ready()

    threading.Thread(target=work, name="houdini-wizard-values", daemon=True).start()


def _ask(pending: list[dict], node_path: str = "", type_label: str = "") -> dict[str, str]:
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
    from houdini_wizard.usage import from_ollama

    usage = from_ollama(body, model=payload["model"], skill="houdini-values", task="write value lines")
    from houdini_wizard.usage import attach_resident

    attach_resident(usage, base_url=url.rsplit("/api/chat", 1)[0], model=payload["model"])
    content = str(body.get("message", {}).get("content", "")).strip()
    parsed = json.loads(content)
    found: dict[str, str] = {}
    for item in parsed.get("guides") or []:
        name = str(item.get("name", "")).strip()
        text = " ".join(str(item.get("text", "")).split())
        if name and text:
            found[name] = text
    _note_model(usage, node_path, type_label, found)
    return found


def _note_model(usage: dict, node_path: str, type_label: str, written: dict) -> None:
    """One session line for a value-line model call. It is not a second card."""
    try:
        from houdini_wizard.usage import skipped
        from houdini_wizard.userlog import record

        if not usage:
            usage = skipped("write value lines", "Gemma did not answer.")
        record(
            {
                "state": "online" if usage.get("used") else "error",
                "title": "Model",
                "detail": "Gemma wrote short value lines." if written else "Gemma did not write value lines.",
                "node": node_path,
                "node_label": type_label or "Value lines",
                "headings": list(written)[:24],
                "usage": usage,
            }
        )
    except Exception:
        return


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
