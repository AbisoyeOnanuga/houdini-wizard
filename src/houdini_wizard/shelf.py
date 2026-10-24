"""hython shelf. Reads the selection, stores the card, opens the dialog."""

from __future__ import annotations

import asyncio
import os

from houdini_wizard.help_file import installed_help
from houdini_wizard.pick import decide, finish, pick_heading
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
    _present(hou, card, note, help_file.sections)


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
        card = asyncio.run(_open(card_id, request))
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


def _present(hou, card: dict, note: str, sections) -> None:
    if card["kind"] == "list":
        labels = [section.heading for section in sections]
        if not labels:
            hou.ui.displayMessage("This help file has no headings.", title="Houdini wizard")
            return
        message = "No heading matched. Open one from this file."
        if note:
            message = f"{message}\n\n{note}"
        picks = hou.ui.selectFromList(labels, exclusive=True, title="Houdini wizard", message=message)
        if not picks:
            return
        section = sections[picks[0]]
        _show_quote(hou, section.heading, section.body, "")
        return
    _show_quote(hou, card["title"], card["body"], note)


def _show_quote(hou, title: str, body: str, note: str) -> None:
    text = body or "This heading has no text in the installed file."
    if note:
        text = f"{text}\n\n{note}"
    hou.ui.displayMessage(text, title=title, severity=hou.severityType.Message)
