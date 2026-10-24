# Houdini wizard tool

Shelf tool for Houdini. You select a node, or a parameter whose channel is selected, or you are stuck on a cook error. The card quotes the matching section from the help that shipped with this install.

![Flow](docs/flow.svg)

The same labels are in [FLOW.md](FLOW.md).

You still change the node. The shelf does not set a value.

## What is added to Gemma

Gemma does not know this shelf. `skills/houdini-section/SKILL.md` is sent only when a cook error does not already name a heading. It tells the model to return one heading from the list it was given, or `none`. A normal Ollama chat can paraphrase the help or invent a number. This file forbids both.

Python quotes the section. The model never writes the card.

Add another file under `skills/` when a later call needs its own constraint, and name it here.

## Help files

Houdini stores node help as wiki text in `$HFS/houdini/help/nodes.zip`. One member is one node, for example `sop/box.txt`.

A heading is a `= Title =` line, a `== Folder ==` line, or a parameter `Label:` under `@parameters`. The real parameter names are on the next `#channels:` line (`/sizex` belongs to Size). A more-indented `Label:` is a menu choice and stays inside that parameter's quote.

The shelf opens that one member. It does not extract the zip, scan other nodes, or start the help server behind `?`. The split for that member is kept for the rest of the Houdini session.

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

Open [http://localhost:8233](http://localhost:8233) while the dev server is running. That Web UI is the history of the card: the Workflow, the Activity, and the result. That page is the thing to show in the write-up.

### Where the CLI installs

`winget install --id Temporal.TemporalCLI -e` installs version 1.9.1 as a portable zip, not an MSI and not into Houdini or this repo. WinGet unpacks `temporal.exe` under your user profile (`%LOCALAPPDATA%\Microsoft\WinGet\Packages\`) and puts a `temporal` command on your PATH. It does not change Houdini. Open a new PowerShell window after the install so the command is visible. Confirm with `where.exe temporal`.

Docs: [Run a development server](https://docs.temporal.io/develop/run-a-development-server).

Start it and leave that window open:

```powershell
temporal server start-dev --db-filename D:\Documents\vscode\houdini-wizard\.temporal\dev.db
```

That process is the whole local service: `localhost:7233` for the SDK, and the Web UI at `http://localhost:8233`. The `--db-filename` flag stores the card in SQLite, so quitting Houdini does not drop it. Without that flag the server keeps the history in memory only, and stopping the server erases the cards. Ctrl+C stops the server.

### The worker

The worker is our Python process, already installed in `.venv`. It is not part of the CLI. It connects to `localhost:7233` and waits on the task queue `houdini-wizard`. The shelf starts the Workflow. The worker runs it, including the Gemma Activity.

In a second terminal:

```powershell
D:\Documents\vscode\houdini-wizard\.venv\Scripts\python -m houdini_wizard.workflow
```

It prints `Houdini wizard worker on houdini-wizard` and stays running. The shelf can show a quote with both of these stopped. Restore, and a Gemma pick, need the server and the worker.

## Install the shelf in Houdini 22

This machine's hython is Python 3.13, same as the worker. Install the package into hython so the shelf can import it:

```powershell
& "C:\Program Files\Side Effects Software\Houdini 22.0.466\bin\hython.exe" -m pip install --user -e "D:\Documents\vscode\houdini-wizard"
```

Use the `hython.exe` next to the Houdini you actually open.

Copy `shelf/houdini_wizard.shelf` into the toolbar folder hython reports as `HOUDINI_USER_PREF_DIR`. On this machine that folder is `D:\Documents\houdini22.0\toolbar`.

Restart Houdini. The shelf tab is **Houdini Wizard**. The tool is **Section card**.

1. Select a node.
2. To quote one parameter, click its name so that channel is selected, then click the shelf. The label or the `#channels` name has to match a heading. Gemma is not called.
3. A cook error that already contains a heading quotes that section. Gemma is not called.
4. A cook error that does not name a heading asks Gemma, inside the Temporal workflow.
5. If nothing matches, the dialog lists the file's headings. You open one.

Ollama, the dev server, and the worker need to be running for the Gemma pick and for restoring a card after Houdini quits. If Temporal is down, the shelf still shows the quote and says the card was not stored.

Entire records this build so a later search can explain why the shelf skips Gemma. The click does not call Entire.
