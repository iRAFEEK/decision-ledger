import time
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.synthesizer import synthesize_answer
from app.db.models import DecisionLink, QueryLog
from app.search.engine import hybrid_search

log = structlog.get_logger()


async def handle_decision_query(
    db_session: AsyncSession,
    workspace_id: str,
    query_text: str,
    user_slack_id: str,
    source: str = "slack",
) -> dict:
    start = time.monotonic()

    results = await hybrid_search(db_session, workspace_id, query_text)

    for result in results:
        links = (
            await db_session.execute(
                select(DecisionLink).where(
                    DecisionLink.decision_id == uuid.UUID(result["id"])
                )
            )
        ).scalars().all()

        result["referenced_tickets"] = []
        result["referenced_prs"] = []
        result["referenced_urls"] = []
        for link in links:
            if link.link_type == "jira":
                result["referenced_tickets"].append(link.link_title or link.link_url)
            elif link.link_type == "github_pr":
                result["referenced_prs"].append(link.link_title or link.link_url)
            else:
                result["referenced_urls"].append(link.link_url)

    answer = await synthesize_answer(query_text, results)

    elapsed_ms = int((time.monotonic() - start) * 1000)

    query_log = QueryLog(
        id=uuid.uuid4(),
        workspace_id=uuid.UUID(workspace_id),
        user_slack_id=user_slack_id,
        query_text=query_text,
        results_count=len(results),
        response_time_ms=elapsed_ms,
        source=source,
    )
    db_session.add(query_log)
    await db_session.commit()

    log.info(
        "query_handled",
        workspace_id=workspace_id,
        results=len(results),
        elapsed_ms=elapsed_ms,
    )

    return {
        "answer": answer,
        "decisions": results,
        "response_time_ms": elapsed_ms,
    }
