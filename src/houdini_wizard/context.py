"""Arrange one node's installed help around the network the artist has open.

Menu choices, steps, and pictures come from the help files shipped with this
Houdini. Nothing in this module invents a parameter value.
"""

from __future__ import annotations

import os
import re
import zipfile

from houdini_wizard.help_file import Section, load_zip_member

_WHERE = {
    "Sop": "Geometry network. This node changes the geometry passing through it.",
    "Dop": "Dynamics network. This node is one step of a simulation.",
    "Lop": "Solaris stage. This node edits the scene a renderer will see.",
    "Copernicus": "Copernicus network. This node works on images or material layers.",
    "Cop": "Compositing network.",
    "Cop2": "Compositing network.",
    "Vop": "VOP network. This node is part of a shader or a snippet.",
    "Driver": "Render node. It starts a render from the scene you already built.",
    "Chop": "Channel network. This node edits motion or channel data.",
    "Top": "Task network. This node runs a job on the scene you already built.",
    "Object": "Object level. Geometry, cameras, and lights sit here.",
    "Shop": "Material. The parameters here are the look you still decide.",
    "Apex": "APEX network. This node is part of a rig you still pose.",
}

_IMAGE_ARCHIVES: dict[str, zipfile.ZipFile | None] = {}


def build_study(sections: tuple[Section, ...] | list[Section], scene: dict, focus_heading: str) -> dict:
    focus = _find(sections, focus_heading) or _find_role(sections, "title")
    title = _find_role(sections, "title")
    title_body = title.body if title else ""
    wires_in = _wires(scene.get("inputs") or [], sections, "input")
    wires_out = _wires(scene.get("outputs") or [], sections, "output")
    usage = usage_for(scene.get("hfs") or "", tuple(scene.get("includes") or ()))
    parameters = _parameters(
        sections,
        scene.get("values") or {},
        scene.get("parm_label") or focus_heading,
        scene.get("ranges") or {},
        scene.get("tooltips") or {},
        scene.get("guides") or {},
    )
    related_nodes = _related_nodes(sections, scene.get("hfs") or "")
    heading = focus.heading if focus else ""
    folder = focus.folder if focus else ""
    return {
        "type_label": scene.get("type_label") or heading or "This node",
        "path": scene.get("path") or "",
        "icon": scene.get("icon") or "",
        "hfs": scene.get("hfs") or "",
        "where": _WHERE.get(scene.get("category") or "", "The node you selected."),
        "summary": _summary(title_body),
        "callout": _callout(title_body),
        "error": (scene.get("error") or "").strip(),
        "focus_heading": heading,
        "focus_folder": folder,
        "parameters": parameters,
        "inputs": _ends(scene.get("inputs") or [], sections, "input"),
        "outputs": _ends(scene.get("outputs") or [], sections, "output"),
        "wires_in": wires_in,
        "wires_out": wires_out,
        "steps": usage["steps"],
        "figures": usage["figures"],
        "related_nodes": related_nodes,
        "related": [item["label"] for item in related_nodes],
        "headings": [item["name"] for item in parameters],
        "cache": _cache(sections, scene.get("type_label") or "", scene.get("category") or ""),
        "note": _note(
            heading if focus and focus.role == "parameter" else "",
            folder if focus and focus.role == "parameter" else "",
            (scene.get("error") or "").strip(),
            wires_in,
        ),
    }


def plain(text: str) -> str:
    """Drop wiki markup so the panel reads as help, not as a source file."""
    cleaned = re.sub(r"\[Icon:[^\]]+\]", "", text)
    cleaned = re.sub(r"\[([^\]|]+)\|[^\]]+\]", r"\1", cleaned)
    cleaned = re.sub(r"\[/?Node:[^\]]+\]", "", cleaned)
    cleaned = re.sub(r"\[Image:[^\]]+\]", "", cleaned)
    cleaned = cleaned.replace("((", "").replace("))", "")
    cleaned = cleaned.replace("__", "")
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def usage_for(hfs: str, includes: tuple[str, ...] | list[str]) -> dict:
    """Steps and pictures from a `:include` in the node file, usually the shelf page."""
    empty = {"steps": [], "figures": []}
    if not hfs:
        return empty
    shelf_path = os.path.join(hfs, "houdini", "help", "shelf.zip")
    if not os.path.isfile(shelf_path):
        return empty
    ordered = sorted(includes, key=lambda item: 0 if item.startswith("/shelf/") else 1)
    try:
        with zipfile.ZipFile(shelf_path) as archive:
            names = set(archive.namelist())
            for include in ordered:
                member = _shelf_member(include)
                if member not in names:
                    continue
                text = archive.read(member).decode("utf-8", errors="replace")
                usage = _usage(text)
                if usage["steps"] or usage["figures"]:
                    return usage
    except (OSError, zipfile.BadZipFile):
        return empty
    return empty


def image_bytes(hfs: str, wiki_path: str) -> bytes | None:
    member = wiki_path.replace("\\", "/")
    if "/images/" in member:
        member = member.split("/images/", 1)[1]
    member = member.lstrip("/")
    archive = _images(hfs)
    if archive is None or member not in archive.namelist():
        return None
    return archive.read(member)


