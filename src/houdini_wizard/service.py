"""Start the local Temporal service for this shelf.

Temporal's development server is a separate program. A fresh install downloads
that program once. Opening the tool starts it in the background, with the
history kept in `.temporal/dev.db`. The artist does not run a terminal command.
The monitor stays at http://localhost:8233.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import threading
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".temporal"
CLI_VERSION = "1.9.1"
CLI_URL = (
    "https://github.com/temporalio/cli/releases/download/"
    f"v{CLI_VERSION}/temporal_cli_{CLI_VERSION}_windows_amd64.zip"
)
_LOCK = threading.Lock()
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_FLAGS = _NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def port_open(port: int = 7233) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def cli_path() -> Path | None:
    bundled = STATE / "bin" / "temporal.exe"
    if bundled.is_file():
        return bundled
    found = shutil.which("temporal")
    if found:
        return Path(found)
    packaged = Path(os.environ.get("LOCALAPPDATA", "")) / (
        "Microsoft/WinGet/Packages/Temporal.TemporalCLI_Microsoft.Winget.Source_8wekyb3d8bbwe/temporal.exe"
    )
    if packaged.is_file():
        return packaged
    return None


def ensure_cli() -> Path:
    """Return temporal.exe, downloading the official Windows build once if needed."""
    found = cli_path()
    if found is not None:
        return found
    destination = STATE / "bin" / "temporal.exe"
    destination.parent.mkdir(parents=True, exist_ok=True)
    archive = STATE / "temporal-cli.zip"
    urllib.request.urlretrieve(CLI_URL, archive)
    with zipfile.ZipFile(archive) as package:
        member = next(name for name in package.namelist() if Path(name).name == "temporal.exe")
        target = destination.parent / Path(member).name
        with package.open(member) as source, target.open("wb") as output:
            output.write(source.read())
    return destination


def worker_python() -> str:
    recorded = STATE / "client-python.txt"
    if recorded.is_file():
        path = recorded.read_text(encoding="utf-8").strip()
        if path and Path(path).is_file():
            return path
    hfs = os.environ.get("HFS", "")
    hython = Path(hfs) / "bin" / "hython.exe" if hfs else None
    if hython is not None and hython.is_file():
        return str(hython)
    return shutil.which("python") or "python"


def _worker_alive() -> bool:
    pidfile = STATE / "worker.pid"
    if not pidfile.is_file():
        return False
    try:
        pid = int(pidfile.read_text(encoding="utf-8").strip())
    except ValueError:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    import ctypes

    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(handle)
    return True


def _spawn(command: list[str]) -> int:
    process = subprocess.Popen(
        command,
        creationflags=_FLAGS,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        cwd=str(ROOT),
        close_fds=True,
    )
    return process.pid


def ensure_running() -> None:
    """Start the server and the worker when they are not already up."""
    with _LOCK:
        if not port_open():
            database = STATE / "dev.db"
            database.parent.mkdir(parents=True, exist_ok=True)
            _spawn(
                [
                    str(ensure_cli()),
                    "server",
                    "start-dev",
                    "--db-filename",
                    str(database),
                ]
            )
            for _ in range(40):
                if port_open():
                    break
                threading.Event().wait(0.25)
            else:
                raise RuntimeError("The recovery service did not start")
        if _worker_alive():
            return
        pid = _spawn([worker_python(), "-m", "houdini_wizard.workflow"])
        (STATE / "worker.pid").write_text(str(pid), encoding="utf-8")
