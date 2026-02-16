import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AnalyticsOverview, CategoryCount, TopOwner
from app.auth.middleware import get_current_user
from app.db.models import Decision, QueryLog
from app.db.session import get_db

router = APIRouter()


@router.get("/analytics/overview", response_model=AnalyticsOverview)
async def analytics_overview(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace_id = uuid.UUID(user["workspace_id"])
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    # Total active decisions
    total_decisions = (
        await db.execute(
            select(func.count(Decision.id)).where(
                Decision.workspace_id == workspace_id,
                Decision.status == "active",
            )
        )
    ).scalar_one()

    # Decisions this week
    decisions_this_week = (
        await db.execute(
            select(func.count(Decision.id)).where(
                Decision.workspace_id == workspace_id,
                Decision.created_at >= week_ago,
            )
        )
    ).scalar_one()

    # Queries this week
    queries_this_week = (
        await db.execute(
            select(func.count(QueryLog.id)).where(
                QueryLog.workspace_id == workspace_id,
                QueryLog.created_at >= week_ago,
            )
        )
    ).scalar_one()

    # Confirmation rate
    confirmed_count = (
        await db.execute(
            select(func.count(Decision.id)).where(
                Decision.workspace_id == workspace_id,
                Decision.status == "active",
            )
        )
    ).scalar_one()

    ignored_count = (
        await db.execute(
            select(func.count(Decision.id)).where(
                Decision.workspace_id == workspace_id,
                Decision.status == "ignored",
            )
        )
    ).scalar_one()

    total_reviewed = confirmed_count + ignored_count
    confirmation_rate = confirmed_count / total_reviewed if total_reviewed > 0 else 0.0

    # Top owners
    top_owners_rows = (
        await db.execute(
            select(
                Decision.owner_name,
                Decision.owner_slack_id,
                func.count(Decision.id).label("count"),
            )
            .where(
                Decision.workspace_id == workspace_id,
                Decision.status == "active",
            )
            .group_by(Decision.owner_name, Decision.owner_slack_id)
            .order_by(func.count(Decision.id).desc())
            .limit(5)
        )
    ).all()

    top_owners = [
        TopOwner(owner_name=r[0], owner_slack_id=r[1], count=r[2])
        for r in top_owners_rows
    ]

    # Decisions by category
    category_rows = (
        await db.execute(
            select(
                Decision.category,
                func.count(Decision.id).label("count"),
            )
            .where(
                Decision.workspace_id == workspace_id,
                Decision.status == "active",
            )
            .group_by(Decision.category)
            .order_by(func.count(Decision.id).desc())
        )
    ).all()

    decisions_by_category = [
        CategoryCount(category=r[0], count=r[1]) for r in category_rows
    ]

    return AnalyticsOverview(
        total_decisions=total_decisions,
        decisions_this_week=decisions_this_week,
        queries_this_week=queries_this_week,
        confirmation_rate=round(confirmation_rate, 3),
        top_owners=top_owners,
        decisions_by_category=decisions_by_category,
    )
