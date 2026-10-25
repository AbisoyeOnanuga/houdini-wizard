"""One Temporal Python workflow. It retries the heading pick and restores the card."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.worker import Worker

TASK_QUEUE = "houdini-wizard"

with workflow.unsafe.imports_passed_through():
    from houdini_wizard.card import card_from_heading


@activity.defn(name="pick_heading_activity")
async def pick_heading_activity(request: dict) -> str:
    from houdini_wizard.pick import pick_heading

    return pick_heading(request["headings"], request["error_text"])


@workflow.defn
class CardWorkflow:
    @workflow.run
    async def run(self, request: dict) -> dict:
        heading = request.get("known_heading") or ""
        if not heading and request.get("needs_model"):
            heading = await workflow.execute_activity(
                pick_heading_activity,
                {"headings": request.get("headings") or [], "error_text": request.get("error_text") or ""},
                start_to_close_timeout=timedelta(seconds=90),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        return card_from_heading(request.get("sections") or [], heading or None)


def workflow_id(node_path: str, parm_name: str, error_text: str) -> str:
    raw = f"{node_path}\n{parm_name}\n{error_text.strip()}"
    return "wizard-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


async def open_card(client: Client, card_id: str, request: dict) -> dict:
    """Run the card, or return the one already stored under this id.

    The workflow result stays as the quote. ``kept`` is added here so the
    shelf can say whether this click stored a new card or reopened one.
    """
    try:
        card = await client.execute_workflow(
            CardWorkflow.run,
            request,
            id=card_id,
            task_queue=TASK_QUEUE,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
        kept = "stored"
    except WorkflowAlreadyStartedError:
        handle = client.get_workflow_handle(card_id)
        card = await handle.result()
        kept = "reopened"
    card = dict(card)
    card["kept"] = kept
    card["card_id"] = card_id
    return card


async def connect(address: str | None = None) -> Client:
    import os

    target = address or os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    return await Client.connect(target)


async def run_worker() -> None:
    client = await connect()
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[CardWorkflow],
        activities=[pick_heading_activity],
    )
    print(f"Houdini wizard worker on {TASK_QUEUE}", flush=True)
    await worker.run()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
