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

_HEADING = re.compile(r"^(=+)\s*(.+?)\s*\1\s*$")
_LABEL = re.compile(r"^(\s*)(\S.*):\s*$")
_CHANNELS = re.compile(r"^\s*#channels:\s*(.+)$")
_DIRECTIVE = re.compile(r"^\s*:")
_META = re.compile(r"^\s*#\w+:")

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

    def as_dict(self) -> dict:
        return {
            "heading": self.heading,
            "channels": list(self.channels),
            "body": self.body,
        }


@dataclass(frozen=True)
class HelpFile:
    source: str
    sections: tuple[Section, ...]


def parse_wiki(text: str) -> tuple[Section, ...]:
    """Split one wiki file.

    `= Title =` and `== Folder ==` are headings. After `@parameters`,
    `@inputs`, or `@outputs`, a `Label:` line at the parameter indent is a
    heading too. A more-indented `Label:` is a menu choice and stays in the
    parent section. `#channels:` holds the parameter's real names (`/sizex`).
    """
    sections: list[_Draft] = []
    current: _Draft | None = None
    param_indent: int | None = None
    in_parms = False

    def start(heading: str) -> _Draft:
        nonlocal current
        current = _Draft(heading)
        sections.append(current)
        return current

    for raw in text.splitlines():
        line = raw.replace("\t", "    ")
        stripped = line.strip()
        if not stripped:
            if current is not None:
                current.lines.append("")
            continue
        if stripped in {"@parameters", "@inputs", "@outputs"}:
            in_parms = True
            param_indent = None
            if stripped != "@parameters":
                start(stripped[1:].capitalize())
            continue
        if stripped.startswith("@related"):
            in_parms = False
            param_indent = None
            start("Related")
            continue
        heading = _HEADING.match(stripped)
        if heading and line.lstrip() == stripped:
            # A folder such as `== Code ==` stays inside @parameters.
            # The next Label: at the left edge is still a parameter.
            param_indent = None
            start(heading.group(2).strip())
            continue
        label = _LABEL.match(line)
        if in_parms and label and not stripped.startswith("#") and not stripped.startswith(":"):
            indent = len(label.group(1))
            if param_indent is None or indent <= param_indent:
                param_indent = indent if param_indent is None else param_indent
                start(label.group(2).strip())
                continue
        if current is None:
            continue
        channels = _CHANNELS.match(line)
        if channels and not current.lines:
            names = tuple(part.strip() for part in channels.group(1).split() if part.strip())
            current.channels.extend(names)
            continue
        if _DIRECTIVE.match(line) or (_META.match(line) and not current.lines):
            continue
        current.lines.append(raw.rstrip())

    return tuple(_finish(item) for item in sections if item.heading)


def load_text(text: str, source: str) -> HelpFile:
    return HelpFile(source=source, sections=parse_wiki(text))


def load_path(path: str) -> HelpFile:
    key = (path, "", _mtime(path))
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    with open(path, encoding="utf-8", errors="replace") as handle:
        loaded = load_text(handle.read(), path)
    _CACHE[key] = loaded
    return loaded


def load_zip_member(zip_path: str, member: str) -> HelpFile:
    key = (zip_path, member, _mtime(zip_path))
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
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
            return load_zip_member(zip_path, member)
        except FileNotFoundError:
            pass
    loose = os.path.join(help_root, "nodes", member.replace("/", os.sep))
    if os.path.isfile(loose):
        return load_path(loose)
    raise FileNotFoundError(member)


class _Draft:
    def __init__(self, heading: str) -> None:
        self.heading = heading
        self.channels: list[str] = []
        self.lines: list[str] = []


def _finish(draft: _Draft) -> Section:
    while draft.lines and draft.lines[-1] == "":
        draft.lines.pop()
    body = textwrap.dedent("\n".join(draft.lines)).strip()
    return Section(draft.heading, tuple(draft.channels), body)


def _mtime(path: str) -> int:
    try:
        return int(os.path.getmtime(path))
    except OSError:
        return 0
