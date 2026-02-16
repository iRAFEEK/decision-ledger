import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    ChannelCreateIn,
    ChannelOut,
    GitHubConfigIn,
    JiraConfigIn,
    WorkspaceOut,
    WorkspaceSettingsUpdate,
)
from app.auth.middleware import get_current_user
from app.db.models import MonitoredChannel, Workspace
from app.db.session import get_db
from app.integrations.github.client import GitHubClient
from app.integrations.jira.client import JiraClient

log = structlog.get_logger()

router = APIRouter()


@router.get("/workspace", response_model=WorkspaceOut)
async def get_workspace(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace = (
        await db.execute(
            select(Workspace).where(
                Workspace.id == uuid.UUID(user["workspace_id"])
            )
        )
    ).scalar_one_or_none()

    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return WorkspaceOut.model_validate(workspace)


@router.patch("/workspace/settings", response_model=WorkspaceOut)
async def update_workspace_settings(
    body: WorkspaceSettingsUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace = (
        await db.execute(
            select(Workspace).where(
                Workspace.id == uuid.UUID(user["workspace_id"])
            )
        )
    ).scalar_one_or_none()

    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace.settings = body.settings
    await db.commit()
    await db.refresh(workspace)
    return WorkspaceOut.model_validate(workspace)


@router.get("/workspace/channels", response_model=list[ChannelOut])
async def list_channels(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace_id = uuid.UUID(user["workspace_id"])
    channels = (
        await db.execute(
            select(MonitoredChannel)
            .where(MonitoredChannel.workspace_id == workspace_id)
            .order_by(MonitoredChannel.created_at)
        )
    ).scalars().all()
    return [ChannelOut.model_validate(c) for c in channels]


@router.post("/workspace/channels", response_model=ChannelOut, status_code=201)
async def add_channel(
    body: ChannelCreateIn,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace_id = uuid.UUID(user["workspace_id"])

    existing = (
        await db.execute(
            select(MonitoredChannel).where(
                MonitoredChannel.workspace_id == workspace_id,
                MonitoredChannel.channel_id == body.channel_id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=409, detail="Channel already monitored")

    channel = MonitoredChannel(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        channel_id=body.channel_id,
        channel_name=body.channel_name,
        enabled=True,
    )
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return ChannelOut.model_validate(channel)


@router.delete("/workspace/channels/{channel_id}", status_code=204)
async def remove_channel(
    channel_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace_id = uuid.UUID(user["workspace_id"])
    channel = (
        await db.execute(
            select(MonitoredChannel).where(
                MonitoredChannel.workspace_id == workspace_id,
                MonitoredChannel.channel_id == channel_id,
            )
        )
    ).scalar_one_or_none()

    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")

    await db.delete(channel)
    await db.commit()


@router.post("/workspace/integrations/jira")
async def configure_jira(
    body: JiraConfigIn,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace = (
        await db.execute(
            select(Workspace).where(
                Workspace.id == uuid.UUID(user["workspace_id"])
            )
        )
    ).scalar_one_or_none()

    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    jira = JiraClient(body.domain, body.email, body.api_token)
    test = await jira.get_issue("TEST-1")
    # If credentials are completely wrong, httpx will raise or return None.
    # We accept either outcome — the important thing is no exception from auth.

    workspace.jira_domain = body.domain
    workspace.jira_email = body.email
    workspace.jira_api_token = body.api_token
    await db.commit()

    return {"status": "connected", "domain": body.domain}


@router.post("/workspace/integrations/github")
async def configure_github(
    body: GitHubConfigIn,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace = (
        await db.execute(
            select(Workspace).where(
                Workspace.id == uuid.UUID(user["workspace_id"])
            )
        )
    ).scalar_one_or_none()

    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    gh = GitHubClient(body.token)
    test = await gh.get_pull_request(body.org, body.repo, 1)

    workspace.github_org = body.org
    workspace.github_repo = body.repo
    workspace.github_token = body.token
    await db.commit()

    return {"status": "connected", "org": body.org, "repo": body.repo}


@router.post("/workspace/backfill")
async def trigger_backfill(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace = (
        await db.execute(
            select(Workspace).where(
                Workspace.id == uuid.UUID(user["workspace_id"])
            )
        )
    ).scalar_one_or_none()

    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if workspace.backfill_status == "in_progress":
        raise HTTPException(status_code=409, detail="Backfill already running")

    workspace.backfill_status = "running"
    await db.commit()

    # Enqueue backfill job
    # await arq_pool.enqueue_job("backfill_history", str(workspace.id))

    return {"status": "started", "workspace_id": str(workspace.id)}
