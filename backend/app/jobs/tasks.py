import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import structlog
from sqlalchemy import func, select

from app.ai.detector import detect_decision
from app.ai.embeddings import generate_embedding
from app.ai.extractor import extract_decision
from app.db.models import (
    Decision,
    DecisionLink,
    MonitoredChannel,
    PendingConfirmation,
    RawMessage,
    Workspace,
)
from app.db.session import async_session_factory
from app.integrations.github.client import GitHubClient
from app.integrations.github.references import extract_github_references
from app.integrations.jira.client import JiraClient
from app.integrations.jira.references import extract_jira_references
from app.search.query_handler import handle_decision_query
from app.slack import client as slack_client
from app.slack.messages import build_confirmation_blocks, build_search_result_blocks

log = structlog.get_logger()

MAX_DAILY_DETECTIONS = 5


async def process_message(ctx: dict, message_id: str) -> None:
    async with async_session_factory() as session:
        raw_msg = (
            await session.execute(
                select(RawMessage).where(RawMessage.id == uuid.UUID(message_id))
            )
        ).scalar_one_or_none()

        if raw_msg is None or raw_msg.processed:
            return

        workspace = (
            await session.execute(
                select(Workspace).where(Workspace.id == raw_msg.workspace_id)
            )
        ).scalar_one_or_none()

        if workspace is None or not workspace.bot_access_token:
            raw_msg.processed = True
            await session.commit()
            return

        monitored = (
            await session.execute(
                select(MonitoredChannel).where(
                    MonitoredChannel.workspace_id == workspace.id,
                    MonitoredChannel.channel_id == raw_msg.channel_id,
                    MonitoredChannel.enabled.is_(True),
                )
            )
        ).scalar_one_or_none()

        if monitored is None:
            raw_msg.processed = True
            await session.commit()
            return

        # Fetch thread context
        thread_ts = raw_msg.thread_ts or raw_msg.message_ts
        thread_resp = await slack_client.conversations_replies(
            workspace.bot_access_token, raw_msg.channel_id, thread_ts, limit=50
        )
        thread_messages = thread_resp.get("messages", [])
        if not thread_messages:
            thread_messages = [{"text": raw_msg.text or "", "user": raw_msg.user_slack_id, "ts": raw_msg.message_ts}]

        formatted = [
            {
                "user_slack_id": m.get("user", ""),
                "user_name": m.get("user", ""),
                "text": m.get("text", ""),
                "message_ts": m.get("ts", ""),
            }
            for m in thread_messages
        ]

        detection = await detect_decision(formatted)

        if detection["confidence"] < 0.7:
            raw_msg.processed = True
            await session.commit()
            log.info("message_below_threshold", message_id=message_id, confidence=detection["confidence"])
            return

        # Check daily detection count
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_count = (
            await session.execute(
                select(func.count(Decision.id)).where(
                    Decision.workspace_id == workspace.id,
                    Decision.created_at >= today_start,
                )
            )
        ).scalar_one()

        if daily_count >= MAX_DAILY_DETECTIONS:
            raw_msg.processed = True
            await session.commit()
            log.warning("daily_detection_limit", workspace_id=str(workspace.id), count=daily_count)
            return

        extraction = await extract_decision(formatted)

        decision = Decision(
            id=uuid.uuid4(),
            workspace_id=workspace.id,
            title=extraction["title"],
            summary=extraction["summary"],
            rationale=extraction["rationale"],
            owner_slack_id=extraction["owner_slack_id"],
            owner_name=extraction["owner_name"],
            source_type="slack_thread",
            source_channel_id=raw_msg.channel_id,
            source_channel_name=monitored.channel_name,
            source_thread_ts=thread_ts,
            tags=extraction["tags"],
            impact_area=extraction["impact_area"],
            category=extraction["category"],
            confidence=detection["confidence"],
            status="pending",
            raw_context={"messages": [m.get("text", "") for m in thread_messages]},
            decision_made_at=datetime.now(timezone.utc),
        )
        session.add(decision)
        await session.flush()

        confirmation = PendingConfirmation(
            id=uuid.uuid4(),
            workspace_id=workspace.id,
            decision_id=decision.id,
            slack_channel_id=raw_msg.channel_id,
            target_user_slack_id=extraction["owner_slack_id"],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
            status="pending",
        )
        session.add(confirmation)

        blocks = build_confirmation_blocks(decision)
        post_resp = await slack_client.post_message(
            workspace.bot_access_token,
            raw_msg.channel_id,
            text=f"Decision detected: {decision.title}",
            blocks=blocks,
        )

        if post_resp.get("ok"):
            confirmation.slack_message_ts = post_resp.get("ts")

        raw_msg.processed = True
        raw_msg.decision_id = decision.id
        await session.commit()

        log.info(
            "decision_created",
            decision_id=str(decision.id),
            title=decision.title,
            confidence=detection["confidence"],
        )


