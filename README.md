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

The shelf starts that server in the background the first time a card is saved, using the database file in `.temporal`. An artist does not run the command and does not see a console. The commands below are for the person who wants the monitor open first.

Open [http://localhost:8233](http://localhost:8233) while the dev server is running. That page is optional. It lists one run per card opened with the shelf, a retry, and a second open that did not ask the model again. Selecting another node updates the help and does not add a run. The help window shows Saved, Restored, or Not saved on the card itself.

Temporal's own docs treat `temporal server start-dev` as the local development server, not a production cluster and not a window the artist operates. A production service would be Temporal Cloud or a self-hosted cluster. This tool uses the local server so a Houdini install can recover a card without those steps. The Web UI can be turned off with `--headless`; we leave it on so the monitor stays available.

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

List the cards this project has stored:

```powershell
python -m houdini_wizard.history
```

Each line is one card. The same id is the row in the Web UI. Opening the tool on that node again reopens that row instead of starting another model call.

### Test the stored card

Leave the dev server and the worker running. Restart Houdini so it loads the current shelf code. Select a node and click **Section card**. The banner changes from Saving to Saved, and one row appears at [http://localhost:8233](http://localhost:8233). Clicking other nodes updates the help. It does not open a console and it does not add a row.

Quit Houdini after the banner says Saved. Open it again, select that same node, and click the shelf. The banner says Restored. The monitor still has one workflow for that id, and the model is not asked again.

Short value lines that needed the model are remembered in the Houdini user preferences, so the next session does not ask for them again. They are not a separate workflow.

A named heading never starts the model activity. To see the retry, use a cook error whose text does not contain a help heading, and stop Ollama before the click. The activity in the monitor tries up to three times. Start Ollama again before those attempts run out if you want the card to finish. Closing Houdini during those attempts does not start a second run. The next time you open the tool on that node, it waits for the run already in progress and then shows that result.

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

## Why the code exists

Entire records the agent session that built this tool. The shelf click does not call it. A technical reader asks from this repository:

```powershell
python -m houdini_wizard.why "why a named heading skips Gemma"
```

With no question, the same command lists the checkpoints for the build, each tied to the commit it produced. One checkpoint, `01M5QRE9FZAKB6Q9V2K6HRS78R`, is the session where the card became one Temporal workflow: the heading pick is an activity with three attempts, and a heading that is already named never becomes that activity. `entire checkpoint explain <id>` opens that session. The artist-facing card stays the help quote.
