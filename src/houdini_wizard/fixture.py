"""Check the quote, the heading list, and a card restored by the same workflow id."""

from __future__ import annotations

import asyncio
import os
import sys
import warnings
from pathlib import Path

from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from houdini_wizard.context import build_study, _value_guide
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

    study = build_study(
        loaded.sections,
        {
            "type_label": "Box",
            "category": "Sop",
            "path": "/obj/geo1/box1",
            "error": "",
            "inputs": [{"label": "Bounding source", "wired": ""}],
            "outputs": [],
        },
        "Size",
    )
    if "geometry network" not in study["where"].lower():
        fail("the panel did not say which network the node is in")
    if "nothing is wired" in " ".join(study["wires_in"]) or "no node connected" not in " ".join(study["wires_in"]):
        fail("an empty input was not shown")
    if "Size" not in study["note"] or any(char.isdigit() for char in study["note"]):
        fail("the note invented a value or missed the parameter")
    primitive = next(section for section in loaded.sections if section.heading == "Primitive Type")
    if [name for name, _body in primitive.options] != ["Polygon"]:
        fail("Polygon was not kept as a menu choice on Primitive Type")
    if any(char.isdigit() for _name, body in primitive.options for char in body):
        fail("a menu choice grew a number the help file does not have")
    ranged = build_study(
        loaded.sections,
        {
            "type_label": "Box",
            "category": "Sop",
            "ranges": {
                "Size": {"low": 0, "high": 1, "low_strict": True, "high_strict": True},
                "Primitive Type": {"low": 0, "high": 1, "low_strict": True, "high_strict": True},
            },
            "inputs": [],
            "outputs": [],
        },
        "Size",
    )
    size_row = next(row for row in ranged["parameters"] if row["name"] == "Size")
    menu_row = next(row for row in ranged["parameters"] if row["name"] == "Primitive Type")
    if "from 0 to 1" not in size_row["range"] or "what the line above" in size_row["range"]:
        fail("a 0 to 1 parameter did not explain both ends")
    if menu_row["range"]:
        fail("a menu parameter was given a number range")
    rotate = _value_guide(
        "Rotate",
        "Rotate angles in degrees",
        {"low": 0, "high": 360, "low_strict": False, "high_strict": False},
    )
    if "no rotation" not in rotate or "360" not in rotate or "clockwise" in rotate.lower():
        fail("a rotation was not explained from its own help")
    ocean = _value_guide(
        "Ocean Size",
        "The world space size of the generated ocean spectrum. Increasing this value will fit more wave peaks into a single ocean tile.",
        {"low": 0, "high": 50, "low_strict": True, "high_strict": False},
    )
    if "wave peaks" not in ocean or "what the line above" in ocean:
        fail("a parameter with a real tooltip fell back to a generic line")
    print("Panel: geometry network, empty input, Size left for the artist.")
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

    unwrap = load_zip_member(str(INSTALL_ZIP), "sop/uvunwrap.txt")
    layout = next(section for section in unwrap.sections if section.heading == "Layout")
    choices = [name for name, _body in layout.options]
    if choices != ["Strip", "Square"]:
        fail(f"Layout choices were not Strip and Square: {choices}")
    strip = next(body for name, body in layout.options if name == "Strip")
    if "offset in U" not in strip or "largest remaining" in strip:
        fail("Strip picked up another choice's sentence")
    hfs = str(INSTALL_ZIP.parents[2])
    guide = build_study(
        unwrap.sections,
        {
            "type_label": "UV Unwrap",
            "category": "Sop",
            "path": "/obj/geo1/uvunwrap1",
            "hfs": hfs,
            "includes": unwrap.includes,
            "parm_label": "Layout",
            "values": {"Layout": "Square"},
            "inputs": [{"label": "Input", "wired": ""}],
            "outputs": [],
        },
        "Layout",
    )
    marked = next(row for row in guide["parameters"] if row["name"] == "Layout")
    if marked["current"] != "Square" or not any(option["current"] for option in marked["options"]):
        fail("the current menu choice was not marked")
    if not guide["steps"] or not any(figure["images"] for figure in guide["figures"]):
        fail("the shelf picture and steps were not picked up")
    if "File Cache" not in guide["cache"] or any(char.isdigit() for char in guide["cache"]):
        fail("the cache note invented a number or missed the technique")
    print("UV Unwrap: Strip and Square, current choice marked, picture and steps included.")
    print()

    project = load_zip_member(str(INSTALL_ZIP), "sop/uvproject.txt")
    translate = next(section for section in project.sections if section.heading == "Translate")
    u_range = next(section for section in project.sections if section.heading == "U Range")
    if translate.folder != "Transformation" or u_range.folder:
        fail(f"parameter tabs were mixed up: Translate={translate.folder!r} U Range={u_range.folder!r}")
    print("UV Project: Transformation stays its own tab, and U Range is not pulled into it.")
    print()

    from houdini_wizard.help_file import installed_help

    ocean_help = installed_help("Cop", "oceanspectrum", str(INSTALL_ZIP.parents[2]))
    wind = next(section for section in ocean_help.sections if section.heading == "Wind Speed")
    distribution = next(section for section in ocean_help.sections if section.heading == "Distribution")
    if "Higher wind speeds" not in wind.body:
        fail("the parameter tooltip was not pulled from the linked help page")
    if "Gaussian" not in [name for name, _body in distribution.options]:
        fail("a menu tooltip did not bring its choices")
    print("Ocean Spectrum: Wind Speed and Distribution use the parameter-window tooltip.")
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


def check_ui_thread() -> None:
    """The shelf runs while Houdini's loop is already running."""
    from houdini_wizard.shelf import _run_async

    async def sample():
        return "kept"

    async def inside_houdini_loop():
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", RuntimeWarning)
            value = _run_async(sample())
        leaked = [item for item in caught if "never awaited" in str(item.message)]
        if value != "kept" or leaked:
            fail("the shelf dropped the Temporal coroutine")
        print("Panel open: the Temporal call is awaited on Houdini's loop.")

    asyncio.run(inside_houdini_loop())


def main() -> None:
    os.chdir(ROOT)
    check_file(FIXTURE)
    check_install()
    check_ui_thread()
    asyncio.run(check_restore())
    print("Fixture passed.")


if __name__ == "__main__":
    main()
