"""Start the local Temporal service for this shelf, and stop it with Houdini.

Temporal's development server is a separate program. A fresh install downloads
that program once. Opening the tool starts it in the background, and the
browser stays closed. Ending Houdini stops it, including when the process is killed, so it does not stay
behind and use memory. The artist does not run a terminal command.
"""

from __future__ import annotations

import atexit
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

from houdini_wizard.userlog import PAGE_PORT

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
_JOB = None
_OWNED: list[tuple[str, int]] = []
_STOP_REGISTERED = False


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
    pid = _read_pid("worker")
    return pid is not None and _alive(pid)


def _worker_current() -> bool:
    """True when the running worker was started from this copy of the workflow."""
    if not _worker_alive():
        return False
    stamp = STATE / "worker.stamp"
    source = Path(__file__).with_name("workflow.py")
    if not stamp.is_file() or not source.is_file():
        return False
    try:
        return stamp.read_text(encoding="utf-8").strip() == str(source.stat().st_mtime)
    except OSError:
        return False


def _write_worker_stamp() -> None:
    source = Path(__file__).with_name("workflow.py")
    try:
        (STATE / "worker.stamp").write_text(str(source.stat().st_mtime), encoding="utf-8")
    except OSError:
        return


def history_exists() -> bool:
    """True when a previous session already left a database file."""
    database = STATE / "dev.db"
    try:
        return database.is_file() and database.stat().st_size > 0
    except OSError:
        return False


def ensure_running() -> None:
    """Start the server and the worker when they are not already up.

    Processes started here are tied to this Houdini process. When Houdini
    exits, they exit too.
    """
    with _LOCK:
        _own_existing()
        if not port_open():
            database = STATE / "dev.db"
            database.parent.mkdir(parents=True, exist_ok=True)
            _spawn(
                "server",
                [
                    str(ensure_cli()),
                    "server",
                    "start-dev",
                    "--db-filename",
                    str(database),
                ],
            )
            for _ in range(40):
                if port_open():
                    break
                threading.Event().wait(0.25)
            else:
                raise RuntimeError("The recovery service did not start")
        if not _worker_current():
            previous = _read_pid("worker")
            if previous and _alive(previous):
                _terminate(previous)
                for _ in range(20):
                    if not _alive(previous):
                        break
                    threading.Event().wait(0.05)
            _spawn("worker", [worker_python(), "-m", "houdini_wizard.workflow"])
            _write_worker_stamp()
        if not port_open(PAGE_PORT):
            _spawn("page", [worker_python(), "-m", "houdini_wizard.userview"])
        _register_stop()


def stop_owned() -> None:
    """Ask the service we started to exit, then end anything still running."""
    owned = list(_OWNED)
    for _kind, pid in owned:
        _signal_stop(pid)
    deadline = time.time() + 2
    while time.time() < deadline and any(_alive(pid) for _kind, pid in owned):
        time.sleep(0.1)
    for kind, pid in owned:
        if _alive(pid):
            _terminate(pid)
        _clear_pid(kind)


def _spawn(kind: str, command: list[str]) -> None:
    process = subprocess.Popen(
        command,
        creationflags=_FLAGS,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        cwd=str(ROOT),
        close_fds=True,
    )
    _note(kind, process.pid, getattr(process, "_handle", None))


def _own_existing() -> None:
    """Adopt a service left from the last Houdini, so this exit can stop it."""
    if port_open():
        recorded = _read_pid("server")
        pid = recorded if recorded and _alive(recorded) else _pid_listening(7233)
        if pid and not _known(pid):
            _note("server", pid, None)
    worker = _read_pid("worker")
    if worker and _alive(worker) and not _known(worker):
        _note("worker", worker, None)
    page = _read_pid("page")
    if not (page and _alive(page)):
        page = _pid_listening(PAGE_PORT) if port_open(PAGE_PORT) else None
    if page and not _known(page):
        _note("page", page, None)


def _note(kind: str, pid: int, handle) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / f"{kind}.pid").write_text(str(pid), encoding="utf-8")
    _assign_job(pid, handle)
    if not _known(pid):
        _OWNED.append((kind, pid))


def _known(pid: int) -> bool:
    return any(owned == pid for _kind, owned in _OWNED)


def _register_stop() -> None:
    global _STOP_REGISTERED
    if _STOP_REGISTERED:
        return
    _STOP_REGISTERED = True
    atexit.register(stop_owned)


def _read_pid(kind: str) -> int | None:
    path = STATE / f"{kind}.pid"
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _clear_pid(kind: str) -> None:
    try:
        (STATE / f"{kind}.pid").unlink(missing_ok=True)
    except OSError:
        return


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    code = wintypes.DWORD()
    ok = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel.CloseHandle(handle)
    if not ok:
        return False
    return code.value == 259


def _pid_listening(port: int) -> int | None:
    completed = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_NO_WINDOW,
        check=False,
    )
    token = f":{port}"
    for line in completed.stdout.splitlines():
        if "LISTENING" not in line or token not in line:
            continue
        parts = line.split()
        try:
            return int(parts[-1])
        except (ValueError, IndexError):
            continue
    return None


def _signal_stop(pid: int) -> None:
    if os.name != "nt":
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return
        return
    try:
        os.kill(pid, signal.CTRL_BREAK_EVENT)
    except OSError:
        _terminate(pid)


def _terminate(pid: int) -> None:
    if os.name != "nt":
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            return
        return
    import ctypes

    handle = ctypes.windll.kernel32.OpenProcess(0x1F0FFF, False, pid)
    if not handle:
        return
    ctypes.windll.kernel32.TerminateProcess(handle, 1)
    ctypes.windll.kernel32.CloseHandle(handle)


def _assign_job(pid: int, handle) -> None:
    """End this process when Houdini's process handle closes, even if killed."""
    if os.name != "nt":
        return
    job = _job_handle()
    if job is None:
        return
    import ctypes

    kernel = ctypes.windll.kernel32
    opened = None
    if not handle:
        handle = kernel.OpenProcess(0x0100 | 0x0001, False, pid)
        opened = handle
    if not handle:
        return
    kernel.AssignProcessToJobObject(job, int(handle))
    if opened:
        kernel.CloseHandle(opened)


def _job_handle():
    global _JOB
    if _JOB:
        return _JOB
    if os.name != "nt":
        return None
    import ctypes

    kernel = ctypes.windll.kernel32

    class Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class Counters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class Extended(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", Basic),
            ("IoInfo", Counters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    job = kernel.CreateJobObjectW(None, None)
    if not job:
        return None
    info = Extended()
    info.BasicLimitInformation.LimitFlags = 0x2000
    if not kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        kernel.CloseHandle(job)
        return None
    _JOB = job
    return job
