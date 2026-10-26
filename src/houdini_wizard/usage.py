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
    done = str(body.get("done_reason") or "").strip()
    if done and len(done) <= 40:
        usage["done_reason"] = done
    return usage


def skipped(task: str, reason: str) -> dict:
    return {"used": False, "task": task, "reason": reason}


def from_ps(body: dict, model: str) -> dict:
    """Memory of the loaded model, as Ollama's process list reports it."""
    models = body.get("models") if isinstance(body, dict) else None
    if not isinstance(models, list):
        return {}
    wanted = model.strip()
    chosen = None
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "")
        if name == wanted:
            chosen = item
            break
        if chosen is None and name.split(":")[0] == wanted.split(":")[0]:
            chosen = item
    if chosen is None:
        return {}
    found: dict = {}
    size = _bytes(chosen.get("size"))
    vram = _bytes(chosen.get("size_vram"))
    if size is not None:
        found["model_bytes"] = size
    if vram is not None:
        found["vram_bytes"] = vram
    return found


def attach_resident(usage: dict, *, base_url: str, model: str) -> dict:
    """Add resident memory when Ollama answers. A miss leaves the call record as it was."""
    import json
    import urllib.request

    url = base_url.rstrip("/") + "/api/ps"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            body = json.loads(response.read().decode("utf-8"))
    except Exception:
        return usage
    if isinstance(body, dict):
        usage.update(from_ps(body, model))
    return usage


def pending_pick(model: str) -> dict:
    return {
        "pending": True,
        "task": "pick a heading",
        "skill": "houdini-section",
        "model": model,
        "reason": "Gemma is choosing one heading from this file.",
    }


def _bytes(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or value > 200_000_000_000:
        return None
    return value


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
