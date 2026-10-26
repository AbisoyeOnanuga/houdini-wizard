"""Start or reopen one help card from a normal Python process.

Houdini's asyncio loop refuses any thread except the main one, and it cannot
host the Temporal client. The shelf launches this module with the system
Python and reads the card back from stdout.
"""

from __future__ import annotations

import asyncio
import json
import sys

from houdini_wizard.memory import heading_of, remember
from houdini_wizard.workflow import connect, open_card


async def _run(card_id: str, request: dict) -> dict:
    client = await connect()
    card = await open_card(client, card_id, request)
    heading = heading_of(card)
    if request.get("needs_model") or (heading and heading != "none"):
        remember(card_id, heading)
    return card


def main() -> None:
    card_id = sys.argv[1]
    request = json.load(sys.stdin)
    card = asyncio.run(_run(card_id, request))
    json.dump(card, sys.stdout)


if __name__ == "__main__":
    main()
