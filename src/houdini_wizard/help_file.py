"""Read one Houdini node help file and split it on headings.

The install keeps node help as wiki text in `$HFS/houdini/help/nodes.zip`.
One member is one node, for example `sop/box.txt`. This module opens that
member. It does not extract the archive and it does not start the help server.
"""

from __future__ import annotations

import os
import re
import textwrap
import zipfile
from dataclasses import dataclass

_HEADING = re.compile(r"^(=+)\s*(.+?)\s*\1(?:\s*\(([^)]*)\))?\s*$")
_LABEL = re.compile(r"^(\s*)(\S.*):\s*$")
_CHANNELS = re.compile(r"^\s*#channels:\s*(.+)$")
_DIRECTIVE = re.compile(r"^\s*:")
_META = re.compile(r"^\s*#\w+:")
_INCLUDE = re.compile(r":include\s+(\S+):")
_ID = re.compile(r"^\s*#id:\s*(\S*)")
_CONTENTFROM = re.compile(r"^\s*#contentfrom:\s*(\S+)")

# Hou category name -> folder inside nodes.zip.
_FOLDERS = {
    "Sop": "sop",
    "Object": "obj",
    "Dop": "dop",
    "Vop": "vop",
    "Driver": "out",
    "Chop": "chop",
    "Shop": "shop",
    "Cop": "cop",
    "Cop2": "cop",
    "Copernicus": "cop",
    "Lop": "lop",
    "Top": "top",
    "Apex": "apex",
}

_CACHE: dict[tuple[str, str, int], "HelpFile"] = {}


@dataclass(frozen=True)
class Section:
    heading: str
    channels: tuple[str, ...]
    body: str
    role: str = "section"
    folder: str = ""
    options: tuple[tuple[str, str], ...] = ()
    anchor: str = ""
    contentfrom: str = ""
    groups: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "heading": self.heading,
            "channels": list(self.channels),
            "body": self.body,
            "role": self.role,
            "folder": self.folder,
            "options": [{"name": name, "body": body} for name, body in self.options],
            "anchor": self.anchor,
            "contentfrom": self.contentfrom,
            "groups": list(self.groups),
        }


@dataclass(frozen=True)
class HelpFile:
    source: str
    sections: tuple[Section, ...]
    includes: tuple[str, ...] = ()


