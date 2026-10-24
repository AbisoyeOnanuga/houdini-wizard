"""Build the card from headings that are already in the file."""

from __future__ import annotations

import re

from houdini_wizard.help_file import Section


def card_from_heading(sections: list[dict], heading: str | None) -> dict:
    usable = [item for item in sections if item.get("heading")]
    names = [item["heading"] for item in usable]
    if heading and heading != "none":
        for item in usable:
            if item["heading"] == heading:
                return {
                    "kind": "quote",
                    "title": item["heading"],
                    "body": item.get("body") or "",
                    "headings": names,
                }
    return {
        "kind": "list",
        "title": "Headings in this file",
        "body": "",
        "headings": names,
    }


def match_parameter(sections: tuple[Section, ...] | list[Section], name: str, label: str) -> Section | None:
    name = name.strip().lstrip("/").lower()
    label = label.strip().lower()
    for section in sections:
        if label and section.heading.lower() == label:
            return section
        if name and _channel_match(section, name):
            return section
    return None


def match_error(sections: tuple[Section, ...] | list[Section], error_text: str) -> Section | None:
    text = error_text.strip().lower()
    if not text:
        return None
    best: Section | None = None
    best_len = 0
    for section in sections:
        tokens = [section.heading, *section.channels]
        for token in tokens:
            cleaned = token.strip().lstrip("/")
            minimum = 2 if token in section.channels else 3
            if len(cleaned) < minimum:
                continue
            if re.search(r"\b" + re.escape(cleaned.lower()) + r"\b", text):
                if len(cleaned) > best_len:
                    best = section
                    best_len = len(cleaned)
    return best


def _channel_match(section: Section, name: str) -> bool:
    for channel in section.channels:
        cleaned = channel.lstrip("/").lower()
        if cleaned == name:
            return True
    compact = re.sub(r"\s+", "", section.heading.lower())
    return compact == name
