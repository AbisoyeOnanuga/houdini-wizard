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
from houdini_wizard.memory import uses_workflow
from houdini_wizard.pick import decide, finish
from houdini_wizard.workflow import (
    TASK_QUEUE,
    CardWorkflow,
    open_card,
    pick_heading_activity,
    workflow_id,
)

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
    if study["cache"]:
        fail("a fast node was told to cache")
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
    from houdini_wizard.values import _needs_model

    if not _needs_model("Rotate angles in degrees"):
        fail("a short angle label should be the one Gemma is allowed to rewrite")
    if _needs_model("The wind speed. Higher wind speeds create larger low-frequency waves."):
        fail("a tooltip that already explains the value was sent to Gemma")
    if _needs_model("Size of the box along xyz axes."):
        fail("an understandable size tip was sent to Gemma")
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
    if guide["cache"]:
        fail("UV Unwrap was given a cache note it does not need")
    pelt = next(item for item in guide["related_nodes"] if item["help"].endswith("/uvpelt"))
    if pelt["label"].lower() == "uvpelt" or not pelt["note"] or "installed help lists" in pelt["note"].lower():
        fail("a related node was missing its help-browser name or its own note")
    print("UV Unwrap: Strip and Square, current choice marked, picture and steps included.")
    print()

    project = load_zip_member(str(INSTALL_ZIP), "sop/uvproject.txt")
    translate = next(section for section in project.sections if section.heading == "Translate")
    u_range = next(section for section in project.sections if section.heading == "U Range")
    if translate.folder != "Transformation" or u_range.folder:
        fail(f"parameter tabs were mixed up: Translate={translate.folder!r} U Range={u_range.folder!r}")
    print("UV Project: Transformation stays its own tab, and U Range is not pulled into it.")
    arranged = load_zip_member(str(INSTALL_ZIP), "sop/uvlayout.txt")
    edges = next(section for section in arranged.sections if section.heading == "Separator edges")
    areas = next(section for section in arranged.sections if section.heading == "Scale Island to Match Their Surface Areas")
    if edges.groups != ("Islands To Pack", "Overrides", "Connectivity"):
        fail(f"Connectivity was not kept inside Overrides: {edges.groups}")
    if areas.groups != ("Islands To Pack",):
        fail(f"Scale Island left its parent folder: {areas.groups}")
    align = next(section for section in arranged.sections if section.heading == "Axis Alignment")
    if "By Island Symmetry (default)" not in [name for name, _body in align.options]:
        fail("Axis Alignment lost the menu choices from the help file")
    print("UV Layout: Overrides stays inside Islands To Pack.")
    vellum = load_zip_member(str(INSTALL_ZIP), "sop/vellumsolver.txt")
    if not any(section.role == "parameter" and section.groups[:2] == ("Solver", "Collisions") for section in vellum.sections):
        fail("Vellum Solver did not keep Collisions inside its own Solver folder")
    shader = load_zip_member(str(INSTALL_ZIP), "vop/principledshader.txt")
    if not any(
        section.role == "parameter" and section.groups[:3] == ("Surface", "Specular", "Reflection")
        for section in shader.sections
    ):
        fail("Principled Shader did not keep Reflection inside Surface / Specular")
    print("Vellum Solver and Principled Shader use the same folder nesting.")
    from houdini_wizard.help_file import library_catalog

    catalog = library_catalog(hfs)
    geometry = next(group for group in catalog if group["label"] == "Geometry")
    if not any(node["internal"] == "box" and node["label"] == "Box" for node in geometry["nodes"]):
        fail("the help library did not list Box under Geometry")
    if not any(group["label"] == "Dynamics" for group in catalog):
        fail("the help library left out Dynamics")
    print("Help library: Geometry includes Box, and Dynamics is its own section.")
    print()

    from houdini_wizard.help_file import installed_help

    ocean_help = installed_help("Cop", "oceanspectrum", str(INSTALL_ZIP.parents[2]))
    wind = next(section for section in ocean_help.sections if section.heading == "Wind Speed")
    distribution = next(section for section in ocean_help.sections if section.heading == "Distribution")
    if "Higher wind speeds" not in wind.body:
        fail("the parameter tooltip was not pulled from the linked help page")
    if "Gaussian" not in [name for name, _body in distribution.options]:
        fail("a menu tooltip did not bring its choices")
    spectrum = load_zip_member(str(INSTALL_ZIP), "sop/oceanspectrum.txt")
    heavy = build_study(
        spectrum.sections,
        {"type_label": "Ocean Spectrum", "category": "Sop", "hfs": hfs},
        "",
    )
    if "File Cache" not in heavy["cache"] or any(char.isdigit() for char in heavy["cache"]):
        fail("a heavy cook was missing the cache technique, or the note invented a number")
    flip = load_zip_member(str(INSTALL_ZIP), "dop/flipsolver.txt")
    sim = build_study(
        flip.sections,
        {"type_label": "FLIP Solver", "category": "Dop", "hfs": hfs},
        "",
    )
    help_paths = [item["help"] for item in sim["related_nodes"]]
    if not any(path.startswith("/nodes/dop/") for path in help_paths):
        fail("related nodes on a DOP were limited to SOP")
    if "/nodes/sop/particlefluidsurface" not in help_paths:
        fail("a SOP listed beside a DOP was dropped")
    fluid = next(item for item in sim["related_nodes"] if item["help"].endswith("/flipobject"))
    if "particle fluid object" not in fluid["note"].lower():
        fail("a DOP related note was not read from that node's help")
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
        quoted = decide(loaded.sections, "scale", "Uniform Scale", "")
        if uses_workflow(quoted):
            fail("a named heading asked Gemma")
        card = finish(quoted)
        if card["title"] != "Uniform Scale" or calls["n"] != 0:
            fail("a named heading did not stay a local quote")
        from houdini_wizard.workflow import _log_card

        noted = dict(quoted)
        noted["node_path"] = "/obj/geo1/box1"
        noted["type_label"] = "Box"
        noted["shown_parm"] = "Uniform Scale"
        logged = _log_card(noted)
        if logged["node_path"] != "/obj/geo1/box1" or logged["situation"] != "Quoted from this install":
            fail("the workflow log lost the node")
        if logged["parm_label"] != "Uniform Scale" or "sections" in logged:
            fail("the workflow log stored the help file instead of the node")
        if "Uniform Scale" not in logged["headings"] or not logged["quote"].strip():
            fail("the workflow log left out the heading list or the quote")

        async with await WorkflowEnvironment.start_time_skipping() as env:
            worker = Worker(
                env.client,
                task_queue=TASK_QUEUE,
                workflows=[CardWorkflow],
                activities=[pick_heading_activity],
            )
            async with worker:
                quote_id = workflow_id("/obj/geo1/box1", "scale", "")
                first = await open_card(env.client, quote_id, quoted)
                second = await open_card(env.client, quote_id, quoted)
                if first["title"] != "Uniform Scale" or second["title"] != first["title"]:
                    fail("a normal card was not saved")
                if first.get("kept") != "stored" or second.get("kept") != "reopened":
                    fail("the same node did not reopen the saved card")
                if first.get("usage", {}).get("used") is not False:
                    fail("a quoted card reported a model call")
                if "cook" in first.get("usage", {}).get("reason", "").lower():
                    fail("a quoted card talked about a cook error")
                if calls["n"] != 0:
                    fail("Gemma ran for a heading that was already named")
                print("Saved card without a cook error: Uniform Scale")

                unnamed = decide(loaded.sections, "", "", UNNAMED)
                if not uses_workflow(unnamed):
                    fail("an unnamed cook error skipped the workflow")
                other_id = workflow_id("/obj/geo1/box1", "", UNNAMED)
                listed = await open_card(env.client, other_id, unnamed)
                again = await open_card(env.client, other_id, unnamed)
                if listed["kind"] != "list" or again["headings"] != listed["headings"]:
                    fail("the unnamed error did not restore the heading list")
                if listed.get("kept") != "stored" or again.get("kept") != "reopened":
                    fail("the unnamed error did not report the reopened card")
                if listed.get("heading") != "none" or calls["n"] != 1:
                    fail(f"Gemma ran {calls['n']} times for one card")
                if listed.get("usage", {}).get("task") != "pick a heading":
                    fail("the heading pick did not record the model task")
                print("One heading pick, reopened from the same run. Gemma ran once.")
    finally:
        pick_mod.pick_heading = original


