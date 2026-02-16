#!/usr/bin/env python3
"""Seed the database with demo data for local development."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5499/decision_ledger"

engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

now = datetime.now(timezone.utc)


def days_ago(n: int) -> datetime:
    return now - timedelta(days=n)


async def seed():
    async with async_session() as db:
        # Check if demo data already exists
        result = await db.execute(
            text("SELECT id FROM workspaces WHERE slack_team_id = 'T_DEMO'")
        )
        if result.scalar():
            print("Demo data already exists. Clearing and re-seeding...")
            await db.execute(text(
                "DELETE FROM workspaces WHERE slack_team_id = 'T_DEMO'"
            ))
            await db.commit()

        # 1. Workspace
        ws_id = uuid.uuid4()
        await db.execute(
            text("""
                INSERT INTO workspaces (id, slack_team_id, team_name, bot_access_token, onboarding_complete)
                VALUES (:id, :team_id, :name, :token, true)
            """),
            {"id": ws_id, "team_id": "T_DEMO", "name": "Demo Team", "token": "xoxb-demo"},
        )

        # 2. Monitored channels
        ch_general_id = uuid.uuid4()
        ch_eng_id = uuid.uuid4()
        for ch_id, ch_slack_id, ch_name in [
            (ch_general_id, "C_GENERAL", "general"),
            (ch_eng_id, "C_ENGINEERING", "engineering"),
        ]:
            await db.execute(
                text("""
                    INSERT INTO monitored_channels (id, workspace_id, channel_id, channel_name, enabled)
                    VALUES (:id, :ws_id, :ch_id, :name, true)
                """),
                {"id": ch_id, "ws_id": ws_id, "ch_id": ch_slack_id, "name": ch_name},
            )

        # 3. Decisions
        decisions = [
            {
                "id": uuid.uuid4(),
                "title": "Adopt PostgreSQL for event store",
                "summary": "We will use PostgreSQL with pgvector as our primary event store instead of a dedicated event-sourcing database. This gives us vector search capabilities alongside relational queries.",
                "rationale": "The team evaluated DynamoDB, EventStoreDB, and PostgreSQL. PostgreSQL won because we already have operational expertise, pgvector covers our embedding search needs, and it reduces infrastructure complexity.",
                "owner_slack_id": "U_ALICE",
                "owner_name": "Alice Chen",
                "category": "infrastructure",
                "tags": ["database", "postgresql", "event-sourcing"],
                "impact_area": ["backend", "data-pipeline"],
                "status": "active",
                "confidence": 0.95,
                "channel_id": "C_ENGINEERING",
                "channel_name": "engineering",
                "confirmed_at": days_ago(25),
                "confirmed_by": "U_BOB",
                "created_at": days_ago(28),
            },
            {
                "id": uuid.uuid4(),
                "title": "Use JWT for API authentication",
                "summary": "All API endpoints will use JWT tokens for authentication. Tokens are issued after Slack OAuth and stored as httpOnly cookies.",
                "rationale": "JWT allows stateless auth which simplifies horizontal scaling. The Slack OAuth flow naturally provides user identity, so we encode workspace_id and user_id in the token payload.",
                "owner_slack_id": "U_BOB",
                "owner_name": "Bob Martinez",
                "category": "security",
                "tags": ["auth", "jwt", "security"],
                "impact_area": ["backend", "frontend"],
                "status": "active",
                "confidence": 0.97,
                "channel_id": "C_ENGINEERING",
                "channel_name": "engineering",
                "confirmed_at": days_ago(24),
                "confirmed_by": "U_ALICE",
                "created_at": days_ago(26),
            },
            {
                "id": uuid.uuid4(),
                "title": "Migrate from REST to GraphQL for mobile clients",
                "summary": "Mobile clients will use a GraphQL API to reduce over-fetching and minimize network requests. The web frontend will continue using REST.",
                "rationale": "Mobile clients fetch deeply nested data (decisions with links and threads) in single views. GraphQL lets them request exactly what they need. REST stays for the web dashboard since it's simpler and our endpoints already match the UI.",
                "owner_slack_id": "U_CAROL",
                "owner_name": "Carol Park",
                "category": "api",
                "tags": ["graphql", "mobile", "api-design"],
                "impact_area": ["backend", "mobile"],
                "status": "pending",
                "confidence": 0.82,
                "channel_id": "C_ENGINEERING",
                "channel_name": "engineering",
                "confirmed_at": None,
                "confirmed_by": None,
                "created_at": days_ago(20),
            },
            {
                "id": uuid.uuid4(),
                "title": "Deprecate v1 API by end of Q2",
                "summary": "The v1 REST API will be deprecated on June 30th and removed by September 30th. All clients must migrate to v2 endpoints.",
                "rationale": "v1 has accumulated significant tech debt with inconsistent response formats and no pagination. Maintaining both versions doubles our testing burden. Three months gives all integrators time to migrate.",
                "owner_slack_id": "U_ALICE",
                "owner_name": "Alice Chen",
                "category": "deprecation",
                "tags": ["api", "deprecation", "migration"],
                "impact_area": ["backend", "documentation"],
                "status": "active",
                "confidence": 0.91,
                "channel_id": "C_GENERAL",
                "channel_name": "general",
                "confirmed_at": days_ago(14),
                "confirmed_by": "U_CAROL",
                "created_at": days_ago(18),
            },
            {
                "id": uuid.uuid4(),
                "title": "Use arq for background job processing",
                "summary": "Background jobs (message processing, embedding generation, enrichment) will use arq with Redis as the broker instead of Celery.",
                "rationale": "arq is async-native, lightweight, and integrates cleanly with our asyncio codebase. Celery would require synchronous workers or complex workarounds. arq's cron support covers our scheduled tasks.",
                "owner_slack_id": "U_BOB",
                "owner_name": "Bob Martinez",
                "category": "architecture",
                "tags": ["async", "jobs", "redis", "arq"],
                "impact_area": ["backend", "infrastructure"],
                "status": "active",
                "confidence": 0.93,
                "channel_id": "C_ENGINEERING",
                "channel_name": "engineering",
                "confirmed_at": days_ago(21),
                "confirmed_by": "U_ALICE",
                "created_at": days_ago(23),
            },
            {
                "id": uuid.uuid4(),
                "title": "Adopt Tailwind CSS v4 for the frontend",
                "summary": "The Next.js frontend will use Tailwind CSS v4 for all styling. No additional CSS-in-JS libraries.",
                "rationale": "Tailwind v4 has zero-config setup with Next.js, excellent performance, and the team already has experience with it. Avoids runtime CSS-in-JS overhead.",
                "owner_slack_id": "U_DIANA",
                "owner_name": "Diana Reeves",
                "category": "tooling",
                "tags": ["frontend", "css", "tailwind"],
                "impact_area": ["frontend"],
                "status": "active",
                "confidence": 0.96,
                "channel_id": "C_ENGINEERING",
                "channel_name": "engineering",
                "confirmed_at": days_ago(19),
                "confirmed_by": "U_BOB",
                "created_at": days_ago(22),
            },
            {
                "id": uuid.uuid4(),
                "title": "Implement hybrid search with vector + full-text + tags",
                "summary": "Search will combine pgvector cosine similarity (60% weight), PostgreSQL full-text search (30% weight), and tag overlap scoring (10% weight).",
                "rationale": "Pure vector search misses exact keyword matches. Pure FTS misses semantic similarity. The hybrid approach with tuned weights gives the best results in our benchmarks across 200 test queries.",
                "owner_slack_id": "U_ALICE",
                "owner_name": "Alice Chen",
                "category": "architecture",
                "tags": ["search", "pgvector", "full-text-search"],
                "impact_area": ["backend", "search"],
                "status": "active",
                "confidence": 0.94,
                "channel_id": "C_ENGINEERING",
                "channel_name": "engineering",
                "confirmed_at": days_ago(10),
                "confirmed_by": "U_DIANA",
                "created_at": days_ago(15),
            },
            {
                "id": uuid.uuid4(),
                "title": "Use Slack Block Kit for all bot messages",
                "summary": "All messages sent by the bot will use Slack Block Kit format for rich interactive UIs, including confirm/edit/ignore action buttons.",
                "rationale": "Block Kit provides a consistent, interactive experience. Users can confirm or ignore decisions directly from Slack without switching to the web dashboard.",
                "owner_slack_id": "U_CAROL",
                "owner_name": "Carol Park",
                "category": "process",
                "tags": ["slack", "ux", "block-kit"],
                "impact_area": ["integrations", "ux"],
                "status": "active",
                "confidence": 0.88,
                "channel_id": "C_GENERAL",
                "channel_name": "general",
                "confirmed_at": days_ago(7),
                "confirmed_by": "U_ALICE",
                "created_at": days_ago(12),
            },
            {
                "id": uuid.uuid4(),
                "title": "Pin Node.js version to 20 LTS for frontend builds",
                "summary": "All CI/CD pipelines and Docker images for the frontend will use Node.js 20 LTS. No upgrading to Node 22 until it reaches LTS.",
                "rationale": "Node 20 is the current LTS with the best ecosystem compatibility. Several of our dependencies have reported issues with Node 22. We'll revisit when Node 22 reaches LTS in October.",
                "owner_slack_id": "U_BOB",
                "owner_name": "Bob Martinez",
                "category": "dependency",
                "tags": ["nodejs", "ci-cd", "versioning"],
                "impact_area": ["frontend", "ci-cd"],
                "status": "ignored",
                "confidence": 0.72,
                "channel_id": "C_GENERAL",
                "channel_name": "general",
                "confirmed_at": None,
                "confirmed_by": None,
                "created_at": days_ago(5),
            },
            {
                "id": uuid.uuid4(),
                "title": "Add structured logging with structlog",
                "summary": "All backend services will use structlog for structured JSON logging in production and colored console output in development.",
                "rationale": "Structured logs are essential for our observability stack. structlog integrates well with Python's logging, supports async, and makes it easy to add context (workspace_id, user_id) to every log line.",
                "owner_slack_id": "U_DIANA",
                "owner_name": "Diana Reeves",
                "category": "tooling",
                "tags": ["logging", "observability", "structlog"],
                "impact_area": ["backend", "devops"],
                "status": "pending",
                "confidence": 0.85,
                "channel_id": "C_ENGINEERING",
                "channel_name": "engineering",
                "confirmed_at": None,
                "confirmed_by": None,
                "created_at": days_ago(2),
            },
        ]

        decision_ids = []
        for d in decisions:
            d_id = d["id"]
            decision_ids.append(d_id)
            await db.execute(
                text("""
                    INSERT INTO decisions (
                        id, workspace_id, title, summary, rationale,
                        owner_slack_id, owner_name, category, tags, impact_area,
                        status, confidence, source_type, source_channel_id, source_channel_name,
                        confirmed_at, confirmed_by, created_at
                    ) VALUES (
                        :id, :ws_id, :title, :summary, :rationale,
                        :owner_slack_id, :owner_name, :category, :tags, :impact_area,
                        :status, :confidence, 'slack', :channel_id, :channel_name,
                        :confirmed_at, :confirmed_by, :created_at
                    )
                """),
                {
                    "id": d_id,
                    "ws_id": ws_id,
                    "title": d["title"],
                    "summary": d["summary"],
                    "rationale": d["rationale"],
                    "owner_slack_id": d["owner_slack_id"],
                    "owner_name": d["owner_name"],
                    "category": d["category"],
                    "tags": d["tags"],
                    "impact_area": d["impact_area"],
                    "status": d["status"],
                    "confidence": d["confidence"],
                    "channel_id": d["channel_id"],
                    "channel_name": d["channel_name"],
                    "confirmed_at": d["confirmed_at"],
                    "confirmed_by": d["confirmed_by"],
                    "created_at": d["created_at"],
                },
            )

        # 4. Decision links
        links = [
            # PostgreSQL decision - Jira ticket
            {
                "decision_id": decisions[0]["id"],
                "link_type": "jira",
                "link_url": "https://demo-team.atlassian.net/browse/INFRA-142",
                "link_title": "INFRA-142: Evaluate event store options",
            },
            # PostgreSQL decision - GitHub PR
            {
                "decision_id": decisions[0]["id"],
                "link_type": "github_pr",
                "link_url": "https://github.com/demo-team/backend/pull/87",
                "link_title": "PR #87: Add pgvector extension and migration",
            },
            # JWT auth decision - GitHub PR
            {
                "decision_id": decisions[1]["id"],
                "link_type": "github_pr",
                "link_url": "https://github.com/demo-team/backend/pull/91",
                "link_title": "PR #91: Implement JWT auth middleware",
            },
            # Deprecate v1 API - Jira epic
            {
                "decision_id": decisions[3]["id"],
                "link_type": "jira",
                "link_url": "https://demo-team.atlassian.net/browse/API-301",
                "link_title": "API-301: v1 API deprecation epic",
            },
            # Hybrid search - GitHub PR
            {
                "decision_id": decisions[6]["id"],
                "link_type": "github_pr",
                "link_url": "https://github.com/demo-team/backend/pull/105",
                "link_title": "PR #105: Implement hybrid search engine",
            },
            # Hybrid search - Jira
            {
                "decision_id": decisions[6]["id"],
                "link_type": "jira",
                "link_url": "https://demo-team.atlassian.net/browse/SEARCH-55",
                "link_title": "SEARCH-55: Design hybrid search ranking",
            },
        ]

        for link in links:
            await db.execute(
                text("""
                    INSERT INTO decision_links (id, decision_id, link_type, link_url, link_title)
                    VALUES (:id, :decision_id, :link_type, :link_url, :link_title)
                """),
                {"id": uuid.uuid4(), **link},
            )

        # 5. Query logs
        queries = [
            {"query": "Why did we choose PostgreSQL over DynamoDB?", "results": 3, "time_ms": 420, "source": "slack", "days": 25},
            {"query": "What's the authentication strategy?", "results": 2, "time_ms": 380, "source": "web", "days": 20},
            {"query": "When is v1 API being deprecated?", "results": 1, "time_ms": 290, "source": "slack", "days": 14},
            {"query": "How does search ranking work?", "results": 2, "time_ms": 510, "source": "web", "days": 8},
            {"query": "What background job framework are we using?", "results": 1, "time_ms": 340, "source": "slack", "days": 3},
        ]

        for q in queries:
            await db.execute(
                text("""
                    INSERT INTO query_logs (id, workspace_id, user_slack_id, query_text, results_count, response_time_ms, source, created_at)
                    VALUES (:id, :ws_id, :user_id, :query, :results, :time_ms, :source, :created_at)
                """),
                {
                    "id": uuid.uuid4(),
                    "ws_id": ws_id,
                    "user_id": "U_ALICE",
                    "query": q["query"],
                    "results": q["results"],
                    "time_ms": q["time_ms"],
                    "source": q["source"],
                    "created_at": days_ago(q["days"]),
                },
            )

        await db.commit()

        print(f"Seeded successfully!")
        print(f"  Workspace: {ws_id}")
        print(f"  Channels: 2")
        print(f"  Decisions: {len(decisions)}")
        print(f"  Decision links: {len(links)}")
        print(f"  Query logs: {len(queries)}")


if __name__ == "__main__":
    asyncio.run(seed())
