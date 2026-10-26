"""Why a piece of this tool exists, for a technical reader.

The shelf click does not call Entire. From this repository, with no question,
a local page opens:

    python -m houdini_wizard.why

A question on the command line still prints the matches:

    python -m houdini_wizard.why "why a named heading skips Gemma"

Search uses `entire search --json`. The page does not upload anything.
Checkpoints already sync to the git remote, and entire.com is where they
are browsed after `entire login`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from houdini_wizard.whyview import PAGE

ROOT = Path(__file__).resolve().parents[2]
PAGE_PORT = 8245
QUESTIONS = (
    "why a named heading skips Gemma",
    "why the help card is stored in Temporal",
    "why the window stays where the artist moved it",
)
_CHECKPOINT = re.compile(r"^01[0-9A-HJKMNP-TV-Z]{24}$")
_SESSION = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_SHA = re.compile(r"^[0-9a-f]{40}$")


def accept_checkpoint(value: str) -> bool:
    return bool(_CHECKPOINT.fullmatch(value or ""))


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
        timeout=45,
    )


def _question(value: str) -> str:
    text = " ".join(str(value or "").split())
    return text[:180]


def _plain(value, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def repo_slug() -> str:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "AbisoyeOnanuga/houdini-wizard"
    match = re.search(r"github\.com[:/]([^/\s]+)/([^/\s.]+)", result.stdout or "")
    if not match:
        return "AbisoyeOnanuga/houdini-wizard"
    return f"{match.group(1)}/{match.group(2)}"


def dashboard_url() -> str:
    return f"https://entire.com/gh/{repo_slug()}"


def shape_hit(item: dict) -> dict:
    """The fields the page shows. Prompt text is left out."""
    if not isinstance(item, dict):
        return {}
    kind = _plain(item.get("type"), 20) or "hit"
    identity = _plain(item.get("id"), 80)
    if kind == "session" and not _SESSION.fullmatch(identity):
        identity = ""
    if kind == "checkpoint" and not accept_checkpoint(identity):
        identity = ""
    return {
        "id": identity,
        "type": kind,
        "title": _plain(item.get("title"), 140),
        "date": _plain(item.get("date"), 40),
        "author": _plain(item.get("author"), 80),
        "branch": _plain(item.get("branch"), 80),
    }


def _files(value) -> list[str]:
    found: list[str] = []
    if not isinstance(value, list):
        return found
    for item in value:
        if isinstance(item, str):
            name = _plain(item, 160)
        elif isinstance(item, dict):
            name = _plain(item.get("path") or item.get("file") or item.get("name"), 160)
        else:
            name = ""
        if name and name not in found:
            found.append(name)
        if len(found) == 12:
            break
    return found


def shape_detail(payload: dict, *, commit: str = "", dashboard: str = "") -> dict:
    """Files, agent, and token counts. Transcript text is not copied."""
    sessions = []
    for item in payload.get("sessions") or []:
        if not isinstance(item, dict):
            continue
        usage = item.get("token_usage") if isinstance(item.get("token_usage"), dict) else {}
        sessions.append(
            {
                "agent": _plain(item.get("agent"), 40),
                "model": _plain(item.get("model"), 40),
                "created_at": _plain(item.get("created_at"), 40),
                "input_tokens": usage.get("input_tokens") if isinstance(usage.get("input_tokens"), int) else None,
                "output_tokens": usage.get("output_tokens") if isinstance(usage.get("output_tokens"), int) else None,
            }
        )
        if len(sessions) == 4:
            break
    sha = commit if _SHA.fullmatch(commit or "") else ""
    slug = dashboard or dashboard_url()
    return {
        "id": _plain(payload.get("checkpoint_id"), 32),
        "branch": _plain(payload.get("branch"), 80),
        "files": _files(payload.get("files_touched")),
        "sessions": sessions,
        "commit": sha,
        "dashboard": slug,
        "commit_url": f"{slug}/commit/{sha}" if sha else "",
    }


def _error_text(result: subprocess.CompletedProcess[str]) -> str:
    text = _plain(result.stderr or result.stdout, 240)
    if not text:
        text = "Entire search did not run. Install the Entire CLI and run it from this repository."
    lowered = text.lower()
    if "login" in lowered or "auth" in lowered:
        text += " Run entire login in this repository, then search again."
    return text


def _rank(question: str, rows: list[dict]) -> list[dict]:
    words = {word.lower() for word in question.split() if len(word) > 3}
    scored = []
    for item in rows:
        message = item.get("message") or ""
        score = sum(len(word) for word in words if word in message.lower())
        scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    matched = [item for score, item in scored if score > 0]
    return (matched or [item for _, item in scored])[:6]


def _checkpoints(session_id: str, question: str) -> list[dict]:
    if not _SESSION.fullmatch(session_id or ""):
        return []
    result = _entire("checkpoint", "explain", "--session", session_id, "--json", "--limit", "40", "--no-pager")
    if result.returncode != 0:
        return []
    try:
        payload = json.loads(result.stdout or "")
    except json.JSONDecodeError:
        return []
    rows = payload if isinstance(payload, list) else []
    if isinstance(payload, dict):
        rows = payload.get("checkpoints") or payload.get("results") or []
    chosen: list[dict] = []
    for item in rows:
        if not isinstance(item, dict) or not accept_checkpoint(str(item.get("checkpoint_id") or "")):
            continue
        chosen.append(
            {
                "id": item["checkpoint_id"],
                "message": _plain(item.get("message"), 240),
                "date": _plain(item.get("date"), 40),
                "agent": _plain(item.get("agent"), 40),
            }
        )
    return _rank(question, chosen)


def ask(question: str) -> dict:
    """Search recorded sessions and attach the checkpoints behind the first match."""
    text = _question(question)
    home = {"question": text, "dashboard": dashboard_url(), "hits": [], "checkpoints": []}
    if not text:
        home["error"] = "Ask why a piece of this tool exists."
        return home
    try:
        result = _entire("search", "--json", "--compact", "--limit", "5", text)
    except (OSError, subprocess.TimeoutExpired) as exc:
        home["error"] = _plain(exc, 240) or "Entire search did not finish."
        return home
    if result.returncode != 0:
        home["error"] = _error_text(result)
        return home
    try:
        payload = json.loads(result.stdout or "")
    except json.JSONDecodeError:
        home["error"] = "Entire search did not return a result list."
        return home
    hits = [hit for hit in (shape_hit(item) for item in payload.get("results") or []) if hit.get("id")]
    home["hits"] = hits[:5]
    looked = 0
    for hit in home["hits"]:
        if hit["type"] == "checkpoint":
            home["checkpoints"] = [{"id": hit["id"], "message": hit["title"], "date": hit["date"], "agent": ""}]
            break
        if hit["type"] != "session":
            continue
        looked += 1
        found = _checkpoints(hit["id"], text)
        if found:
            home["checkpoints"] = found
            break
        if looked >= 2:
            break
    if not home["hits"]:
        home["error"] = "No recorded session matched that question."
    return home


def _commit_for(checkpoint_id: str) -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H", f"--grep={checkpoint_id}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    sha = (result.stdout or "").strip()
    return sha if _SHA.fullmatch(sha) else ""


def detail(checkpoint_id: str) -> dict:
    if not accept_checkpoint(checkpoint_id):
        return {"error": "That is not a checkpoint id."}
    try:
        result = _entire("checkpoint", "explain", checkpoint_id, "--json", "--no-pager")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": _plain(exc, 240) or "That checkpoint could not be read."}
    if result.returncode != 0:
        return {"error": _error_text(result)}
    try:
        payload = json.loads(result.stdout or "")
    except json.JSONDecodeError:
        return {"error": "That checkpoint did not return a readable record."}
    if not isinstance(payload, dict):
        return {"error": "That checkpoint did not return a readable record."}
    return shape_detail(payload, commit=_commit_for(checkpoint_id), dashboard=dashboard_url())


def _format(payload: dict) -> str:
    if payload.get("error") and not payload.get("checkpoints"):
        return str(payload["error"])
    lines = [f"Question: {payload.get('question', '')}", ""]
    for item in payload.get("checkpoints") or []:
        lines.append(item["id"])
        if item.get("message"):
            lines.append(f"  {item['message']}")
        lines.append("")
    if not payload.get("checkpoints"):
        for hit in payload.get("hits") or []:
            lines.append(f"{hit['type']}: {hit['title']}")
            lines.append("")
    lines.append(f"Browse the same checkpoints on {payload.get('dashboard') or dashboard_url()}")
    lines.append("The shelf does not call Entire.")
    return "\n".join(lines).strip()


def serve(open_browser: bool = True) -> None:
    """Serve the why page on this computer. Nothing starts it from the shelf."""
    url = f"http://127.0.0.1:{PAGE_PORT}"

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path in {"/", "/index.html"}:
                self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
                return
            if path == "/home":
                self._json({"dashboard": dashboard_url(), "questions": list(QUESTIONS)})
                return
            if path == "/search":
                question = parse_qs(urlparse(self.path).query).get("q", [""])[0]
                self._json(ask(question))
                return
            if path == "/checkpoint":
                identity = parse_qs(urlparse(self.path).query).get("id", [""])[0]
                self._json(detail(identity))
                return
            self._send(404, "text/plain; charset=utf-8", b"Not found")

        def log_message(self, fmt: str, *args) -> None:
            return

        def _json(self, payload: dict) -> None:
            self._send(200, "application/json; charset=utf-8", json.dumps(payload).encode("utf-8"))

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    try:
        server = ThreadingHTTPServer(("127.0.0.1", PAGE_PORT), _Handler)
    except OSError:
        print(f"Why this code exists is already open at {url}")
        if open_browser:
            webbrowser.open(url)
        return
    print(f"Why this code exists: {url}")
    print("The shelf does not open this page. On entire.com, open the same repository and use Search.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return


def main() -> None:
    args = sys.argv[1:]
    if not args or args == ["--page"]:
        serve(open_browser=True)
        return
    print(_format(ask(" ".join(args))))


if __name__ == "__main__":
    main()
