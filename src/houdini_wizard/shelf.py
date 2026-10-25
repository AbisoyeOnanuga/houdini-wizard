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


def show_card() -> None:
    import hou

    selected = _selection(hou)
    if selected is None:
        return
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
    scene = _scene(node, error_text)
    extra = ""
    if request.get("needs_model") and card.get("kind") == "quote":
        try:
            from houdini_wizard.context import build_study

            study = build_study(help_file.sections, scene, card.get("title") or "")
            extra = explain_context(error_text, study["focus_heading"], study["wires_in"])
        except Exception:
            extra = note
    show_panel(help_file.sections, scene, card.get("title") or "", extra)


def _selection(hou):
    nodes = list(hou.selectedNodes())
    parm = _selected_parm(hou, nodes[0] if nodes else None)
    node = parm.node() if parm is not None else (nodes[0] if nodes else None)
    if node is None:
        if hasattr(hou, "ui"):
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


def _scene(node, error_text: str) -> dict:
    return {
        "type_label": _type_label(node),
        "category": node.type().category().name(),
        "path": node.path(),
        "error": error_text,
        "inputs": _ends(node, incoming=True),
        "outputs": _ends(node, incoming=False),
    }


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
        return card, ""
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
