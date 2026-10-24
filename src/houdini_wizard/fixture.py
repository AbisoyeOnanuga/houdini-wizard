"""Check the quote, the heading list, and a card restored by the same workflow id."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from houdini_wizard.help_file import load_path, load_zip_member
from houdini_wizard.pick import decide
from houdini_wizard.workflow import TASK_QUEUE, CardWorkflow, open_card, pick_heading_activity, workflow_id

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "box.txt"
UNNAMED = "Primitive count exceeds the point limit for this cook."
INSTALL_ZIP = Path(r"C:\Program Files\Side Effects Software\Houdini 22.0.466\houdini\help\nodes.zip")


def fail(message: str) -> None:
    print(f"FAIL {message}")
    sys.exit(1)


def check_file(path: Path) -> None:
    loaded = load_path(str(path))
    headings = [section.heading for section in loaded.sections]
    if "Polygon" in headings:
        fail("a menu choice was treated as a heading")
    size = next(section for section in loaded.sections if section.heading == "Size")
    if "sizex" not in [channel.lstrip("/") for channel in size.channels]:
        fail("Size is missing the sizex channel")
    if "Size of the box along xyz axes." not in size.body:
        fail("Size quote is missing the installed sentence")

    quoted = decide(loaded.sections, "sizex", "Size", "")
    if quoted["needs_model"] or quoted["known_heading"] != "Size":
        fail(f"selected Size still called Gemma: {quoted['known_heading']!r}")
    print("Quote: Size")
    print(size.body)
    print()

    named = decide(loaded.sections, "", "", "Uniform Scale must be greater than zero.")
    if named["needs_model"] or named["known_heading"] != "Uniform Scale":
        fail("cook error that names Uniform Scale did not quote it")
    print("Quote from cook error: Uniform Scale")
    print()

    unnamed = decide(loaded.sections, "", "", UNNAMED)
    if not unnamed["needs_model"] or unnamed["known_heading"]:
        fail("an unnamed cook error skipped Gemma")
    print("No heading named. The file's headings:")
    for heading in unnamed["headings"]:
        print(f"- {heading}")
    print()


def check_install() -> None:
    if not INSTALL_ZIP.is_file():
        print("Installed nodes.zip was not on this machine. Fixture file only.")
        print()
        return
    loaded = load_zip_member(str(INSTALL_ZIP), "sop/box.txt")
    headings = [section.heading for section in loaded.sections]
    if "Size" not in headings or "Polygon" in headings:
        fail(f"installed sop/box.txt headings look wrong: {headings[:12]}")
    size = next(section for section in loaded.sections if section.heading == "Size")
    if "Size of the box along xyz axes." not in size.body:
        fail("installed Size section was not quoted")
    print(f"Installed help: {loaded.source}")
    print(f"Headings: {len(headings)}. Menu choice Polygon stayed inside Primitive Type.")
    print()


async def check_restore() -> None:
    import houdini_wizard.pick as pick_mod

    loaded = load_path(str(FIXTURE))
    calls = {"n": 0}
    original = pick_mod.pick_heading

    def fake(headings: list[str], error_text: str) -> str:
        calls["n"] += 1
        return "none"

    pick_mod.pick_heading = fake
    try:
        async with await WorkflowEnvironment.start_time_skipping() as env:
            worker = Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[CardWorkflow],
                activities=[pick_heading_activity],
            )
            async with worker:
                quoted = decide(loaded.sections, "scale", "Uniform Scale", "")
                card_id = workflow_id("/obj/geo1/box1", "scale", "")
                first = await open_card(env.client, card_id, quoted)
                second = await open_card(env.client, card_id, quoted)
                if first["title"] != "Uniform Scale" or second["title"] != first["title"]:
                    fail("the same workflow id did not restore the quote")
                if calls["n"] != 0:
                    fail("Gemma ran for a heading that was already named")
                print(f"Restored card: {second['title']}")

                unnamed = decide(loaded.sections, "", "", UNNAMED)
                other_id = workflow_id("/obj/geo1/box1", "", UNNAMED)
                listed = await open_card(env.client, other_id, unnamed)
                again = await open_card(env.client, other_id, unnamed)
                if listed["kind"] != "list" or again["headings"] != listed["headings"]:
                    fail("the unnamed error did not restore the heading list")
                if calls["n"] != 1:
                    fail(f"Gemma ran {calls['n']} times for one card")
                print("Restored heading list from the same workflow id. Gemma ran once.")
    finally:
        pick_mod.pick_heading = original


def main() -> None:
    os.chdir(ROOT)
    check_file(FIXTURE)
    check_install()
    asyncio.run(check_restore())
    print("Fixture passed.")


if __name__ == "__main__":
    main()
