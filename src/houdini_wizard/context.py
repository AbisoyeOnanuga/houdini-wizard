"""What this node is doing in the network the artist has open.

The words of each section still come from the installed help file. This module
only arranges them around the wires, the parameter tab, and the cook error.
"""

from __future__ import annotations

import re

from houdini_wizard.help_file import Section

_WHERE = {
    "Sop": "You are in a geometry network. This node changes the geometry passing through it.",
    "Dop": "You are in a dynamics network. This node is one step of a simulation, such as rigid bodies, cloth, or fluid.",
    "Lop": "You are in a Solaris stage. This node edits the scene a renderer will see.",
    "Copernicus": "You are in a Copernicus network. This node works on images or material layers.",
    "Cop": "You are in a compositing network.",
    "Cop2": "You are in a compositing network.",
    "Vop": "You are in a VOP network. This node is wired into a shader or a snippet.",
    "Driver": "You are on a render node. It starts a render from the scene you already built.",
    "Chop": "You are in a channel network. This node edits motion or channel data.",
    "Top": "You are in a task network. This node runs a job on the scene you already built.",
    "Object": "You are on an object. Geometry, cameras, and lights are placed as objects.",
    "Shop": "You are on a material. The parameters here are the look you still decide.",
    "Apex": "You are in an APEX network. This node is part of a rig you still pose.",
}


def build_study(sections: tuple[Section, ...] | list[Section], scene: dict, focus_heading: str) -> dict:
    focus = _find(sections, focus_heading) or _find_role(sections, "title")
    folders = [section.heading for section in sections if section.role == "folder"]
    wires_in = _wires(scene.get("inputs") or [], sections, "input")
    wires_out = _wires(scene.get("outputs") or [], sections, "output")
    heading = focus.heading if focus else ""
    folder = focus.folder if focus else ""
    return {
        "type_label": scene.get("type_label") or heading or "This node",
        "path": scene.get("path") or "",
        "where": _WHERE.get(scene.get("category") or "", "You are on the node you selected."),
        "error": (scene.get("error") or "").strip(),
        "focus_heading": heading,
        "focus_body": plain(focus.body) if focus else "",
        "focus_folder": folder,
        "folders": folders,
        "wires_in": wires_in,
        "wires_out": wires_out,
        "related": _related(sections),
        "headings": [section.heading for section in sections if section.heading],
        "note": _note(heading, folder, (scene.get("error") or "").strip(), wires_in),
    }


def plain(text: str) -> str:
    """Drop wiki markup so the panel reads as help, not as a source file."""
    cleaned = re.sub(r"\[([^\]|]+)\|[^\]]+\]", r"\1", text)
    cleaned = re.sub(r"\[/?Node:[^\]]+\]", "", cleaned)
    cleaned = cleaned.replace("__", "")
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _wires(live: list[dict], sections: list[Section] | tuple[Section, ...], role: str) -> list[str]:
    help_sections = [section for section in sections if section.role == role]
    lines: list[str] = []
    if live:
        for item in live:
            label = item.get("label") or "Input"
            wired = (item.get("wired") or "").strip()
            if wired:
                lines.append(f"{label}: wired from {wired}.")
            else:
                lines.append(f"{label}: nothing is wired here.")
            match = _find(help_sections, label)
            if match and match.body:
                lines.append(plain(match.body))
        return lines
    for section in help_sections:
        if section.heading.lower() in {"inputs", "outputs"}:
            if section.body:
                lines.append(plain(section.body))
            continue
        lines.append(f"{section.heading}: {plain(section.body)}".strip())
    return [line for line in lines if line]


def _related(sections: list[Section] | tuple[Section, ...]) -> list[str]:
    names: list[str] = []
    for section in sections:
        if section.role != "related" and "Node:" not in section.body:
            continue
        for match in re.findall(r"\[([^\]|]+)\|Node:[^\]]+\]", section.body):
            names.append(match.strip())
        for match in re.findall(r"\[Node:[a-z0-9_]+/([a-z0-9_]+)\]", section.body, re.I):
            names.append(match)
    seen: list[str] = []
    for name in names:
        if name and name not in seen:
            seen.append(name)
    return seen


def _note(heading: str, folder: str, error: str, wires_in: list[str]) -> str:
    lines: list[str] = []
    if error and heading:
        lines.append(
            f"This cook lines up with {heading}. Open that name in the parameter window and change it yourself."
        )
    elif heading and folder:
        lines.append(
            f"{heading} is under {folder} in the parameter window. The numbers and menu choices are still yours."
        )
    elif heading:
        lines.append(f"The section for what you selected is {heading}. You change that control. This card does not.")
    if any(line.endswith("nothing is wired here.") for line in wires_in):
        lines.append(
            "An input has no wire. The help says what that input accepts. What you connect is part of the setup you are building."
        )
    return "\n\n".join(lines)


def _find(sections, heading: str) -> Section | None:
    if not heading:
        return None
    for section in sections:
        if section.heading.lower() == heading.lower():
            return section
    return None


def _find_role(sections, role: str) -> Section | None:
    for section in sections:
        if section.role == role:
            return section
    return None