async def process_query(
    ctx: dict,
    workspace_id: str,
    query_text: str,
    user_slack_id: str,
    response_url: str,
) -> None:
    async with async_session_factory() as session:
        result = await handle_decision_query(
            session, workspace_id, query_text, user_slack_id, source="slack"
        )

    blocks = build_search_result_blocks(result["answer"], result["decisions"])

    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            response_url,
            json={
                "response_type": "ephemeral",
                "text": result["answer"],
                "blocks": blocks,
            },
        )


async def enrich_decision(ctx: dict, decision_id: str) -> None:
    async with async_session_factory() as session:
        decision = (
            await session.execute(
                select(Decision).where(Decision.id == uuid.UUID(decision_id))
            )
        ).scalar_one_or_none()

        if decision is None:
            return

        workspace = (
            await session.execute(
                select(Workspace).where(Workspace.id == decision.workspace_id)
            )
        ).scalar_one_or_none()

        combined_text = " ".join(
            filter(None, [decision.summary, decision.rationale])
        )
        if decision.raw_context and isinstance(decision.raw_context, dict):
            for msg_text in decision.raw_context.get("messages", []):
                combined_text += " " + msg_text

        # Jira enrichment
        jira_refs = extract_jira_references(combined_text)
        if jira_refs and workspace and workspace.jira_domain and workspace.jira_email and workspace.jira_api_token:
            jira = JiraClient(workspace.jira_domain, workspace.jira_email, workspace.jira_api_token)
            for ref in jira_refs:
                issue = await jira.get_issue(ref)
                if issue:
                    link = DecisionLink(
                        id=uuid.uuid4(),
                        decision_id=decision.id,
                        link_type="jira",
                        link_url=issue["url"],
                        link_title=f"{issue['key']}: {issue['title']}",
                        link_metadata=issue,
                    )
                    session.add(link)

        # GitHub enrichment
        gh_refs = extract_github_references(combined_text)
        if gh_refs and workspace and workspace.github_token:
            gh = GitHubClient(workspace.github_token)
            owner = workspace.github_org
            repo = workspace.github_repo
            for ref in gh_refs:
                ref_owner = ref.get("owner") or owner
                ref_repo = ref.get("repo") or repo
                if not ref_owner or not ref_repo:
                    continue
                pr = await gh.get_pull_request(ref_owner, ref_repo, ref["number"])
                if pr:
                    link = DecisionLink(
                        id=uuid.uuid4(),
                        decision_id=decision.id,
                        link_type="github_pr",
                        link_url=pr["url"],
                        link_title=f"#{pr['number']}: {pr['title']}",
                        link_metadata=pr,
                    )
                    session.add(link)

        await session.commit()
        log.info("decision_enriched", decision_id=decision_id)


async def generate_embedding_task(ctx: dict, decision_id: str) -> None:
    async with async_session_factory() as session:
        decision = (
            await session.execute(
                select(Decision).where(Decision.id == uuid.UUID(decision_id))
            )
        ).scalar_one_or_none()

        if decision is None:
            return

        text = " ".join(
            filter(None, [decision.title, decision.summary, decision.rationale])
        )
        if not text.strip():
            return

        embedding = await generate_embedding(text)
        if not embedding:
            log.warning("empty_embedding", decision_id=decision_id)
            return

        decision.embedding = embedding
        await session.commit()
        log.info("embedding_generated", decision_id=decision_id)


