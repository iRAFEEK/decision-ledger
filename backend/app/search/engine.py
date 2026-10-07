from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import generate_query_embedding


@dataclass
class SearchPage:
    decisions: list[dict]
    total_count: int


# Filter first. Count the same candidate set on every page, including empty pages.
# A missing query vector leaves keyword/tag retrieval fully operational.
SEARCH_SQL = text("""
WITH filtered AS (
    SELECT * FROM decisions
    WHERE workspace_id = CAST(:workspace_id AS uuid)
      AND status = :status AND status <> 'deleted'
      AND (CAST(:date_from AS timestamptz) IS NULL OR created_at >= CAST(:date_from AS timestamptz))
      AND (CAST(:date_to AS timestamptz) IS NULL OR created_at <= CAST(:date_to AS timestamptz))
      AND (CAST(:owner_filter AS varchar) IS NULL OR owner_slack_id = :owner_filter)
      AND (CAST(:categories AS varchar[]) IS NULL OR category = ANY(CAST(:categories AS varchar[])))
      AND (CAST(:filter_tags AS varchar[]) IS NULL OR tags && CAST(:filter_tags AS varchar[]))
), ranked AS (
    SELECT id, title, summary, rationale, owner_name, tags, source_url,
           created_at, decision_made_at,
           0.6 * COALESCE(1 - (embedding <=> CAST(:query_embedding AS vector)), 0)
           + 0.3 * ts_rank(search_vector, plainto_tsquery('english', :query))
           + 0.1 * CASE WHEN tags && CAST(:query_tags AS varchar[]) THEN 1 ELSE 0 END AS combined_score
    FROM filtered
    WHERE (CAST(:query_embedding AS vector) IS NOT NULL AND embedding IS NOT NULL)
       OR search_vector @@ plainto_tsquery('english', :query)
       OR tags && CAST(:query_tags AS varchar[])
), page AS (
    SELECT * FROM ranked
    ORDER BY combined_score DESC, created_at DESC, id
    LIMIT :result_limit OFFSET :result_offset
)
SELECT page.*, totals.total_count
FROM (SELECT count(*) AS total_count FROM ranked) totals
LEFT JOIN page ON TRUE
ORDER BY page.combined_score DESC, page.created_at DESC, page.id
""")


async def hybrid_search(
    db_session: AsyncSession,
    workspace_id: str,
    query: str,
    filters: dict | None = None,
    limit: int = 5,
    offset: int = 0,
) -> SearchPage:
    filters = filters or {}
    embedding = await generate_query_embedding(query)
    params = {
        "query_embedding": str(embedding) if embedding else None,
        "workspace_id": workspace_id,
        "query": query,
        "query_tags": [t.strip().lower() for t in query.split() if len(t.strip()) > 2],
        "date_from": filters.get("date_from"),
        "date_to": filters.get("date_to"),
        "owner_filter": filters.get("owner_slack_id"),
        "categories": filters.get("categories"),
        "filter_tags": filters.get("tags"),
        "status": filters.get("status") or "active",
        "result_limit": limit,
        "result_offset": offset,
    }
    result = await db_session.execute(SEARCH_SQL, params)
    rows = result.mappings().all()
    decisions = []
    for row in rows:
        if row["id"] is None:
            continue
        decisions.append({
            "id": str(row["id"]),
            "title": row["title"],
            "summary": row["summary"],
            "rationale": row["rationale"],
            "owner_name": row["owner_name"],
            "tags": row["tags"],
            "source_url": row["source_url"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "decision_made_at": row["decision_made_at"].isoformat() if row["decision_made_at"] else None,
            "combined_score": float(row["combined_score"]),
        })
    return SearchPage(decisions, int(rows[0]["total_count"]) if rows else 0)
