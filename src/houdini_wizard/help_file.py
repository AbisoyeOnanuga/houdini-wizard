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
_INCLUDE = re.compile(r":include\s+(\S+):")

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

    def as_dict(self) -> dict:
        return {
            "heading": self.heading,
            "channels": list(self.channels),
            "body": self.body,
            "role": self.role,
            "folder": self.folder,
            "options": [{"name": name, "body": body} for name, body in self.options],
        }


@dataclass(frozen=True)
class HelpFile:
    source: str
    sections: tuple[Section, ...]
    includes: tuple[str, ...] = ()


def parse_wiki(text: str) -> tuple[Section, ...]:
    """Split one wiki file.

    `= Title =` and `== Folder ==` are headings. After `@parameters`,
    `@inputs`, or `@outputs`, a `Label:` line at the parameter indent is a
    heading too. A more-indented `Label:` is a menu choice on that parameter.
    `#channels:` holds the parameter's real names (`/sizex`).
    """
    sections: list[_Draft] = []
    current: _Draft | None = None
    param_indent: int | None = None
    block = "title"
    folder_name = ""
    folder_content_indent: int | None = None

    def start(heading: str, role: str) -> _Draft:
        nonlocal current
        folder = folder_name if role == "parameter" else ""
        if current is not None:
            current.option = None
        current = _Draft(heading, role, folder)
        sections.append(current)
        return current

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
            folder_name = ""
            folder_content_indent = None
            continue
        if stripped in {"@inputs", "@outputs"}:
            block = stripped[1:]
            param_indent = None
            start(stripped[1:].capitalize(), block)
            continue
        if stripped.startswith("@related"):
            block = "related"
            param_indent = None
            start("Related", "related")
            continue
        heading = _HEADING.match(stripped)
        if heading and line.lstrip() == stripped:
            # A folder such as `== Code ==` stays inside @parameters.
            # The next Label: at the left edge is still a parameter.
            param_indent = None
            title = heading.group(2).strip()
            if block == "parameters":
                folder_name = title
                folder_content_indent = None
                start(title, "folder")
            else:
                start(title, "title" if block == "title" else block)
            continue
        label = _LABEL.match(line)
        if block in {"parameters", "inputs", "outputs"} and label and not stripped.startswith("#") and not stripped.startswith(":"):
            indent = len(label.group(1))
            if param_indent is None or indent <= param_indent:
                if folder_name:
                    if folder_content_indent is None:
                        folder_content_indent = indent
                    elif indent < folder_content_indent:
                        folder_name = ""
                        folder_content_indent = None
                param_indent = indent if param_indent is None else param_indent
                role = "parameter" if block == "parameters" else block[:-1]
                start(label.group(2).strip(), role)
                continue
            if current is not None and current.role == "parameter":
                choice = _Draft(label.group(2).strip(), "option", "")
                current.options.append(choice)
                current.option = choice
                continue
        if current is None:
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
    def __init__(self, heading: str, role: str, folder: str) -> None:
        self.heading = heading
        self.role = role
        self.folder = folder
        self.channels: list[str] = []
        self.lines: list[str] = []
        self.options: list[_Draft] = []
        self.option: _Draft | None = None


def _finish(draft: _Draft) -> Section:
    while draft.lines and draft.lines[-1] == "":
        draft.lines.pop()
    body = textwrap.dedent("\n".join(draft.lines)).strip()
    options = tuple((item.heading, _body(item)) for item in draft.options)
    return Section(draft.heading, tuple(draft.channels), body, draft.role, draft.folder, options)


def _body(draft: _Draft) -> str:
    while draft.lines and draft.lines[-1] == "":
        draft.lines.pop()
    return textwrap.dedent("\n".join(draft.lines)).strip()


def _mtime(path: str) -> int:
    try:
        return int(os.path.getmtime(path))
    except OSError:
        return 0
