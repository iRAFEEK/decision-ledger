import json
import uuid

import structlog
from fastapi import Request, Response
from sqlalchemy import select

from app.config import settings
from app.db.models import MonitoredChannel, RawMessage, Workspace
from app.db.session import async_session_factory
from app.slack import router
from app.slack.verify import verify_slack_signature

log = structlog.get_logger()


@router.post("/events")
async def slack_events(request: Request) -> Response:
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")

    if settings.slack_signing_secret and not verify_slack_signature(
        settings.slack_signing_secret, timestamp, body, signature
    ):
        return Response(status_code=401)

    payload = json.loads(body)

    if payload.get("type") == "url_verification":
        return Response(
            content=json.dumps({"challenge": payload["challenge"]}),
            media_type="application/json",
        )

    event = payload.get("event", {})
    team_id = payload.get("team_id")

    if event.get("type") == "message":
        subtype = event.get("subtype")
        is_huddle = subtype == "huddle_thread"

        if event.get("bot_id"):
            return Response(status_code=200)
        if subtype and not is_huddle:
            return Response(status_code=200)

        async with async_session_factory() as session:
            workspace = (
                await session.execute(
                    select(Workspace).where(Workspace.slack_team_id == team_id)
                )
            ).scalar_one_or_none()

            if workspace is None:
                log.warning("workspace_not_found", team_id=team_id)
                return Response(status_code=200)

            channel_id = event.get("channel")
            monitored = (
                await session.execute(
                    select(MonitoredChannel).where(
                        MonitoredChannel.workspace_id == workspace.id,
                        MonitoredChannel.channel_id == channel_id,
                        MonitoredChannel.enabled.is_(True),
                    )
                )
            ).scalar_one_or_none()

            if monitored is None:
                return Response(status_code=200)

            # Deduplicate Slack retries by checking message_ts
            message_ts = event.get("ts")
            existing = (
                await session.execute(
                    select(RawMessage.id).where(
                        RawMessage.workspace_id == workspace.id,
                        RawMessage.channel_id == channel_id,
                        RawMessage.message_ts == message_ts,
                    )
                )
            ).scalar_one_or_none()

            if existing is not None:
                log.info("duplicate_message_skipped", message_ts=message_ts)
                return Response(status_code=200)

            raw_msg = RawMessage(
                id=uuid.uuid4(),
                workspace_id=workspace.id,
                slack_message_id=event.get("client_msg_id"),
                channel_id=channel_id,
                thread_ts=event.get("thread_ts"),
                user_slack_id=event.get("user"),
                text=event.get("text", ""),
                message_ts=message_ts,
                source_hint="huddle" if is_huddle else None,
                processed=False,
            )
            session.add(raw_msg)
            await session.commit()

            log.info(
                "message_stored",
                workspace_id=str(workspace.id),
                channel_id=channel_id,
                message_id=str(raw_msg.id),
            )

            arq_pool = request.app.state.arq_pool
            await arq_pool.enqueue_job("process_message", str(raw_msg.id))

    return Response(status_code=200)
