# Houdini wizard tool

Shelf tool for Houdini. Select a node, or a parameter whose channel is selected. The window stays open while you work, and it follows the next node you select. It shows that node's inputs and outputs, then each parameter with the menu choices from the help that shipped with this install, including the pictures on the shelf page. You still set the values and the look.

![Flow](docs/flow.svg)

The same labels are in [FLOW.md](FLOW.md).

You still change the node. The shelf does not set a value.

## What is added to Gemma

Gemma does not know this shelf. `skills/houdini-section/SKILL.md` is sent only when an error, a warning, or a message on the node does not already name a heading. It tells the model to return one heading from the list it was given, or `none`. A normal Ollama chat can paraphrase the help or invent a number. This file forbids both.

Python quotes the section. The model never writes the card.

Add another file under `skills/` when a later call needs its own constraint, and name it here.

## Help files

Houdini stores node help as wiki text in `$HFS/houdini/help/nodes.zip`. One member is one node, for example `sop/box.txt`.

A heading is a `= Title =` line, a `== Folder ==` line, or a parameter `Label:` under `@parameters`. The real parameter names are on the next `#channels:` line (`/sizex` belongs to Size). A more-indented `Label:` is a menu choice on that parameter. The panel lists those choices with the sentence the help file gives them. A `:include` of a shelf page can add the short steps and the pictures. The shelf reads that one node, that included page, and those image bytes. It does not extract the archives or start the help server behind `?`. The split for that node is kept for the rest of the Houdini session.

## Model

This click is one constrained choice, so the model to pull is `gemma3:4b`. It is the speed and accuracy balance for a short JSON heading. Ollama's `format` schema limits the reply to a heading from the file, or `none`. The install steps are under [Ollama and Gemma](#ollama-and-gemma).

`deepseek-r1:8b` is a reasoning model. It spends the click on a hidden chain of thought. Leave it for other work.

## Temporal

The feature is one durable Workflow, written with the Temporal Python SDK. A multi-process agent harness is a different kind of tool: the model chooses the next step, and several processes keep a conversation going. This shelf already knows the steps. Opening a node saves that card, whether or not the node is showing an error, a warning, or a message. A heading named by the parameter or by that text is quoted from the installed help, and Gemma is not called. Gemma runs only when that text names no heading, and it may only return one of those headings or `none`.

Each card is one workflow:

- A normal node is stored with no model call. The same node and parameter reuse that id, so looking at it again does not add another row.
- An error, warning, or message that names no heading is an Activity, with three attempts. If Gemma times out, the same run tries again. It does not start a second call that might both succeed.
- The help text never enters the workflow. Python quotes the section from this install.
- The service starts when the tool opens, with no console window. It stops when Houdini exits, including when Houdini is ended from outside, so the process does not stay behind. The rows stay in `.temporal\dev.db`.

The browser stays closed. **Session log** and **Developer monitor** are buttons on the panel, and each page opens only when you click it. [http://localhost:8244](http://localhost:8244) is the session for the person using the tool: one line per node, so Saving becomes Saved on that line. The line names the parameter, the heading, the situation, the quoted sentence, any cook error, and the other headings in that file. It also says whether Gemma ran. A quote says Gemma was not asked. A heading pick shows the model name, the skill file, the attempt, the round trip, and the prompt and answer token counts Ollama reported, plus how long that call took. Short value lines that needed Gemma are a separate Model line, because they are not a workflow. There is no dollar cost: the model is local, so the numbers are time and tokens on this computer. **From this install** stays on that same line when the quote came from this Houdini. **Light** on that page switches it, and the choice stays on this computer. [http://localhost:8233](http://localhost:8233) is the developer view of those runs. Each run stores the node path, the node type, the parameter, the cook error, the situation, the heading names, and the quoted sentence when a heading is already known.

Temporal's docs describe `temporal server start-dev` as the local development server, a single program with a database file, not a production cluster and not a window the artist keeps open. A production service would be [Temporal Cloud or a self-hosted cluster](https://docs.temporal.io/production-deployment). This tool uses the local server because the artist is on one computer. Each node you open is one saved card. A cook error that names no heading retries inside that card. The same command, if you ever want to start it yourself, is:

```powershell
temporal server start-dev --db-filename D:\Documents\vscode\houdini-wizard\.temporal\dev.db
```

## Install

Houdini is the only thing to install first. From this folder, one command installs the shelf and prepares Temporal:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Restart Houdini. The shelf tab is **Houdini Wizard**. The tool is **Section card**. Opening it starts recovery in the background. **Session log** and **Developer monitor** are on the panel. Quotes from this install do not need a model. Heading picks and thin value lines do. Those steps are next.

### Ollama and Gemma

Ollama runs Gemma on this computer. The shelf talks to `http://127.0.0.1:11434`. It does not use a cloud model or an API key.

On Windows, Ollama's installer is the one on [the Windows download page](https://ollama.com/download/windows). In PowerShell:

```powershell
irm https://ollama.com/install.ps1 | iex
```

Close that terminal and open a new one, so `ollama` is on the path. The app stays running in the background and serves the local API. You do not leave a chat window open.

Pull the tag this shelf asks for. The download is about 3.4 GB, and it needs [Ollama 0.6 or later](https://ollama.com/library/gemma3:4b).

```powershell
ollama pull gemma3:4b
ollama list
```

`ollama list` should show `gemma3:4b`. Then restart Houdini if it was already open.

A quoted parameter still works when this step is skipped. An error, warning, or message that names no heading, or a value tip too short to explain itself, needs the model. If the session log says Gemma did not answer, Ollama is not running or `gemma3:4b` is not in `ollama list`.

To point the shelf at another local tag, set `HOUDINI_WIZARD_MODEL` to that tag before Houdini starts. To point it at another local Ollama address, set `HOUDINI_WIZARD_OLLAMA`. Restart Houdini after either change. The worker reads them when the tool opens.

### Use the shelf

1. Select a node.
2. To quote one parameter, click its name so that channel is selected, then click the shelf. The label or the `#channels` name has to match a heading. Gemma is not called.
3. An error, a warning, or a message that already names a heading quotes that section. Gemma is not called.
4. An error, a warning, or a message that does not name a heading asks Gemma, inside the Temporal workflow, to choose one heading from this node's help or `none`.
5. If nothing matches, the dialog lists the file's headings. You open one.

Clicking other nodes updates the help and saves that card. The same node does not add a second row. The Temporal line goes from **Saving** to **Saved**, and a quoted section also shows **From this install**. An error, a warning, or a message that does not name a heading uses that same save, and Gemma chooses the heading inside it. Quit Houdini and the service process stops. The database file remains. Open the tool on that node again. The Temporal line says **Restored**.

Short value lines that needed the model are remembered in the Houdini user preferences. They are not a separate workflow.

## Why the code exists

Entire records the agent session that built this tool. The shelf click does not call it. A technical reader asks from this repository:

```powershell
python -m houdini_wizard.why "why a named heading skips Gemma"
```

With no question, the same command lists the checkpoints for the build, each tied to the commit it produced. One checkpoint, `01M5QRE9FZAKB6Q9V2K6HRS78R`, is the session where the card became one Temporal workflow: the heading pick is an activity with three attempts, and a heading that is already named never becomes that activity. `entire checkpoint explain <id>` opens that session. The artist-facing card stays the help quote.
