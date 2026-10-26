"""hython shelf. Reads the selection, stores the card, opens the dialog."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from houdini_wizard.help_file import installed_help
from houdini_wizard.panel import show_panel
from houdini_wizard.memory import recall, uses_workflow
from houdini_wizard.pick import decide, finish, pick_heading
from houdini_wizard.service import ensure_running, worker_python
from houdini_wizard.workflow import connect, open_card, workflow_id

_seen = {"signature": None, "guide_token": 0, "status_token": 0, "shown_status": 0}
_LOG = Path(__file__).resolve().parents[2] / ".temporal" / "shelf.log"


def show_card() -> None:
    import hou

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
    node, parm_name, parm_label, error_text = selected
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
    request = decide(help_file.sections, parm_name, parm_label, error_text)
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
    try:
        ensure_running()
        _log("service ready")
    except Exception as exc:
        _log(f"service {exc}")


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
    errors = node.errors()
    if isinstance(errors, (list, tuple)):
        error_text = "\n".join(str(item) for item in errors if item)
    else:
        error_text = errors or ""
    return node, parm_name, parm_label, error_text


def hold_for_browse(hou) -> None:
    """Keep the library on screen until the network selection changes."""
    selected = _selection(hou, announce=False)
    if selected is None:
        _seen["browse_hold"] = None
    else:
        node, parm_name, parm_label, error_text = selected
        _seen["browse_hold"] = _signature(node, parm_name, parm_label, error_text)
    _seen["browsing"] = True
    _seen["signature"] = ("library",)


def _poll(hou):
    selected = _selection(hou, announce=False)
    if selected is None:
        return None
    node, parm_name, parm_label, error_text = selected
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
    request = decide(help_file.sections, parm_name, parm_label, error_text)
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
    """Show where this card lives. A workflow starts only for a model pick."""
    if not uses_workflow(request):
        _mark(
            card_id,
            _service(
                "local",
                "Quoted from the help installed with Houdini. Looking at a node does not save a workflow.",
            ),
        )
        return
    remembered = recall(card_id)
    if remembered:
        _seen["kept_id"] = card_id
        _seen["kept_card"] = finish(request, remembered)
        _seen["kept_state"] = "reopened"
        _mark(
            card_id,
            _service(
                "restored",
                "Brought this heading back from this computer. The model was not asked again.",
            ),
        )
        if card_id not in _seen.setdefault("released", set()):
            _seen["released"].add(card_id)
            threading.Thread(
                target=_release_quiet,
                args=(card_id,),
                name="houdini-wizard-release",
                daemon=True,
            ).start()
        return
    _keep_once(card_id, request)


def _mark(card_id: str, service: dict) -> None:
    _seen.setdefault("cards", {})[card_id] = dict(service)
    _seen["service"] = dict(service)
    _seen["status_token"] = _seen.get("status_token", 0) + 1


def _keep_once(card_id: str, request: dict) -> None:
    """Store one heading pick. The same cook error reuses that run.

    Browsing nodes does not call this. A named heading is quoted locally.
    """
    state = _seen.get("kept_state")
    if _seen.get("started_id") == card_id and state in {"keeping", "stored", "reopened"}:
        return
    _seen["started_id"] = card_id
    _seen["kept_id"] = card_id
    _seen["kept_state"] = "keeping"
    _seen["kept_card"] = None
    _mark(
        card_id,
        _service(
            "working",
            "Saving this heading. If the model times out, the same run tries again.",
        ),
    )
    _log(f"start {card_id}")
    threading.Thread(
        target=_keep_worker,
        args=(card_id, request),
        name="houdini-wizard-temporal",
        daemon=True,
    ).start()


def _keep_worker(card_id: str, request: dict) -> None:
    try:
        ensure_running()
        card = _ask_temporal(card_id, request)
    except Exception as exc:
        _log(f"fail {card_id} {exc}")
        remembered = recall(card_id)
        if remembered:
            card = finish(request, remembered)
            service = _service(
                "restored",
                "Brought this heading back from this computer. The model was not asked again.",
            )
            _publish(card_id, card, service["detail"], "reopened", service)
            return
        service = _failure_service(exc)
        note = service["detail"]
        if request.get("needs_model"):
            try:
                heading = pick_heading(request["headings"], request["error_text"])
                card = finish(request, heading)
            except Exception as model_exc:
                card = finish(request, "none")
                service = _service(
                    "error",
                    "This heading could not be saved, and it was not chosen. Open one from the file.",
                )
                note = service["detail"]
                _log(f"fail {card_id} model {model_exc}")
        else:
            card = finish(request)
        _publish(card_id, card, note, service["state"], service)
        return
    if card.get("released") is False:
        _log(f"release {card_id} kept the finished run")
    kept_id = card.get("card_id") or card_id
    if card.get("kept") == "reopened":
        service = _service(
            "restored",
            "Brought this heading back from this computer. The model was not asked again.",
        )
        state = "reopened"
    else:
        service = _service(
            "online",
            "This heading is saved on this computer. If the model times out, the same run tries again. Closing Houdini stops the service.",
        )
        state = "stored"
    _log(f"{state} {kept_id}")
    _publish(card_id, card, service["detail"], state, service)


def _release_quiet(card_id: str) -> None:
    """Drop a finished run once the heading is already on disk."""
    try:
        subprocess.run(
            [worker_python(), "-m", "houdini_wizard.bridge", card_id, "--release"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:
        _log(f"release {card_id} {exc}")


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
    service = (_seen.get("cards") or {}).get(card_id)
    if isinstance(service, dict):
        scene["service"] = dict(service)


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
