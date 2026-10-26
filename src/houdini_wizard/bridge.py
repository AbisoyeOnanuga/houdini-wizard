"""Start or reopen one help card from a normal Python process.

Houdini's asyncio loop refuses any thread except the main one, and it cannot
host the Temporal client. The shelf launches this module with the system
Python and reads the card back from stdout.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys

from houdini_wizard.memory import heading_of, remember
from houdini_wizard.service import release_command
from houdini_wizard.workflow import connect, open_card, release_card


async def _run(card_id: str, request: dict) -> dict:
    client = await connect()
    card = await open_card(client, card_id, request)
    if remember(card_id, heading_of(card)):
        card["released"] = await _drop(client, card_id)
    else:
        card["released"] = False
    return card


async def _drop(client, card_id: str) -> bool:
    try:
        await release_card(client, card_id)
        return True
    except Exception:
        return _release_cli(card_id)


def _release_cli(card_id: str) -> bool:
    try:
        completed = subprocess.run(
            release_command(card_id),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


async def _release_only(card_id: str) -> None:
    client = await connect()
    await _drop(client, card_id)


def main() -> None:
    card_id = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] == "--release":
        asyncio.run(_release_only(card_id))
        return
    request = json.load(sys.stdin)
    card = asyncio.run(_run(card_id, request))
    json.dump(card, sys.stdout)


if __name__ == "__main__":
    main()