def check_memory() -> None:
    from tempfile import TemporaryDirectory

    from houdini_wizard.memory import KEEP, recall, remember

    previous = os.environ.get("HOUDINI_USER_PREF_DIR")
    with TemporaryDirectory() as tmp:
        os.environ["HOUDINI_USER_PREF_DIR"] = tmp
        if not remember("first", "Size") or recall("first") != "Size":
            fail("heading was not kept locally")
        for index in range(KEEP):
            remember(f"id-{index}", "none")
        if recall("first") is not None:
            fail("the local file kept every heading")
        if recall(f"id-{KEEP - 1}") != "none":
            fail("the newest heading was dropped")
    if previous is None:
        os.environ.pop("HOUDINI_USER_PREF_DIR", None)
    else:
        os.environ["HOUDINI_USER_PREF_DIR"] = previous
    print("Local file: newest headings only, one file.")
    print()


def check_userlog() -> None:
    from tempfile import TemporaryDirectory

    from houdini_wizard.userlog import read_events, record

    previous = os.environ.get("HOUDINI_WIZARD_USERLOG")
    with TemporaryDirectory() as tmp:
        os.environ["HOUDINI_WIZARD_USERLOG"] = str(Path(tmp) / "user-log.jsonl")
        record(
            {
                "state": "online",
                "title": "Saved",
                "detail": "Traceback (most recent call last): File \"shelf.py\", line 1",
                "node": "/obj/geo1/box1",
                "node_label": "Box",
                "heading": "Size",
                "source": "From this install",
            }
        )
        rows = read_events()
        if len(rows) != 1 or rows[0]["node"] != "/obj/geo1/box1":
            fail("the user log dropped the node")
        if "traceback" in rows[0]["detail"].lower() or "wizard-" in rows[0]["detail"]:
            fail("the user log kept a traceback")
        record({"state": "nope", "title": "Saved", "detail": "skip"})
        if len(read_events()) != 1:
            fail("an unknown status was logged")
        record(
            {
                "state": "working",
                "title": "Saving",
                "detail": "Saving this card.",
                "node": "/obj/geo1/blend1",
                "node_label": "Blend",
                "source": "From this install",
            }
        )
        record(
            {
                "state": "online",
                "title": "Saved",
                "detail": "This card is saved.",
                "node": "/obj/geo1/blend1",
                "node_label": "Blend",
                "heading": "Bias",
                "source": "From this install",
            }
        )
        record(
            {
                "state": "working",
                "title": "Saving",
                "detail": "Saving this card.",
                "node": "/obj/geo1/heighttonormal1",
                "node_label": "Height to Normal",
            }
        )
        rows = read_events()
        titles = [row["title"] for row in rows]
        if titles != ["Saved", "Saved", "Saving"]:
            fail("Saving and Saved stayed as two lines for one node")
        record(
            {
                "state": "online",
                "title": "Saved",
                "detail": "This card is saved.",
                "node": "/obj/geo1/heighttonormal1",
                "node_label": "Height to Normal",
            }
        )
        record(
            {
                "state": "restored",
                "title": "Restored",
                "detail": "Brought this card back.",
                "node": "/obj/geo1/blend1",
                "node_label": "Blend",
            }
        )
        rows = read_events()
        if [row["title"] for row in rows] != ["Saved", "Saved", "Saved", "Restored"]:
            fail("a later visit did not stay its own line")
        if rows[1]["node_label"] != "Blend" or rows[3]["node_label"] != "Blend":
            fail("a later visit replaced the first save")
        from houdini_wizard.shelf import _record

        from houdini_wizard.usage import from_ollama

        measured = from_ollama(
            {
                "model": "gemma3:4b",
                "prompt_eval_count": 20,
                "eval_count": 3,
                "total_duration": 1_500_000_000,
                "done_reason": "stop",
                "message": {"content": "do not keep this prompt"},
            },
            model="gemma3:4b",
            skill="houdini-section",
            task="pick a heading",
        )
        if measured["prompt_tokens"] != 20 or measured["answer_tokens"] != 3 or measured["total_ms"] != 1500:
            fail("model timing was not read from Ollama")
        if measured.get("done_reason") != "stop":
            fail("the model log left out how the answer stopped")
        from houdini_wizard.usage import from_ps

        resident = from_ps(
            {"models": [{"name": "gemma3:4b", "size": 3_300_000_000, "size_vram": 3_100_000_000}]},
            "gemma3:4b",
        )
        if resident.get("model_bytes") != 3_300_000_000 or resident.get("vram_bytes") != 3_100_000_000:
            fail("model memory was not read from Ollama")
        if "message" in measured or "content" in measured:
            fail("the model log kept the prompt")
        _record(
            {"state": "online", "title": "Saved", "detail": "This card is saved."},
            {
                "node_path": "/obj/geo1/font1",
                "type_label": "Font",
                "shown_parm": "Text",
                "known_heading": "Text",
                "matched": "status",
                "status_label": "Error",
                "needs_model": False,
                "error_text": 'Traceback (most recent call last):\n  File "shelf.py", line 4',
                "headings": ["Font", "Text", "wizard-secret"],
                "sections": [
                    {"heading": "Text", "body": "Text to write.\n\nThe rest of the section stays in Houdini."},
                ],
            },
            False,
            measured,
        )
        rows = read_events()
        font = rows[-1]
        if font["parameter"] != "Text" or font["quote"] != "Text to write.":
            fail("the session card left out the parameter or the quote")
        if "traceback" in font["error"].lower() or any(name.startswith("wizard-") for name in font["headings"]) or "sections" in font:
            fail("the session card kept a traceback, a workflow id, or the help body")
        if "cook" in font["situation"].lower() or "Font" not in font["headings"]:
            fail("the session card left out the situation or the heading names")
        if font.get("usage", {}).get("prompt_tokens") != 20 or font["usage"].get("answer_tokens") != 3:
            fail("the session card left out the token counts")
        if "do not keep" in str(font):
            fail("the session card kept the model prompt")
        record(
            {
                "state": "restored",
                "title": "Restored",
                "detail": "Brought this heading back. The model was not asked again.",
                "node": "/obj/geo1/font1",
                "node_label": "Font",
                "usage": {
                    "used": True,
                    "task": "pick a heading",
                    "replayed": True,
                    "prompt_tokens": 20,
                    "model_bytes": 3_300_000_000,
                    "vram_bytes": 3_100_000_000,
                },
            }
        )
        restored = read_events()[-1]
        if restored.get("usage", {}).get("replayed") is not True or restored["usage"].get("model_bytes") != 3_300_000_000:
            fail("a restored card lost the model memory")
    if previous is None:
        os.environ.pop("HOUDINI_WIZARD_USERLOG", None)
    else:
        os.environ["HOUDINI_WIZARD_USERLOG"] = previous
    print("User log: node and heading kept, traceback left out.")
    print()


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
    check_memory()
    check_userlog()
    check_ui_thread()
    asyncio.run(check_restore())
    print("Fixture passed.")


if __name__ == "__main__":
    main()
