import json
import uuid
from datetime import datetime, timezone

import structlog
from arq.connections import ArqRedis
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.models import Decision, PendingConfirmation
from app.db.session import async_session_factory
from app.slack import router
from app.slack import client as slack_client
from app.slack.messages import build_confirmed_blocks, build_ignored_blocks
from app.slack.verify import verify_slack_signature

log = structlog.get_logger()


@router.post("/interactive")
async def slack_interactive(request: Request) -> Response:
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if settings.slack_signing_secret and not verify_slack_signature(
        settings.slack_signing_secret, timestamp, body, signature
    ):
        return Response(status_code=401)

    form = await request.form()
    payload = json.loads(form.get("payload", "{}"))
    action_type = payload.get("type")

    if action_type == "block_actions":
        actions = payload.get("actions", [])
        if not actions:
            return Response(status_code=200)

        action = actions[0]
        action_id = action.get("action_id")
        decision_id = action.get("value")
        user = payload.get("user", {})
        user_id = user.get("id", "")
        channel = payload.get("channel", {})
        channel_id = channel.get("id", "")
        message = payload.get("message", {})
        message_ts = message.get("ts", "")

        arq_pool = request.app.state.arq_pool

        if action_id == "confirm_decision":
            await _handle_confirm(decision_id, user_id, channel_id, message_ts, arq_pool)
        elif action_id == "edit_decision":
            await _handle_edit(decision_id, payload)
        elif action_id == "ignore_decision":
            await _handle_ignore(decision_id, user_id, channel_id, message_ts)

    return Response(status_code=200)


async def _handle_confirm(
    decision_id: str,
    user_id: str,
    channel_id: str,
    message_ts: str,
    arq_pool: ArqRedis,
) -> None:
    async with async_session_factory() as session:
        decision = (
            await session.execute(
                select(Decision)
                .options(selectinload(Decision.workspace))
                .where(Decision.id == uuid.UUID(decision_id))
            )
        ).scalar_one_or_none()

        if decision is None:
            log.error("decision_not_found", decision_id=decision_id)
            return

        workspace = decision.workspace
        decision.status = "active"
        decision.confirmed_at = datetime.now(timezone.utc)
        decision.confirmed_by = user_id
        await session.commit()
        await session.refresh(decision)

        log.info("decision_confirmed", decision_id=decision_id, user_id=user_id)
        if workspace and workspace.bot_access_token:
            blocks = build_confirmed_blocks(decision)
            await slack_client.update_message(
                workspace.bot_access_token,
                channel_id,
                message_ts,
                text=f"Decision confirmed: {decision.title}",
                blocks=blocks,
            )

        await arq_pool.enqueue_job("enrich_decision", decision_id)
        await arq_pool.enqueue_job("generate_embedding_task", decision_id)


async def _handle_edit(decision_id: str, payload: dict) -> None:
    trigger_id = payload.get("trigger_id", "")

    async with async_session_factory() as session:
        decision = (
            await session.execute(
                select(Decision)
                .options(selectinload(Decision.workspace))
                .where(Decision.id == uuid.UUID(decision_id))
            )
        ).scalar_one_or_none()

        if decision is None:
            log.error("decision_not_found", decision_id=decision_id)
            return

        workspace = decision.workspace
        if not workspace or not workspace.bot_access_token:
            return

        view = {
            "type": "modal",
            "callback_id": "edit_decision_modal",
            "private_metadata": decision_id,
            "title": {"type": "plain_text", "text": "Edit Decision"},
            "submit": {"type": "plain_text", "text": "Save"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "title_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "title_input",
                        "initial_value": decision.title or "",
                    },
                    "label": {"type": "plain_text", "text": "Title"},
                },
                {
                    "type": "input",
                    "block_id": "summary_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "summary_input",
                        "multiline": True,
                        "initial_value": decision.summary or "",
                    },
                    "label": {"type": "plain_text", "text": "Summary"},
                    "optional": True,
                },
                {
                    "type": "input",
                    "block_id": "rationale_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "rationale_input",
                        "multiline": True,
                        "initial_value": decision.rationale or "",
                    },
                    "label": {"type": "plain_text", "text": "Rationale"},
                    "optional": True,
                },
                {
                    "type": "input",
                    "block_id": "tags_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "tags_input",
                        "initial_value": ", ".join(decision.tags) if decision.tags else "",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "comma-separated tags",
                        },
                    },
                    "label": {"type": "plain_text", "text": "Tags"},
                    "optional": True,
                },
            ],
        }

        await slack_client.open_modal(workspace.bot_access_token, trigger_id, view)


async def _handle_ignore(
    decision_id: str,
    user_id: str,
    channel_id: str,
    message_ts: str,
) -> None:
    async with async_session_factory() as session:
        decision = (
            await session.execute(
                select(Decision)
                .options(selectinload(Decision.workspace))
                .where(Decision.id == uuid.UUID(decision_id))
            )
        ).scalar_one_or_none()

        if decision is None:
            log.error("decision_not_found", decision_id=decision_id)
            return

        workspace = decision.workspace
        decision.status = "ignored"
        await session.commit()
        await session.refresh(decision)

        log.info("decision_ignored", decision_id=decision_id, user_id=user_id)
        if workspace and workspace.bot_access_token:
            blocks = build_ignored_blocks(decision)
            await slack_client.update_message(
                workspace.bot_access_token,
                channel_id,
                message_ts,
                text=f"Decision ignored: {decision.title}",
                blocks=blocks,
            )
