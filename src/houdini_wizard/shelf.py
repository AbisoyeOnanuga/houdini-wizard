"""hython shelf. Reads the selection, stores the card, opens the dialog."""

from __future__ import annotations

import asyncio
import inspect
import os
import threading

from houdini_wizard.help_file import installed_help
from houdini_wizard.panel import show_panel
from houdini_wizard.pick import decide, explain_context, finish, pick_heading
from houdini_wizard.workflow import connect, open_card, workflow_id

_seen = {"signature": None, "guide_token": 0}


def show_card() -> None:
    import hou

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
    card, note = _store(card_id, request)
    scene = _scene(node, error_text, hfs, help_file.includes, parm_label)
    from houdini_wizard.values import attach_guides

    attach_guides(scene, help_file.sections, allow_model=True)
    extra = note
    if request.get("needs_model") and card.get("kind") == "quote":
        try:
            from houdini_wizard.context import build_study

            study = build_study(help_file.sections, scene, card.get("title") or "")
            extra = f"{explain_context(error_text, study['focus_heading'], study['wires_in'])} {note}".strip()
        except Exception:
            extra = note
    focus = card.get("title") or parm_label or ""
    _seen["signature"] = _signature(node, parm_name, parm_label, error_text)
    show_panel(help_file.sections, scene, focus, extra, refresh=lambda: _poll(hou))


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
    if signature == _seen["signature"]:
        return None
    try:
        category = node.type().category().name()
        internal = node.type().nameComponents()[2]
        hfs = hou.getenv("HFS") or os.environ.get("HFS", "")
        help_file = installed_help(category, internal, hfs)
    except Exception:
        return None
    _seen["signature"] = signature
    scene = _scene(node, error_text, hfs, help_file.includes, parm_label)
    from houdini_wizard.values import attach_guides

    attach_guides(scene, help_file.sections, allow_model=True)
    focus = parm_label or ""
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


def _store(card_id: str, request: dict) -> tuple[dict, str]:
    try:
        card = _run_async(_open(card_id, request))
    except Exception as exc:
        note = f"Temporal did not keep this card ({exc}). The quote is still from the help file."
        heading = request.get("known_heading") or ""
        if request.get("needs_model"):
            try:
                heading = pick_heading(request["headings"], request["error_text"])
                note = "Temporal did not keep this card. Gemma still chose the heading."
            except Exception as model_exc:
                heading = "none"
                note = f"Temporal and Gemma did not run ({model_exc}). Open a heading from the file."
        return finish(request, heading), note
    kept_id = card.get("card_id") or card_id
    if card.get("kept") == "reopened":
        note = (
            f"Reopened the stored card {kept_id}. The model was not asked again. "
            "The same history is at http://localhost:8233"
        )
    else:
        note = (
            f"Stored this card as {kept_id}. Quit Houdini, open it again, select this node, "
            "and click the shelf. History is at http://localhost:8233"
        )
    return card, note


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
