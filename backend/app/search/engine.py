import uuid

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import generate_query_embedding

log = structlog.get_logger()

HYBRID_SEARCH_SQL = text("""\
WITH vector_results AS (
    SELECT
        id,
        title,
        summary,
        rationale,
        owner_name,
        owner_slack_id,
        tags,
        impact_area,
        category,
        source_url,
        source_channel_name,
        created_at,
        decision_made_at,
        (1 - (embedding <=> :query_embedding::vector)) AS vector_score
    FROM decisions
    WHERE workspace_id = :workspace_id
      AND status = 'active'
      AND embedding IS NOT NULL
    ORDER BY embedding <=> :query_embedding::vector
    LIMIT 20
),
keyword_results AS (
    SELECT
        id,
        title,
        summary,
        rationale,
        owner_name,
        owner_slack_id,
        tags,
        impact_area,
        category,
        source_url,
        source_channel_name,
        created_at,
        decision_made_at,
        ts_rank(search_vector, plainto_tsquery('english', :query)) AS keyword_score
    FROM decisions
    WHERE workspace_id = :workspace_id
      AND status = 'active'
      AND search_vector @@ plainto_tsquery('english', :query)
    ORDER BY ts_rank(search_vector, plainto_tsquery('english', :query)) DESC
    LIMIT 20
),
combined AS (
    SELECT
        COALESCE(v.id, k.id) AS id,
        COALESCE(v.title, k.title) AS title,
        COALESCE(v.summary, k.summary) AS summary,
        COALESCE(v.rationale, k.rationale) AS rationale,
        COALESCE(v.owner_name, k.owner_name) AS owner_name,
        COALESCE(v.owner_slack_id, k.owner_slack_id) AS owner_slack_id,
        COALESCE(v.tags, k.tags) AS tags,
        COALESCE(v.impact_area, k.impact_area) AS impact_area,
        COALESCE(v.category, k.category) AS category,
        COALESCE(v.source_url, k.source_url) AS source_url,
        COALESCE(v.source_channel_name, k.source_channel_name) AS source_channel_name,
        COALESCE(v.created_at, k.created_at) AS created_at,
        COALESCE(v.decision_made_at, k.decision_made_at) AS decision_made_at,
        COALESCE(v.vector_score, 0.0) AS vector_score,
        COALESCE(k.keyword_score, 0.0) AS keyword_score,
        CASE WHEN v.tags && :query_tags::varchar[] THEN 1.0 ELSE 0.0 END AS tag_bonus
    FROM vector_results v
    FULL OUTER JOIN keyword_results k ON v.id = k.id
)
SELECT
    id, title, summary, rationale, owner_name, owner_slack_id,
    tags, impact_area, category, source_url, source_channel_name,
    created_at, decision_made_at,
    (0.6 * vector_score + 0.3 * keyword_score + 0.1 * tag_bonus) AS combined_score
FROM combined
WHERE 1=1
  AND (:date_from::timestamptz IS NULL OR created_at >= :date_from::timestamptz)
  AND (:date_to::timestamptz IS NULL OR created_at <= :date_to::timestamptz)
  AND (:owner_filter::varchar IS NULL OR owner_slack_id = :owner_filter::varchar)
  AND (:categories::varchar[] IS NULL OR category = ANY(:categories::varchar[]))
  AND (:filter_tags::varchar[] IS NULL OR tags && :filter_tags::varchar[])
ORDER BY combined_score DESC
LIMIT :result_limit
""")


async def hybrid_search(
    db_session: AsyncSession,
    workspace_id: str,
    query: str,
    filters: dict | None = None,
    limit: int = 5,
) -> list[dict]:
    filters = filters or {}

    embedding = await generate_query_embedding(query)
    if not embedding:
        log.warning("empty_query_embedding", query=query[:50])
        return []

    query_tags = [t.strip().lower() for t in query.split() if len(t.strip()) > 2]

    params = {
        "query_embedding": str(embedding),
        "workspace_id": workspace_id,
        "query": query,
        "query_tags": query_tags or [],
        "date_from": filters.get("date_from"),
        "date_to": filters.get("date_to"),
        "owner_filter": filters.get("owner_slack_id"),
        "categories": filters.get("categories"),
        "filter_tags": filters.get("tags"),
        "result_limit": limit,
    }

    result = await db_session.execute(HYBRID_SEARCH_SQL, params)
    rows = result.mappings().all()

    return [
        {
            "id": str(row["id"]),
            "title": row["title"],
            "summary": row["summary"],
            "rationale": row["rationale"],
            "owner_name": row["owner_name"],
            "tags": row["tags"],
            "source_url": row["source_url"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "combined_score": float(row["combined_score"]),
        }
        for row in rows
    ]
