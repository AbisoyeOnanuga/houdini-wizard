"""List the help cards Temporal has kept for this project.

The shelf writes one workflow per node, parameter, and cook error. This
prints those ids so a later shelf click can reopen the same card. The same
list is the Web UI at http://localhost:8233 while the dev server is running.
"""

from __future__ import annotations

import asyncio

from houdini_wizard.workflow import TASK_QUEUE, connect


async def list_cards(limit: int = 20) -> list[str]:
    client = await connect()
    lines: list[str] = []
    async for execution in client.list_workflows(f'TaskQueue="{TASK_QUEUE}"', limit=limit):
        status = getattr(execution.status, "name", execution.status)
        when = execution.start_time.isoformat(timespec="seconds") if execution.start_time else ""
        lines.append(f"{execution.id}  {status}  {when}")
    return lines


def main() -> None:
    print("Help cards stored for houdini-wizard")
    print("History: http://localhost:8233")
    try:
        lines = asyncio.run(list_cards())
    except Exception as exc:
        print(f"Temporal is not reachable at localhost:7233 ({exc}).")
        print("Start the dev server, then click the shelf on a node.")
        return
    if not lines:
        print("No cards yet. Click the shelf on a node while the server and the worker are running.")
        return
    for line in lines:
        print(line)


if __name__ == "__main__":
    main()