def parse_wiki(text: str) -> tuple[Section, ...]:
    """Split one wiki file.

    `= Title =` and `== Folder ==` are headings. Deeper headings, `===` and
    `====`, nest inside the folder above them. That depth comes from the file
    being read, so each node keeps its own parameter-pane folders. After
    `@parameters`, `@inputs`, or `@outputs`, a `Label:` line at the parameter
    indent is a heading too. A more-indented `Label:` is a menu choice on that
    parameter.
    `#channels:` holds the parameter's real names (`/sizex`).
    """
    sections: list[_Draft] = []
    current: _Draft | None = None
    param_indent: int | None = None
    block = "title"
    folder_stack: list[dict] = []

    def start(heading: str, role: str, groups: tuple[str, ...] = ()) -> _Draft:
        nonlocal current
        folder = groups[0] if role == "parameter" and groups else ""
        if current is not None:
            current.option = None
        current = _Draft(heading, role, folder, groups if role == "parameter" else ())
        sections.append(current)
        return current

    def place_parameter(indent: int) -> None:
        """Pop nested folders when a parameter returns to an outer indent."""
        while folder_stack:
            top = folder_stack[-1]
            if top["content_indent"] is not None and indent < top["content_indent"]:
                folder_stack.pop()
                continue
            if top["content_indent"] is None and top["child_indent"] is not None and indent < top["child_indent"]:
                folder_stack.pop()
                continue
            if top["content_indent"] is None:
                top["content_indent"] = indent
                if len(folder_stack) >= 2 and folder_stack[-2]["child_indent"] is None:
                    folder_stack[-2]["child_indent"] = indent
            break

    for raw in text.splitlines():
        line = raw.replace("\t", "    ")
        stripped = line.strip()
        if not stripped:
            if current is not None:
                target = current.option if current.option is not None else current
                target.lines.append("")
            continue
        if stripped == "@parameters":
            block = "parameters"
            param_indent = None
            folder_stack.clear()
            continue
        if stripped in {"@inputs", "@outputs"}:
            block = stripped[1:]
            param_indent = None
            folder_stack.clear()
            start(stripped[1:].capitalize(), block)
            continue
        if stripped.startswith("@related"):
            block = "related"
            param_indent = None
            folder_stack.clear()
            start("Related", "related")
            continue
        heading = _HEADING.match(stripped)
        if heading and line.lstrip() == stripped:
            # A folder such as `== Code ==` stays inside @parameters.
            # More equals signs nest inside the folder above, matching the parameter pane.
            param_indent = None
            title = heading.group(2).strip()
            anchor = (heading.group(3) or "").strip()
            if block == "parameters":
                depth = len(heading.group(1))
                while folder_stack and folder_stack[-1]["depth"] >= depth:
                    folder_stack.pop()
                folder_stack.append({"depth": depth, "name": title, "content_indent": None, "child_indent": None})
                started = start(title, "folder")
            else:
                started = start(title, "title" if block == "title" else block)
            if anchor:
                started.anchor = anchor
            continue
        label = _LABEL.match(line)
        if block in {"parameters", "inputs", "outputs"} and label and not stripped.startswith("#") and not stripped.startswith(":"):
            indent = len(label.group(1))
            if param_indent is None or indent <= param_indent:
                if param_indent is None or indent < param_indent:
                    param_indent = indent
                if block == "parameters":
                    place_parameter(indent)
                role = "parameter" if block == "parameters" else block[:-1]
                groups = tuple(item["name"] for item in folder_stack) if block == "parameters" else ()
                start(label.group(2).strip(), role, groups)
                continue
            if current is not None and current.role == "parameter":
                choice = _Draft(label.group(2).strip(), "option", "")
                current.options.append(choice)
                current.option = choice
                continue
        if current is None:
            continue
        found_id = _ID.match(line)
        if found_id and current.option is None:
            current.anchor = found_id.group(1).strip()
            continue
        found_from = _CONTENTFROM.match(line)
        if found_from and current.option is None:
            current.contentfrom = found_from.group(1).strip()
            continue
        channels = _CHANNELS.match(line)
        if channels and current.option is None and not current.lines:
            names = tuple(part.strip() for part in channels.group(1).split() if part.strip())
            current.channels.extend(names)
            continue
        if _DIRECTIVE.match(line) or (_META.match(line) and not current.lines and current.option is None):
            continue
        target = current.option if current.option is not None else current
        target.lines.append(raw.rstrip())

    return tuple(_finish(item) for item in sections if item.heading)


def load_text(text: str, source: str) -> HelpFile:
    includes = tuple(dict.fromkeys(_INCLUDE.findall(text)))
    return HelpFile(source=source, sections=parse_wiki(text), includes=includes)


def load_path(path: str) -> HelpFile:
    key = (path, "", _mtime(path))
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    with open(path, encoding="utf-8", errors="replace") as handle:
        loaded = load_text(handle.read(), path)
    _CACHE[key] = loaded
    return loaded


_OPEN_ZIPS: dict[str, tuple[int, zipfile.ZipFile, set[str]]] = {}


def _zip(zip_path: str) -> tuple[zipfile.ZipFile, set[str]]:
    """Keep one archive open so a node and its related pages share the read."""
    mtime = _mtime(zip_path)
    cached = _OPEN_ZIPS.get(zip_path)
    if cached is not None and cached[0] == mtime:
        return cached[1], cached[2]
    if cached is not None:
        cached[1].close()
    archive = zipfile.ZipFile(zip_path)
    names = set(archive.namelist())
    _OPEN_ZIPS[zip_path] = (mtime, archive, names)
    return archive, names


def load_zip_member(zip_path: str, member: str) -> HelpFile:
    key = (zip_path, member, _mtime(zip_path))
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    archive, names = _zip(zip_path)
    chosen = member
    if chosen not in names:
        lowered = {name.lower(): name for name in names}
        chosen = lowered.get(member.lower().replace("\\", "/"), "")
    if not chosen:
        raise FileNotFoundError(member)
    text = archive.read(chosen).decode("utf-8", errors="replace")
    loaded = load_text(text, f"{zip_path}:{chosen}")
    _CACHE[key] = loaded
    return loaded


