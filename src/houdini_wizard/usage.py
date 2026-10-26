"""What a local Gemma call actually cost on this computer.

Ollama reports prompt tokens, answer tokens, and durations. Those numbers
are copied through. A call that did not happen stays marked unused. Nothing
here prices a token, because this model is running locally.
"""

from __future__ import annotations


def from_ollama(body: dict, *, model: str, skill: str, task: str) -> dict:
    """Read token counts and durations from one Ollama chat response."""
    usage = {
        "used": True,
        "model": str(body.get("model") or model or ""),
        "skill": skill,
        "task": task,
    }
    for key, source in (("prompt_tokens", "prompt_eval_count"), ("answer_tokens", "eval_count")):
        number = _count(body.get(source))
        if number is not None:
            usage[key] = number
    for key, source in (
        ("load_ms", "load_duration"),
        ("prompt_ms", "prompt_eval_duration"),
        ("answer_ms", "eval_duration"),
        ("total_ms", "total_duration"),
    ):
        number = _millis(body.get(source))
        if number is not None:
            usage[key] = number
    return usage


def skipped(task: str, reason: str) -> dict:
    return {"used": False, "task": task, "reason": reason}


def pending_pick(model: str) -> dict:
    return {
        "pending": True,
        "task": "pick a heading",
        "skill": "houdini-section",
        "model": model,
        "reason": "Gemma is choosing one heading from this file.",
    }


def _count(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or value > 10_000_000:
        return None
    return value


def _millis(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0:
        return None
    millis = int(round(value / 1_000_000))
    if millis > 600_000:
        return None
    return millis
