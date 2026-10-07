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
from app.db.models import Decision, PendingConfirmation, User, Workspace
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

    if action_type == "view_submission":
        view = payload.get("view", {})
        if view.get("callback_id") == "edit_decision_modal":
            return await _save_edit(payload, request.app.state.arq_pool)
        return Response(status_code=200)

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


async def _editable_decision(session, decision_id: str, payload: dict):
    try:
        parsed_id = uuid.UUID(decision_id)
    except (ValueError, TypeError, AttributeError):
        return None
    team_id = payload.get("team", {}).get("id")
    user_id = payload.get("user", {}).get("id")
    if not team_id or not user_id:
        return None
    decision = (await session.execute(
        select(Decision).join(Workspace)
        .options(selectinload(Decision.workspace))
        .where(Decision.id == parsed_id, Workspace.slack_team_id == team_id,
               Decision.status.in_(["pending", "active"]))
    )).scalar_one_or_none()
    if decision is None:
        return None
    if decision.owner_slack_id == user_id:
        return decision
    admin = (await session.execute(select(User.id).where(
        User.workspace_id == decision.workspace_id,
        User.slack_user_id == user_id, User.is_admin.is_(True),
    ))).scalar_one_or_none()
    return decision if admin is not None else None


def _edit_errors(errors: dict) -> JSONResponse:
    return JSONResponse({"response_action": "errors", "errors": errors})


async def _save_edit(payload: dict, arq_pool: ArqRedis) -> Response:
    view = payload.get("view", {})
    values = view.get("state", {}).get("values", {})
    def value(field):
        return (values.get(f"{field}_block", {}).get(f"{field}_input", {}).get("value") or "").strip()
    title, summary, rationale, tags_text = (value(f) for f in ("title", "summary", "rationale", "tags"))
    errors = {}
    if not title or len(title) > 100:
        errors["title_block"] = "Enter a title between 1 and 100 characters."
    for field, content in (("summary", summary), ("rationale", rationale)):
        if len(content) > 2000:
            errors[f"{field}_block"] = "Use 2,000 characters or fewer."
    tags = list(dict.fromkeys(t.strip().lower() for t in tags_text.split(",") if t.strip()))
    if len(tags) > 20 or any(len(t) > 80 for t in tags):
        errors["tags_block"] = "Use at most 20 tags, each 80 characters or fewer."
    if errors:
        return _edit_errors(errors)
    async with async_session_factory() as session:
        decision = await _editable_decision(session, view.get("private_metadata"), payload)
        if decision is None:
            return _edit_errors({"title_block": "Only this decision's owner or a workspace admin can edit it."})
        changed = (decision.title, decision.summary or "", decision.rationale or "") != (title, summary, rationale)
        decision.title, decision.summary, decision.rationale, decision.tags = title, summary or None, rationale or None, tags
        if changed:
            # Do not serve an old semantic representation while the refresh is pending.
            decision.embedding = None
        await session.commit()
        decision_id = str(decision.id)
    try:
        await arq_pool.enqueue_job("refresh_edited_decision", decision_id)
    except Exception:
        log.exception("edit_refresh_enqueue_failed", decision_id=decision_id)
        return _edit_errors({"title_block": "Your changes were saved, but refresh could not start. Try Save again."})
    return Response(status_code=200)


async def _handle_edit(decision_id: str, payload: dict) -> None:
    trigger_id = payload.get("trigger_id", "")
    async with async_session_factory() as session:
        decision = await _editable_decision(session, decision_id, payload)
        if decision is None:
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
