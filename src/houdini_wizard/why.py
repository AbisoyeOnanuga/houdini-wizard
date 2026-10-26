"""Why a piece of this tool exists, for a technical reader.

The shelf click does not call Entire. From this repository:

    python -m houdini_wizard.why "why a named heading skips Gemma"

That searches the recorded agent session and lists the checkpoints behind
the answer. Pass no question to list the checkpoints for the build session.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSION = "e96d75ea-ea02-4990-b94a-81678a4c1465"

QUESTIONS = (
    "why a named heading skips Gemma",
    "why the help card is stored in Temporal",
    "why the window stays where the artist moved it",
)


def _entire(*args: str) -> subprocess.CompletedProcess[str]:
    program = shutil.which("entire") or str(Path.home() / ".local" / "bin" / "entire.exe")
    return subprocess.run(
        [program, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _checkpoints(question: str) -> str:
    result = _entire("checkpoint", "explain", "--session", SESSION)
    text = (result.stdout or result.stderr).strip()
    if result.returncode != 0:
        return text or "Entire could not list the checkpoints for this session."
    words = {word.lower() for word in question.split() if len(word) > 3}
    rows: list[tuple[int, str]] = []
    current_id = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("●"):
            parts = line.split()
            current_id = parts[1] if len(parts) > 1 else ""
            continue
        if not current_id or not line[:1].isdigit():
            continue
        score = sum(len(word) for word in words if word in line.lower())
        rows.append((score, f"{current_id}  {line}"))
        current_id = ""
    rows.sort(key=lambda item: item[0], reverse=True)
    chosen = [line for score, line in rows if score > 0][:2] or [line for _, line in rows[:2]]
    if not chosen:
        return "No checkpoint matched that question."
    return "\n".join(chosen)


def _search(question: str) -> str:
    result = _entire("search", "--json", "--compact", question)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return detail or "Entire search did not run. Check that `entire` is on PATH in this repo."
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout.strip()
    hits = payload.get("results") or []
    if not hits:
        return "No recorded session matched that question."
    lines = [f"Question: {question}", ""]
    for hit in hits[:3]:
        title = hit.get("title") or hit.get("id")
        kind = hit.get("type") or "hit"
        when = hit.get("date") or ""
        lines.append(f"{kind}: {title}")
        if when:
            lines.append(f"  {when}")
        snippet = (hit.get("snippet") or "").strip()
        if snippet:
            lines.append(f"  {snippet}")
        lines.append("")
    lines.append("The checkpoint behind that answer:")
    lines.append(_checkpoints(question))
    lines.append("")
    lines.append("Read it with: entire checkpoint explain <id>")
    return "\n".join(lines).strip()


def main() -> None:
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        print("Ask why a piece of this tool exists. The shelf does not call Entire.")
        print()
        for item in QUESTIONS:
            print(f"  python -m houdini_wizard.why \"{item}\"")
        print()
        print(_checkpoints("help card shelf gemma temporal window"))
        return
    print(_search(question))


if __name__ == "__main__":
    main()
