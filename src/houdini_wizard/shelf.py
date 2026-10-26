"""hython shelf. Reads the selection, stores the card, opens the dialog."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from houdini_wizard.help_file import installed_help
from houdini_wizard.panel import show_panel
from houdini_wizard.memory import recall, uses_workflow
from houdini_wizard.pick import DEFAULT_MODEL, decide, finish, last_usage, pick_heading
from houdini_wizard.usage import pending_pick, skipped
from houdini_wizard.service import ensure_running, history_exists, worker_python
from houdini_wizard.userlog import record
from houdini_wizard.workflow import _log_card, connect, open_card, plain_reason, workflow_id

_seen = {"signature": None, "guide_token": 0, "status_token": 0, "shown_status": 0}
_LOG = Path(__file__).resolve().parents[2] / ".temporal" / "shelf.log"


def show_card() -> None:
    import hou

    _seen.setdefault(
        "session",
        _service("working", "Starting the recovery service for this session."),
    )
    threading.Thread(target=_warm_service, name="houdini-wizard-service", daemon=True).start()

    selected = _selection(hou, announce=False)
    if selected is None:
        _seen["browsing"] = True
        _seen["browse_hold"] = None
        _seen["signature"] = ("library",)
        hfs = hou.getenv("HFS") or os.environ.get("HFS", "")
        from houdini_wizard.panel import show_library

        show_library(hfs, refresh=lambda: _poll(hou))
        return
    _seen["browsing"] = False
    node, parm_name, parm_label, error_text, status_label = selected
    try:
        category = node.type().category().name()
        internal = node.type().nameComponents()[2]
        hfs = hou.getenv("HFS") or os.environ.get("HFS", "")
        help_file = installed_help(category, internal, hfs)
    except FileNotFoundError as exc:
        hou.ui.displayMessage(
            f"This install has no help file for the node.\n{exc}",
            title="Houdini wizard",
            severity=hou.severityType.Warning,
        )
        return
    request = _note_node(decide(help_file.sections, parm_name, parm_label, error_text), node, parm_label)
    request["status_label"] = status_label
    card_id = workflow_id(node.path(), parm_name or parm_label, error_text)
    _present(card_id, request)
    scene = _scene(node, error_text, hfs, help_file.includes, parm_label)
    _attach_service(scene, card_id)
    from houdini_wizard.values import attach_guides

    attach_guides(scene, help_file.sections, allow_model=True)
    focus = _focus_for(card_id, request, parm_label)
    _seen["signature"] = _signature(node, parm_name, parm_label, error_text)
    _seen["shown_status"] = _seen.get("status_token", 0)
    show_panel(help_file.sections, scene, focus, "", refresh=lambda: _poll(hou))


def _warm_service() -> None:
    had_history = history_exists()
    try:
        ensure_running()
        _log("service ready")
        if had_history:
            service = _service(
                "restored",
                "The recovery service is back for this session. Headings kept earlier are still on this computer.",
            )
        else:
            service = _service(
                "online",
                "The recovery service is running for this session. Closing Houdini stops it.",
            )
    except Exception as exc:
        _log(f"service {exc}")
        service = _failure_service(exc)
    _seen["session"] = service
    _seen["status_token"] = _seen.get("status_token", 0) + 1
    record(
        {
            "state": service["state"],
            "title": service["title"],
            "detail": service["detail"],
            "node_label": "This session",
        }
    )


def _selection(hou, announce: bool = True):
    nodes = list(hou.selectedNodes())
    parm = _selected_parm(hou, nodes[0] if nodes else None)
    node = parm.node() if parm is not None else (nodes[0] if nodes else None)
    if node is None:
        if announce and hasattr(hou, "ui"):
            hou.ui.displayMessage("Select a node, then click the shelf.", title="Houdini wizard")
        return None
    parm_name = parm.name() if parm is not None else ""
    parm_label = ""
    if parm is not None:
        parm_label = parm.description() or parm.parmTemplate().label()
    error_text, status_label = _node_report(node)
    return node, parm_name, parm_label, error_text, status_label


def _node_report(node) -> tuple[str, str]:
    """What the node is showing in the network editor: errors, warnings, and messages."""
    lines: list[str] = []
    labels: list[str] = []
    for label, method_name in (("Error", "errors"), ("Warning", "warnings"), ("Message", "messages")):
        method = getattr(node, method_name, None)
        if not callable(method):
            continue
        try:
            raw = method()
        except Exception:
            continue
        if isinstance(raw, (list, tuple)):
            texts = [str(item).strip() for item in raw if str(item).strip()]
        elif str(raw or "").strip():
            texts = [str(raw).strip()]
        else:
            texts = []
        if not texts:
            continue
        labels.append(label)
        lines.extend(f"{label}: {text}" for text in texts)
    if not labels:
        return "", ""
    if len(labels) == 1:
        brief = labels[0]
    elif len(labels) == 2:
        brief = f"{labels[0]} and {labels[1]}"
    else:
        brief = f"{', '.join(labels[:-1])}, and {labels[-1]}"
    return "\n".join(lines), brief


def hold_for_browse(hou) -> None:
    """Keep the library on screen until the network selection changes."""
    selected = _selection(hou, announce=False)
    if selected is None:
        _seen["browse_hold"] = None
    else:
        node, parm_name, parm_label, error_text, status_label = selected
        _seen["browse_hold"] = _signature(node, parm_name, parm_label, error_text)
    _seen["browsing"] = True
    _seen["signature"] = ("library",)


def _poll(hou):
    selected = _selection(hou, announce=False)
    if selected is None:
        return None
    node, parm_name, parm_label, error_text, status_label = selected
    signature = _signature(node, parm_name, parm_label, error_text)
    if _seen.get("browsing"):
        if signature == _seen.get("browse_hold"):
            return None
        _seen["browsing"] = False
    status_only = signature == _seen["signature"] and _seen.get("shown_status") != _seen.get("status_token")
    if signature == _seen["signature"] and not status_only:
        return None
    try:
        category = node.type().category().name()
        internal = node.type().nameComponents()[2]
        hfs = hou.getenv("HFS") or os.environ.get("HFS", "")
        help_file = installed_help(category, internal, hfs)
    except Exception:
        return None
    request = _note_node(decide(help_file.sections, parm_name, parm_label, error_text), node, parm_label)
    request["status_label"] = status_label
    card_id = workflow_id(node.path(), parm_name or parm_label, error_text)
    if not status_only:
        _present(card_id, request)
    _seen["signature"] = signature
    _seen["shown_status"] = _seen.get("status_token", 0)
    scene = _scene(node, error_text, hfs, help_file.includes, parm_label)
    _attach_service(scene, card_id)
    if not status_only:
        from houdini_wizard.values import attach_guides

        attach_guides(scene, help_file.sections, allow_model=True)
    focus = _focus_for(card_id, request, parm_label)
    return help_file.sections, scene, focus, ""


def _note_node(request: dict, node, parm_label: str) -> dict:
    noted = dict(request)
    try:
        noted["node_path"] = node.path()
    except Exception:
        noted["node_path"] = ""
    noted["type_label"] = _type_label(node)
    noted["shown_parm"] = parm_label
    return noted


def _signature(node, parm_name: str, parm_label: str, error_text: str) -> tuple:
    try:
        internal = node.type().nameComponents()[2]
    except Exception:
        internal = ""
    wired = []
    for row in _ends(node, incoming=True) + _ends(node, incoming=False):
        wired.append((row.get("label"), row.get("wired")))
    current = ""
    if parm_label:
        current = _values(node).get(parm_label, "")
    return (node.path(), internal, parm_name, parm_label, error_text.strip(), tuple(wired), current, _seen.get("guide_token", 0))


def note_guides_ready() -> None:
    _seen["guide_token"] = _seen.get("guide_token", 0) + 1


def _scene(node, error_text: str, hfs: str = "", includes: tuple[str, ...] = (), parm_label: str = "") -> dict:
    return {
        "type_label": _type_label(node),
        "category": node.type().category().name(),
        "path": node.path(),
        "icon": _icon_name(node),
        "hfs": hfs,
        "includes": list(includes),
        "error": error_text,
        "parm_label": parm_label,
        "values": _values(node),
        "ranges": _ranges(node),
        "tooltips": _tooltips(node),
        "inputs": _ends(node, incoming=True),
        "outputs": _ends(node, incoming=False),
    }


def _icon_name(node) -> str:
    try:
        return node.type().icon() or ""
    except Exception:
        return ""


def _values(node) -> dict:
    found: dict[str, str] = {}
    try:
        parms = node.parms()
    except Exception:
        return found
    for parm in parms:
        try:
            label = parm.parmTemplate().label()
        except Exception:
            continue
        if not label or label in found:
            continue
        found[label] = _display(parm)
    return found


def _display(parm) -> str:
    try:
        template = parm.parmTemplate()
        kind = template.type()
        import hou

        if kind == hou.parmTemplateType.Menu:
            labels = list(parm.menuLabels() or [])
            index = parm.eval()
            if isinstance(index, int) and 0 <= index < len(labels):
                return str(labels[index])
        if kind == hou.parmTemplateType.Toggle:
            return "on" if parm.eval() else "off"
        text = str(parm.evalAsString())
        return text if len(text) <= 80 else text[:77] + "..."
    except Exception:
        return ""


def _tooltips(node) -> dict:
    found: dict[str, str] = {}
    try:
        parms = node.parms()
    except Exception:
        return found
    for parm in parms:
        try:
            label = parm.parmTemplate().label()
            text = parm.parmTemplate().help() or ""
        except Exception:
            continue
        if label and text.strip() and label not in found:
            found[label] = text.strip()
    return found


def _ranges(node) -> dict:
    found: dict[str, dict] = {}
    try:
        parms = node.parms()
    except Exception:
        return found
    for parm in parms:
        try:
            label = parm.parmTemplate().label()
        except Exception:
            continue
        if not label or label in found:
            continue
        span = _span(parm)
        if span:
            found[label] = span
    return found


def _span(parm) -> dict | None:
    try:
        import hou

        template = parm.parmTemplate()
        if template.type() not in {hou.parmTemplateType.Float, hou.parmTemplateType.Int}:
            return None
        low = float(template.minValue())
        high = float(template.maxValue())
        if low >= high or abs(low) > 1_000_000 or abs(high) > 1_000_000:
            return None
        return {
            "low": low,
            "high": high,
            "low_strict": bool(template.minIsStrict()),
            "high_strict": bool(template.maxIsStrict()),
        }
    except Exception:
        return None


def _type_label(node) -> str:
    try:
        return node.type().description() or node.type().name()
    except Exception:
        return node.type().name()


def _ends(node, incoming: bool) -> list[dict]:
    try:
        labels = list(node.inputLabels() if incoming else node.outputLabels() or [])
        wires = list(node.inputs() if incoming else node.outputs() or [])
    except Exception:
        return []
    rows: list[dict] = []
    if incoming:
        for index, label in enumerate(labels):
            other = wires[index] if index < len(wires) else None
            rows.append({"label": str(label), "wired": _other_name(other)})
        return rows
    names = [_other_name(other) for other in wires]
    names = [name for name in names if name]
    if labels or names:
        rows.append({"label": str(labels[0]) if labels else "Output", "wired": ", ".join(names)})
    return rows


def _other_name(other) -> str:
    if other is None:
        return ""
    try:
        return other.type().description() or other.name()
    except Exception:
        return ""


def _selected_parm(hou, node):
    """The parameter whose channel is selected on this node, if Houdini has one."""
    if node is None or not hasattr(hou, "ui"):
        return None
    try:
        editors = [tab for tab in hou.ui.paneTabs() if tab.type() == hou.paneTabType.ChannelEditor]
    except Exception:
        return None
    for editor in editors:
        channel_list = getattr(editor, "channelList", None)
        if not callable(channel_list):
            continue
        try:
            selected = channel_list().selected()
        except Exception:
            continue
        for parm in selected:
            try:
                if parm.node().path() == node.path():
                    return parm
            except Exception:
                continue
    return None


def _present(card_id: str, request: dict) -> None:
    """Save this card. A cook error is included, and so is a normal node."""
    model = uses_workflow(request)
    if model:
        (_seen.get("origins") or {}).pop(card_id, None)
    else:
        _seen.setdefault("origins", {})[card_id] = _service(
            "local",
            "Quoted from the help installed with Houdini.",
        )
    stored = dict(request)
    remembered = recall(card_id) if model else ""
    if remembered:
        stored["known_heading"] = remembered
        stored["needs_model"] = False
    _keep_once(card_id, stored, model)


def _mark(card_id: str, service: dict) -> None:
    _seen.setdefault("cards", {})[card_id] = dict(service)
    _seen["service"] = dict(service)
    _seen["status_token"] = _seen.get("status_token", 0) + 1


def _keep_once(card_id: str, request: dict, model: bool) -> None:
    """Store this card. The same node and parameter reuse the saved run."""
    existing = (_seen.get("cards") or {}).get(card_id) or {}
    if existing.get("state") in {"online", "restored"}:
        return
    state = _seen.get("kept_state")
    if _seen.get("started_id") == card_id and state == "keeping":
        return
    _seen["started_id"] = card_id
    _seen["kept_id"] = card_id
    _seen["kept_state"] = "keeping"
    _seen["kept_card"] = None
    if model:
        detail = "Saving this heading. If the model times out, the same run tries again."
    else:
        detail = "Saving this card."
    saving = _service("working", detail)
    _mark(card_id, saving)
    _log(f"start {card_id}")
    _record(saving, request, model, _opening_usage(model, request))
    threading.Thread(
        target=_keep_worker,
        args=(card_id, request, model),
        name="houdini-wizard-temporal",
        daemon=True,
    ).start()


def _keep_worker(card_id: str, request: dict, model: bool) -> None:
    started = time.perf_counter()
    try:
        ensure_running()
        card = _ask_temporal(card_id, request)
    except Exception as exc:
        elapsed = _elapsed(started)
        _log(f"fail {card_id} {exc}")
        remembered = recall(card_id)
        if remembered:
            card = finish(request, remembered)
            service = _service("restored", _restored_detail(model))
            _publish(card_id, card, service["detail"], "reopened", service)
            _record(
                service,
                _with_heading(request, card),
                model,
                _settled_usage(request, model, card, elapsed, replayed=True),
            )
            return
        service = _failure_service(exc)
        note = service["detail"]
        usage = None
        if model:
            try:
                heading = pick_heading(request["headings"], request["error_text"])
                card = finish(request, heading)
                usage = last_usage() or skipped("pick a heading", "Gemma did not answer.")
            except Exception as model_exc:
                card = finish(request, "none")
                usage = last_usage() or skipped("pick a heading", "Gemma did not answer.")
                service = _service(
                    "error",
                    "This heading could not be saved, and it was not chosen. Open one from the file.",
                )
                note = service["detail"]
                _log(f"fail {card_id} model {model_exc}")
        else:
            card = finish(request)
        _publish(card_id, card, note, service["state"], service)
        _record(service, _with_heading(request, card), model, _settled_usage(request, model, card, elapsed, usage))
        return
    elapsed = _elapsed(started)
    kept_id = card.get("card_id") or card_id
    if card.get("kept") == "reopened":
        service = _service("restored", _restored_detail(model))
        state = "reopened"
    else:
        service = _service("online", _saved_detail(model))
        state = "stored"
    _log(f"{state} {kept_id}")
    _publish(card_id, card, service["detail"], state, service)
    _record(
        service,
        _with_heading(request, card),
        model,
        _settled_usage(request, model, card, elapsed, replayed=card.get("kept") == "reopened"),
    )


def _elapsed(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _opening_usage(model: bool, request: dict) -> dict:
    if model:
        usage = pending_pick(os.environ.get("HOUDINI_WIZARD_MODEL", DEFAULT_MODEL))
        usage["reason"] = plain_reason(request, asking=True)
        return usage
    return {}


def _settled_usage(
    request: dict,
    model: bool,
    card: dict,
    elapsed: int,
    fallback: dict | None = None,
    replayed: bool = False,
) -> dict:
    usage = dict(card.get("usage") or fallback or {})
    if not usage:
        logged = _log_card(request)
        if model or logged.get("needs_model"):
            usage = skipped("pick a heading", "Gemma did not answer.")
        elif request.get("matched") == "status":
            usage = skipped("quote the heading", plain_reason(request))
        elif logged.get("known_heading"):
            usage = skipped("quote the heading", plain_reason(request))
        else:
            usage = skipped("open the node", plain_reason(request))
    elif not usage.get("reason"):
        usage["reason"] = plain_reason(request)
    usage["save_ms"] = elapsed
    if replayed:
        usage["replayed"] = True
    return usage


def _record(service: dict, request: dict, model: bool, usage: dict | None = None) -> None:
    logged = _log_card(request)
    heading = logged["known_heading"]
    if heading == "none":
        heading = ""
    record(
        {
            "state": service.get("state"),
            "title": service.get("title"),
            "detail": service.get("detail"),
            "node": logged["node_path"],
            "node_label": logged["type_label"],
            "heading": heading,
            "parameter": logged["parm_label"],
            "situation": logged["situation"],
            "quote": logged["quote"],
            "error": logged["error_text"],
            "status_label": logged.get("status_label") or "",
            "headings": logged["headings"],
            "usage": usage or {},
            "source": "" if model else "From this install",
        }
    )


def _with_heading(request: dict, card: dict) -> dict:
    noted = dict(request)
    if card.get("kind") == "quote" and card.get("title"):
        noted["known_heading"] = card["title"]
    return noted


def _saved_detail(model: bool) -> str:
    if model:
        return (
            "This heading is saved. If the model times out, the same run tries again. "
            "Closing Houdini stops the service."
        )
    return "This card is saved. Open the tool on this node again and it comes back."


def _restored_detail(model: bool) -> str:
    if model:
        return "Brought this heading back. The model was not asked again."
    return "Brought this card back."


def _ask_temporal(card_id: str, request: dict) -> dict:
    """Ask the system Python to store the card. Houdini's loop cannot."""
    completed = subprocess.run(
        [worker_python(), "-m", "houdini_wizard.bridge", card_id],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(detail or f"the card process exited {completed.returncode}")
    return json.loads(completed.stdout)


def _publish(card_id: str, card: dict, note: str, state: str, service: dict | None = None) -> None:
    if service is not None:
        _seen.setdefault("cards", {})[card_id] = dict(service)
        _seen["status_token"] = _seen.get("status_token", 0) + 1
    if _seen.get("started_id") != card_id:
        return
    _seen["kept_id"] = card_id
    _seen["kept_card"] = card
    _seen["kept_note"] = note
    _seen["kept_state"] = state
    if service is not None:
        _seen["service"] = service


def _service(state: str, detail: str) -> dict:
    titles = {
        "working": "Saving",
        "online": "Saved",
        "restored": "Restored",
        "local": "From this install",
        "offline": "Not saved",
        "error": "Not saved",
    }
    return {"state": state, "title": titles.get(state, "Saving"), "detail": detail}


def _failure_service(exc: Exception) -> dict:
    text = str(exc).lower()
    offline = any(
        piece in text
        for piece in ("connection refused", "10061", "timed out", "failed to connect", "unavailable", "7233")
    )
    if offline:
        return _service(
            "offline",
            "The recovery service is not running. This card stays on screen only, and it will not come back if Houdini closes.",
        )
    return _service(
        "error",
        "This card could not be saved. It stays on screen only, and it will not come back if Houdini closes.",
    )


def _attach_service(scene: dict, card_id: str) -> None:
    card = (_seen.get("cards") or {}).get(card_id)
    if isinstance(card, dict) and card.get("state") != "local":
        scene["service"] = dict(card)
    else:
        scene["service"] = dict(
            _seen.get("session")
            or _service("working", "Starting the recovery service for this session.")
        )
    origin = (_seen.get("origins") or {}).get(card_id)
    if isinstance(origin, dict):
        scene["origin"] = dict(origin)


def _focus_for(card_id: str, request: dict, parm_label: str) -> str:
    card = _seen.get("kept_card") if _seen.get("kept_id") == card_id else None
    if isinstance(card, dict) and card.get("title"):
        return card["title"]
    if request.get("known_heading"):
        return request["known_heading"]
    return parm_label or ""


def _log(line: str) -> None:
    try:
        _LOG.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        with _LOG.open("a", encoding="utf-8") as handle:
            handle.write(f"{stamp} {line}\n")
    except Exception:
        return


async def _open(card_id: str, request: dict) -> dict:
    client = await connect()
    return await open_card(client, card_id, request)


def _run_async(coro):
    """Run one coroutine from the Houdini UI thread.

    Houdini already has an event loop. asyncio.run refuses that loop and
    throws the coroutine away, which is the console warning.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    box: dict = {}

    def _worker() -> None:
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as exc:
            box["error"] = exc
        finally:
            if inspect.getcoroutinestate(coro) in {inspect.CORO_CREATED, inspect.CORO_SUSPENDED}:
                coro.close()

    thread = threading.Thread(target=_worker, name="houdini-wizard-temporal", daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["value"]
