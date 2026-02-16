import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas import (
    DecisionDetailOut,
    DecisionOut,
    DecisionUpdateIn,
    PaginatedDecisions,
)
from app.auth.middleware import get_current_user
from app.db.models import Decision, DecisionLink
from app.db.session import get_db

router = APIRouter()


@router.get("/decisions", response_model=PaginatedDecisions)
async def list_decisions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = None,
    category: str | None = None,
    owner_slack_id: str | None = None,
    tag: str | None = None,
    channel_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace_id = uuid.UUID(user["workspace_id"])
    q = select(Decision).where(
        Decision.workspace_id == workspace_id,
        Decision.status != "deleted",
    )

    if status:
        q = q.where(Decision.status == status)
    if category:
        q = q.where(Decision.category == category)
    if owner_slack_id:
        q = q.where(Decision.owner_slack_id == owner_slack_id)
    if tag:
        q = q.where(Decision.tags.any(tag))
    if channel_id:
        q = q.where(Decision.source_channel_id == channel_id)
    if date_from:
        q = q.where(Decision.created_at >= date_from)
    if date_to:
        q = q.where(Decision.created_at <= date_to)

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    q = q.order_by(Decision.created_at.desc())
    q = q.offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(q)).scalars().all()

    return PaginatedDecisions(
        items=[DecisionOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/decisions/{decision_id}", response_model=DecisionDetailOut)
async def get_decision(
    decision_id: uuid.UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace_id = uuid.UUID(user["workspace_id"])
    decision = (
        await db.execute(
            select(Decision)
            .options(selectinload(Decision.links))
            .where(Decision.id == decision_id, Decision.workspace_id == workspace_id)
        )
    ).scalar_one_or_none()

    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return DecisionDetailOut.model_validate(decision)


@router.patch("/decisions/{decision_id}", response_model=DecisionOut)
async def update_decision(
    decision_id: uuid.UUID,
    body: DecisionUpdateIn,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace_id = uuid.UUID(user["workspace_id"])
    decision = (
        await db.execute(
            select(Decision).where(
                Decision.id == decision_id, Decision.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()

    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(decision, field, value)

    await db.commit()
    await db.refresh(decision)
    return DecisionOut.model_validate(decision)


@router.delete("/decisions/{decision_id}", status_code=204)
async def delete_decision(
    decision_id: uuid.UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace_id = uuid.UUID(user["workspace_id"])
    decision = (
        await db.execute(
            select(Decision).where(
                Decision.id == decision_id, Decision.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()

    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")

    decision.status = "deleted"
    await db.commit()


@router.post("/decisions/{decision_id}/confirm", response_model=DecisionOut)
async def confirm_decision(
    decision_id: uuid.UUID,
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace_id = uuid.UUID(user["workspace_id"])
    decision = (
        await db.execute(
            select(Decision).where(
                Decision.id == decision_id, Decision.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()

    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")

    decision.status = "active"
    decision.confirmed_at = datetime.now(timezone.utc)
    decision.confirmed_by = user["slack_user_id"]
    await db.commit()
    await db.refresh(decision)

    arq_pool = request.app.state.arq_pool
    await arq_pool.enqueue_job("enrich_decision", str(decision.id))
    await arq_pool.enqueue_job("generate_embedding_task", str(decision.id))

    return DecisionOut.model_validate(decision)


@router.post("/decisions/{decision_id}/ignore", response_model=DecisionOut)
async def ignore_decision(
    decision_id: uuid.UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace_id = uuid.UUID(user["workspace_id"])
    decision = (
        await db.execute(
            select(Decision).where(
                Decision.id == decision_id, Decision.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()

    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")

    decision.status = "ignored"
    await db.commit()
    await db.refresh(decision)
    return DecisionOut.model_validate(decision)
