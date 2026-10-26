"""One Temporal Python workflow per card.

A normal node is saved as well as a cook error. The activity runs only when
Gemma must choose a heading. The help text stays in Houdini. The finished run
stays in the local database so the same card can be opened again.
"""

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
async def pick_heading_activity(request: dict) -> dict:
    from temporalio import activity as temporal_activity

    from houdini_wizard.pick import last_usage, pick_heading
    from houdini_wizard.usage import skipped

    heading = pick_heading(request.get("headings") or [], request.get("error_text") or "")
    usage = last_usage() or skipped("pick a heading", "The heading pick did not report a model call.")
    try:
        usage["attempt"] = int(temporal_activity.info().attempt)
    except Exception:
        pass
    return {"heading": heading, "usage": usage}


def _kind(request: dict) -> str:
    label = str(request.get("status_label") or "").strip()
    if not label:
        return "message"
    return label[:1].lower() + label[1:]


def plain_reason(request: dict, *, asking: bool = False, chosen: str = "") -> str:
    """A sentence for the person looking at the node."""
    kind = _kind(request)
    showing = bool(str(request.get("error_text") or "").strip())
    matched = request.get("matched") or ""
    if chosen and chosen != "none":
        return f"Gemma chose {chosen} from this node's help."
    if chosen == "none":
        return "Gemma found no heading in this file for what this node is showing."
    if asking:
        return (
            f"This node's {kind} is not a heading in its help. "
            "Gemma is choosing the closest heading from that file, or none."
        )
    if matched == "status" and showing:
        return f"This node's {kind} names a heading in its help, so the card quotes that section."
    if matched == "parameter" or request.get("known_heading"):
        return "The parameter you selected is a heading in this node's help, so the card quotes that section."
    return (
        "This node is not showing an error, a warning, or a message. "
        "The card is the help installed with Houdini."
    )


def _log_card(request: dict) -> dict:
    """What Temporal keeps for this card. The help bodies stay in Houdini."""
    error_text = request.get("error_text") or ""
    known = request.get("known_heading") or ""
    needs_model = bool(request.get("needs_model")) and not known
    kind = _kind(request)
    if needs_model:
        situation = f"This node's {kind} is not a heading in its help."
    elif request.get("matched") == "status" and error_text.strip() and known:
        situation = f"This node's {kind} names a heading in its help."
    elif known:
        situation = "Quoted from this install"
    else:
        situation = "Opened this node"
    quote = ""
    if known:
        for section in request.get("sections") or []:
            if isinstance(section, dict) and section.get("heading") == known:
                quote = section.get("body") or ""
                break
    return {
        "node_path": request.get("node_path") or "",
        "type_label": request.get("type_label") or "",
        "parm_label": request.get("shown_parm") or request.get("parm_label") or "",
        "error_text": error_text,
        "known_heading": known,
        "needs_model": needs_model,
        "situation": situation,
        "status_label": request.get("status_label") or "",
        "matched": request.get("matched") or "",
        "headings": list(request.get("headings") or []),
        "quote": quote,
    }


@workflow.defn
class CardWorkflow:
    @workflow.run
    async def run(self, request: dict) -> dict:
        heading = request.get("known_heading") or ""
        usage: dict = {
            "used": False,
            "task": "quote the heading" if heading else "open the node",
            "reason": plain_reason(request),
        }
        if not heading and request.get("needs_model"):
            picked = await workflow.execute_activity(
                pick_heading_activity,
                {"headings": request.get("headings") or [], "error_text": request.get("error_text") or ""},
                start_to_close_timeout=timedelta(seconds=90),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            if isinstance(picked, dict):
                heading = str(picked.get("heading") or "")
                reported = picked.get("usage")
                if isinstance(reported, dict):
                    usage = reported
            else:
                heading = str(picked or "")
            usage = dict(usage)
            usage["reason"] = plain_reason(request, chosen=heading or "none")
            usage["task"] = "pick a heading"
            usage["skill"] = usage.get("skill") or "houdini-section"
        heading = heading or "none"
        return {
            "heading": heading,
            "situation": request.get("situation") or "",
            "node_path": request.get("node_path") or "",
            "type_label": request.get("type_label") or "",
            "parm_label": request.get("parm_label") or "",
            "error_text": request.get("error_text") or "",
            "needs_model": bool(request.get("needs_model")),
            "quote": request.get("quote") or "",
            "usage": usage,
        }


def workflow_id(node_path: str, parm_name: str, error_text: str) -> str:
    raw = f"{node_path}\n{parm_name}\n{error_text.strip()}"
    return "wizard-v2-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


async def open_card(client: Client, card_id: str, request: dict) -> dict:
    """Run the heading pick, or wait for the pick already running under this id.

    The help text stays in this process. Temporal stores the node, the cook
    error, the situation, and the heading. ``kept`` says whether this call
    started the run or found it still going.
    """
    logged = _log_card(request)
    try:
        result = await client.execute_workflow(
            CardWorkflow.run,
            logged,
            id=card_id,
            task_queue=TASK_QUEUE,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
        kept = "stored"
    except WorkflowAlreadyStartedError:
        handle = client.get_workflow_handle(card_id)
        result = await handle.result()
        kept = "reopened"
    heading = result.get("heading") if isinstance(result, dict) else result
    card = card_from_heading(request.get("sections") or [], heading or "none")
    card["kept"] = kept
    card["card_id"] = card_id
    card["heading"] = heading or "none"
    if isinstance(result, dict) and isinstance(result.get("usage"), dict):
        card["usage"] = result["usage"]
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