def _images(hfs: str) -> zipfile.ZipFile | None:
    if hfs not in _IMAGE_ARCHIVES:
        path = os.path.join(hfs, "houdini", "help", "images.zip")
        try:
            _IMAGE_ARCHIVES[hfs] = zipfile.ZipFile(path) if os.path.isfile(path) else None
        except (OSError, zipfile.BadZipFile):
            _IMAGE_ARCHIVES[hfs] = None
    return _IMAGE_ARCHIVES[hfs]


def _shelf_member(include: str) -> str:
    path = include.split("#", 1)[0].strip("/")
    name = path.split("/")[-1]
    if not name.endswith(".txt"):
        name += ".txt"
    return name


def _usage(text: str) -> dict:
    lines = text.splitlines()
    start = 0
    for index, line in enumerate(lines):
        if "(includeme)" in line:
            start = index + 1
            break
    steps: list[str] = []
    figures: list[dict] = []
    label = ""
    images: list[str] = []

    def flush() -> None:
        nonlocal label, images
        if label or images:
            figures.append({"label": label, "images": list(images)})
        label = ""
        images = []

    for raw in lines[start:]:
        stripped = raw.strip()
        if stripped.startswith("== ") or stripped.startswith("@related"):
            break
        step = re.match(r"#\s+(\S.*)$", stripped)
        if step and not stripped.startswith("#icon") and not stripped.startswith("#tags"):
            steps.append(plain(step.group(1)))
            continue
        if "td>>" in raw:
            cell = raw.split("td>>", 1)[1].strip()
            found = re.findall(r"\[Image:([^\]]+)\]", cell)
            if found:
                images.extend(found)
                continue
            if cell and not cell.startswith("["):
                flush()
                label = plain(cell)
            continue
        found = re.findall(r"\[Image:([^\]]+)\]", stripped)
        if found and "td>>" not in raw:
            if not label:
                label = "Result"
            images.extend(found)
    flush()
    return {"steps": steps[:6], "figures": figures[:8]}


def _parameters(sections, values: dict, selected: str, ranges: dict, tooltips: dict, guides: dict) -> list[dict]:
    rows: list[dict] = []
    for section in sections:
        if section.role != "parameter":
            continue
        current = str(values.get(section.heading, "") or "")
        options = []
        for name, body in section.options:
            options.append(
                {
                    "name": name,
                    "meaning": plain(body),
                    "current": bool(current) and current.lower() == name.lower(),
                }
            )
        tooltip = plain(str(tooltips.get(section.heading, "") or ""))
        meaning = plain(section.body)
        if len(tooltip) > len(meaning):
            meaning = tooltip
        span = None if options else ranges.get(section.heading)
        written = str(guides.get(section.heading, "") or "")
        rows.append(
            {
                "name": section.heading,
                "folder": section.folder,
                "groups": list(section.groups),
                "meaning": meaning,
                "current": current,
                "selected": bool(selected) and selected.lower() == section.heading.lower(),
                "options": options,
                "range": written or _value_guide(section.heading, meaning, span),
            }
        )
    return rows


def _value_guide(name: str, meaning: str, span: dict | None) -> str:
    """Say what the ends of a number parameter do, using the help's own words."""
    if not span:
        return ""
    low = _fmt(span.get("low"))
    high = _fmt(span.get("high"))
    if low == high:
        return ""
    reach = _reach(low, high, bool(span.get("low_strict")), bool(span.get("high_strict")))
    effect = _effect_clause(meaning)
    if effect:
        return f"{name} {reach}. {effect}"
    lead = meaning.rstrip(".") if meaning else name
    sentence = f"{lead} {reach}."
    if _is_angle(name, meaning):
        sentence += " 0 means no rotation. Positive values turn one way and negative values turn the opposite way."
    elif low == "0":
        sentence += f" 0 means none of this. {high} is the high end of the slider."
    return sentence


def _reach(low: str, high: str, low_strict: bool, high_strict: bool) -> str:
    extra = []
    if not high_strict:
        extra.append(f"greater than {high}")
    if not low_strict and low != "0":
        extra.append(f"below {low}")
    elif not low_strict and low == "0":
        extra.append(f"below {low}")
    if extra:
        return f"from {low} to {high}, or {' or '.join(extra)}"
    return f"from {low} to {high}"


def _effect_clause(meaning: str) -> str:
    if not meaning:
        return ""
    for sentence in re.split(r"(?<=[.!?])\s+", meaning.strip()):
        if re.search(r"\b(increasing|decreasing|higher|lower|stronger|weaker|faster|slower)\b", sentence, re.I):
            return sentence.strip()
    return ""


def _is_angle(name: str, meaning: str) -> bool:
    text = f"{name} {meaning}".lower()
    return any(word in text for word in ("rotate", "rotation", "angle", "degrees"))