def member_for(category: str, internal: str) -> str:
    folder = _FOLDERS.get(category, category.lower())
    return f"{folder}/{internal}.txt"


def installed_help(category: str, internal: str, hfs: str | None = None) -> HelpFile:
    root = hfs or os.environ.get("HFS", "")
    if not root:
        raise FileNotFoundError("HFS is not set")
    help_root = os.path.join(root, "houdini", "help")
    member = member_for(category, internal)
    zip_path = os.path.join(help_root, "nodes.zip")
    if os.path.isfile(zip_path):
        try:
            return resolve_contentfrom(load_zip_member(zip_path, member), help_root)
        except FileNotFoundError:
            pass
    loose = os.path.join(help_root, "nodes", member.replace("/", os.sep))
    if os.path.isfile(loose):
        return resolve_contentfrom(load_path(loose), help_root)
    raise FileNotFoundError(member)


def resolve_contentfrom(loaded: HelpFile, help_root: str) -> HelpFile:
    """Copy a parameter's text from the help file a `#contentfrom` line names.

    Copernicus nodes often point at the SOP page for the same control. That
    page is the tooltip the parameter window shows.
    """
    if not any(section.contentfrom for section in loaded.sections):
        return loaded
    zip_path = os.path.join(help_root, "nodes.zip")
    donors: dict[str, HelpFile] = {}
    resolved: list[Section] = []
    for section in loaded.sections:
        if not section.contentfrom:
            resolved.append(section)
            continue
        donor = _donor_section(donors, zip_path, section.contentfrom)
        if donor is None:
            resolved.append(section)
            continue
        body = donor.body if len(donor.body) > len(section.body) else section.body
        options = donor.options or section.options
        resolved.append(
            Section(
                section.heading,
                section.channels or donor.channels,
                body,
                section.role,
                section.folder,
                options,
                section.anchor,
                "",
                section.groups,
            )
        )
    return HelpFile(loaded.source, tuple(resolved), loaded.includes)


def _donor_section(donors: dict[str, HelpFile], zip_path: str, contentfrom: str) -> Section | None:
    path, _, anchor = contentfrom.partition("#")
    member = path.strip("/").split("nodes/", 1)[-1]
    if not member.endswith(".txt"):
        member += ".txt"
    if not os.path.isfile(zip_path):
        return None
    if member not in donors:
        try:
            donors[member] = load_zip_member(zip_path, member)
        except (OSError, FileNotFoundError):
            return None
    wanted = anchor.strip().lower()
    for section in donors[member].sections:
        if section.anchor.lower() == wanted:
            return section
    compact = re.sub(r"[^a-z0-9]", "", wanted)
    for section in donors[member].sections:
        if re.sub(r"[^a-z0-9]", "", section.heading.lower()) == compact:
            return section
    return None


class _Draft:
    def __init__(self, heading: str, role: str, folder: str, groups: tuple[str, ...] = ()) -> None:
        self.heading = heading
        self.role = role
        self.folder = folder
        self.groups = tuple(groups)
        self.channels: list[str] = []
        self.lines: list[str] = []
        self.options: list[_Draft] = []
        self.option: _Draft | None = None
        self.anchor = ""
        self.contentfrom = ""


def _finish(draft: _Draft) -> Section:
    while draft.lines and draft.lines[-1] == "":
        draft.lines.pop()
    body = textwrap.dedent("\n".join(draft.lines)).strip()
    options = tuple((item.heading, _body(item)) for item in draft.options)
    return Section(
        draft.heading,
        tuple(draft.channels),
        body,
        draft.role,
        draft.folder,
        options,
        draft.anchor,
        draft.contentfrom,
        draft.groups,
    )


def _body(draft: _Draft) -> str:
    while draft.lines and draft.lines[-1] == "":
        draft.lines.pop()
    return textwrap.dedent("\n".join(draft.lines)).strip()


def _mtime(path: str) -> int:
    try:
        return int(os.path.getmtime(path))
    except OSError:
        return 0
