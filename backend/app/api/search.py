import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import SearchRequest, SearchResponse, SearchResultDecision
from app.auth.middleware import get_current_user
from app.db.session import get_db
from app.search.query_handler import handle_decision_query

router = APIRouter()


@router.post("/search", response_model=SearchResponse)
async def search_decisions(
    body: SearchRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    workspace_id = user["workspace_id"]

    filters = {}
    if body.filters:
        filters = body.filters.model_dump(exclude_none=True)

    result = await handle_decision_query(
        db, workspace_id, body.query, user["slack_user_id"], source="api"
    )

    decisions = [SearchResultDecision(**d) for d in result["decisions"]]

    return SearchResponse(
        answer=result["answer"],
        decisions=decisions,
        total_count=len(decisions),
        response_time_ms=result["response_time_ms"],
    )