def _fmt(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _ends(live: list[dict], sections, role: str) -> list[dict]:
    help_sections = [section for section in sections if section.role == role]
    rows: list[dict] = []
    if live:
        for item in live:
            label = item.get("label") or ("Input" if role == "input" else "Output")
            wired = (item.get("wired") or "").strip()
            match = _find(help_sections, label)
            rows.append(
                {
                    "label": label,
                    "state": f"from {wired}" if wired else "no node connected",
                    "meaning": plain(match.body) if match and match.body else "",
                }
            )
        return rows
    for section in help_sections:
        if section.heading.lower() in {"inputs", "outputs"}:
            continue
        rows.append({"label": section.heading, "state": "", "meaning": plain(section.body)})
    return rows


def _wires(live: list[dict], sections, role: str) -> list[str]:
    rows = _ends(live, sections, role)
    lines = []
    for row in rows:
        text = f"{row['label']}: {row['state']}".strip(": ")
        if row["meaning"]:
            text = f"{text}. {row['meaning']}"
        lines.append(text)
    return lines


_NODE_LINK = re.compile(
    r"\[(?:([^\]|]+)\|)?Node:([A-Za-z0-9_]+)/([A-Za-z0-9_]+)\]",
    re.I,
)
_HEAVY = re.compile(
    r"\b(simulat\w*|solvers?|volumes?|pyro|flip|oceans?|vellum|cloth|muscles?|crowds?|vdbs?|heightfields?|renders?|fem|grains?)\b",
    re.I,
)


def _related_nodes(sections, hfs: str) -> list[dict]:
    """Nodes the help browser lists next, each with that node's own one-line summary."""
    found: list[dict] = []
    seen: set[str] = set()
    for section in sections:
        if section.role != "related":
            continue
        for match in _NODE_LINK.finditer(section.body):
            label, folder, internal = match.group(1), match.group(2).lower(), match.group(3).lower()
            help_path = f"/nodes/{folder}/{internal}"
            if help_path in seen:
                continue
            seen.add(help_path)
            title, note = _node_blurb(hfs, folder, internal)
            found.append(
                {
                    "label": (label or title or internal).strip(),
                    "help": help_path,
                    "note": note,
                }
            )
    return found


def _node_blurb(hfs: str, folder: str, internal: str) -> tuple[str, str]:
    if not hfs:
        return "", ""
    zip_path = os.path.join(hfs, "houdini", "help", "nodes.zip")
    try:
        loaded = load_zip_member(zip_path, f"{folder}/{internal}.txt")
    except (OSError, FileNotFoundError, zipfile.BadZipFile, KeyError):
        return "", ""
    title = _find_role(loaded.sections, "title")
    if title is None:
        return "", ""
    return title.heading, _lead(title.body)


def _cache(sections, type_label: str, category: str = "") -> str:
    own = [section.heading for section in sections if section.role == "parameter" and re.search(r"cache|freeze", section.heading, re.I)]
    if own:
        return (
            f"{own[0]} is on this node. Use it when you want to hold the cooked result and keep working. "
            "You still choose when it should recook."
        )
    if "cache" in type_label.lower():
        return (
            "This node holds a cooked result. Write it when the upstream nodes look right. "
            "Nodes after it can read the cache instead of cooking the whole chain again."
        )
    title = _find_role(sections, "title")
    described = plain(" ".join([type_label, title.body if title else ""]))
    if category != "Dop" and not _HEAVY.search(described):
        return ""
    if category == "Dop":
        return (
            "This is a simulation step, so it is often the slow part of the network. "
            "When the setup looks right, cache the result and work downstream from that cache. "
            "You still set the parameters here. When you change them, write the cache again."
        )
    return (
        "This cook is the kind that holds up a network. Add a File Cache after it and write the result. "
        "Nodes downstream read that file, so this node does not have to cook on every change. "
        "You still set the parameters here. When you change them, write the cache again."
    )


def _lead(body: str) -> str:
    quoted = _summary(body)
    if quoted:
        return quoted
    lines: list[str] = []
    for raw in body.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(":"):
            if lines:
                break
            continue
        lines.append(stripped)
        if stripped.endswith((".", "!", "?")):
            break
    return plain(" ".join(lines))


def _summary(body: str) -> str:
    match = re.search(r'"""(.+?)"""', body, re.S)
    if not match:
        return ""
    return plain(re.sub(r"\s+", " ", match.group(1)))


def _callout(body: str) -> str:
    match = re.search(r"^NOTE:\s*(.+?)(?:\n\s*\n|\Z)", body, re.S | re.M)
    if not match:
        return ""
    return plain(match.group(1))


def _note(heading: str, folder: str, error: str, wires_in: list[str]) -> str:
    lines: list[str] = []
    if error and heading:
        lines.append(f"This cook lines up with {heading}. That parameter is marked below. You change it.")
    elif heading and folder:
        lines.append(f"{heading} is under {folder}. The menu choices next to it are from the help file. You still set the value.")
    elif heading:
        lines.append(f"{heading} is on this node. The sentence and the choices next to it are from the help file. You still set the value.")
    if any("no node connected" in line for line in wires_in):
        lines.append("An input has no node connected. The line under it says what that input accepts.")
    return " ".join(lines)


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
