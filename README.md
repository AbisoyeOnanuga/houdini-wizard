# Houdini wizard tool

Shelf tool for Houdini. Select a node, or a parameter whose channel is selected. The window stays open while you work, and it follows the next node you select. It shows that node's inputs and outputs, then each parameter with the menu choices from the help that shipped with this install, including the pictures on the shelf page. You still set the values and the look.

![Flow](docs/flow.svg)

The same labels are in [FLOW.md](FLOW.md).

You still change the node. The shelf does not set a value.

## What is added to Gemma

Gemma does not know this shelf. `skills/houdini-section/SKILL.md` is sent only when a cook error does not already name a heading. It tells the model to return one heading from the list it was given, or `none`. A normal Ollama chat can paraphrase the help or invent a number. This file forbids both.

Python quotes the section. The model never writes the card.

Add another file under `skills/` when a later call needs its own constraint, and name it here.

## Help files

Houdini stores node help as wiki text in `$HFS/houdini/help/nodes.zip`. One member is one node, for example `sop/box.txt`.

A heading is a `= Title =` line, a `== Folder ==` line, or a parameter `Label:` under `@parameters`. The real parameter names are on the next `#channels:` line (`/sizex` belongs to Size). A more-indented `Label:` is a menu choice on that parameter. The panel lists those choices with the sentence the help file gives them. A `:include` of a shelf page can add the short steps and the pictures. The shelf reads that one node, that included page, and those image bytes. It does not extract the archives or start the help server behind `?`. The split for that node is kept for the rest of the Houdini session.

## Model

This click is one constrained choice, so the model to pull is `gemma3:4b`. It is the speed and accuracy balance for a short JSON heading. Ollama's `format` schema limits the reply to a heading from the file, or `none`.

`deepseek-r1:8b` is a reasoning model. It spends the click on a hidden chain of thought. Leave it for other work.

```powershell
ollama pull gemma3:4b
```

To use another Gemma tag, set `HOUDINI_WIZARD_MODEL` before the worker starts.

## Temporal

The feature is one durable Workflow, written with the Temporal Python SDK. It is not the multi-process agent harness, and the CLI is not the feature. The CLI only runs a local Temporal Service so that workflow has somewhere to live.

`CardWorkflow` does two things:

- The heading pick is an Activity with three attempts. If Gemma fails, Temporal runs that call again. A heading that was already named never becomes an Activity.
- The card's id is a Workflow id. The same node and the same cook error reuse that id (`REJECT_DUPLICATE`). The next shelf click returns the stored result and does not call Gemma again. A new cook error is a new id, and a new card.

The shelf starts that server in the background when you open the tool, including after the server was stopped. The history stays in `.temporal\dev.db`. There is no terminal step. On a new computer the install command below places `temporal.exe` the first time; opening the tool is what starts it.

Open [http://localhost:8233](http://localhost:8233) after the tool is open. That page is the monitor: one run per card opened with the shelf, a retry, and a second open that did not ask the model again. Selecting another node updates the help and does not add a run. The help window shows Saved, Restored, or Not saved.

Temporal's docs describe `temporal server start-dev` as the local development server, a single program with a database file, not a production cluster and not a window the artist keeps open. A production service would be [Temporal Cloud or a self-hosted cluster](https://docs.temporal.io/production-deployment). This tool starts the local server so Houdini can recover a card. The same command, if you ever want to start it yourself, is:

```powershell
temporal server start-dev --db-filename D:\Documents\vscode\houdini-wizard\.temporal\dev.db
```

## Install

Houdini is the only thing to install first. From this folder, one command installs the shelf and prepares Temporal:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Restart Houdini. The shelf tab is **Houdini Wizard**. The tool is **Section card**. Opening it starts the monitor at [http://localhost:8233](http://localhost:8233). Pull the model once if you want heading picks: `ollama pull gemma3:4b`.

1. Select a node.
2. To quote one parameter, click its name so that channel is selected, then click the shelf. The label or the `#channels` name has to match a heading. Gemma is not called.
3. A cook error that already contains a heading quotes that section. Gemma is not called.
4. A cook error that does not name a heading asks Gemma, inside the Temporal workflow.
5. If nothing matches, the dialog lists the file's headings. You open one.

Clicking other nodes updates the help and does not open a console. Click **Section card** on the node you are working on. The banner changes from Saving to Saved. Quit Houdini after that, open the same node, and click the shelf again. The banner says Restored, and the monitor still has one row for that card.

Short value lines that needed the model are remembered in the Houdini user preferences. They are not a separate workflow.

## Why the code exists

Entire records the agent session that built this tool. The shelf click does not call it. A technical reader asks from this repository:

```powershell
python -m houdini_wizard.why "why a named heading skips Gemma"
```

With no question, the same command lists the checkpoints for the build, each tied to the commit it produced. One checkpoint, `01M5QRE9FZAKB6Q9V2K6HRS78R`, is the session where the card became one Temporal workflow: the heading pick is an activity with three attempts, and a heading that is already named never becomes that activity. `entire checkpoint explain <id>` opens that session. The artist-facing card stays the help quote.