async def expire_confirmations(ctx: dict) -> None:
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        pending = (
            await session.execute(
                select(PendingConfirmation).where(
                    PendingConfirmation.expires_at < now,
                    PendingConfirmation.status == "pending",
                )
            )
        ).scalars().all()

        for conf in pending:
            conf.status = "expired"
            decision = (
                await session.execute(
                    select(Decision).where(Decision.id == conf.decision_id)
                )
            ).scalar_one_or_none()
            if decision and decision.status == "pending":
                decision.status = "expired"

        await session.commit()
        if pending:
            log.info("confirmations_expired", count=len(pending))


async def backfill_history(ctx: dict, workspace_id: str, days: int = 90) -> None:
    async with async_session_factory() as session:
        workspace = (
            await session.execute(
                select(Workspace).where(Workspace.id == uuid.UUID(workspace_id))
            )
        ).scalar_one_or_none()

        if workspace is None or not workspace.bot_access_token:
            return

        workspace.backfill_status = "in_progress"
        await session.commit()

        channels = (
            await session.execute(
                select(MonitoredChannel).where(
                    MonitoredChannel.workspace_id == workspace.id,
                    MonitoredChannel.enabled.is_(True),
                )
            )
        ).scalars().all()

        oldest = str((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

        for channel in channels:
            cursor = None
            while True:
                resp = await slack_client.conversations_history(
                    workspace.bot_access_token,
                    channel.channel_id,
                    oldest=oldest,
                    limit=200,
                    cursor=cursor,
                )
                messages = resp.get("messages", [])

                for msg in messages:
                    if msg.get("bot_id") or msg.get("subtype"):
                        continue

                    thread_ts = msg.get("thread_ts") or msg.get("ts")
                    thread_messages = [msg]

                    if msg.get("reply_count", 0) > 0:
                        await asyncio.sleep(1)
                        thread_resp = await slack_client.conversations_replies(
                            workspace.bot_access_token,
                            channel.channel_id,
                            thread_ts,
                            limit=50,
                        )
                        thread_messages = thread_resp.get("messages", [msg])

                    formatted = [
                        {
                            "user_slack_id": m.get("user", ""),
                            "user_name": m.get("user", ""),
                            "text": m.get("text", ""),
                            "message_ts": m.get("ts", ""),
                        }
                        for m in thread_messages
                    ]

                    detection = await detect_decision(formatted)
                    if detection["confidence"] < 0.7:
                        continue

                    extraction = await extract_decision(formatted)

                    decision = Decision(
                        id=uuid.uuid4(),
                        workspace_id=workspace.id,
                        title=extraction["title"],
                        summary=extraction["summary"],
                        rationale=extraction["rationale"],
                        owner_slack_id=extraction["owner_slack_id"],
                        owner_name=extraction["owner_name"],
                        source_type="backfill",
                        source_channel_id=channel.channel_id,
                        source_channel_name=channel.channel_name,
                        source_thread_ts=thread_ts,
                        tags=extraction["tags"],
                        impact_area=extraction["impact_area"],
                        category=extraction["category"],
                        confidence=detection["confidence"],
                        status="active",
                        raw_context={"messages": [m.get("text", "") for m in thread_messages]},
                        decision_made_at=datetime.now(timezone.utc),
                    )
                    session.add(decision)
                    await session.flush()

                    embedding_text = " ".join(
                        filter(None, [decision.title, decision.summary, decision.rationale])
                    )
                    emb = await generate_embedding(embedding_text)
                    if emb:
                        decision.embedding = emb

                    await session.commit()
                    await asyncio.sleep(1)

                metadata = resp.get("response_metadata", {})
                cursor = metadata.get("next_cursor")
                if not cursor:
                    break
                await asyncio.sleep(1)

        workspace.backfill_status = "complete"
        await session.commit()
        log.info("backfill_complete", workspace_id=workspace_id)
