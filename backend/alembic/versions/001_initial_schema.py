"""initial schema

Revision ID: b21785dd743e
Revises:
Create Date: 2026-02-15
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "b21785dd743e"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # --- workspaces ---
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slack_team_id", sa.String, unique=True, nullable=False),
        sa.Column("team_name", sa.String, nullable=False),
        sa.Column("bot_access_token", sa.Text),
        sa.Column("user_access_token", sa.Text),
        sa.Column("settings", postgresql.JSONB),
        sa.Column("plan", sa.String),
        sa.Column("onboarding_complete", sa.Boolean, server_default="false"),
        sa.Column("backfill_status", sa.String),
        sa.Column("jira_domain", sa.String),
        sa.Column("jira_email", sa.String),
        sa.Column("jira_api_token", sa.Text),
        sa.Column("github_org", sa.String),
        sa.Column("github_repo", sa.String),
        sa.Column("github_token", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("slack_user_id", sa.String, nullable=False),
        sa.Column("display_name", sa.String),
        sa.Column("email", sa.String),
        sa.Column("avatar_url", sa.String),
        sa.Column("is_admin", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "slack_user_id", name="uq_users_workspace_slack"),
    )
    op.create_index("ix_users_workspace_id", "users", ["workspace_id"])

    # --- monitored_channels ---
    op.create_table(
        "monitored_channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("channel_id", sa.String, nullable=False),
        sa.Column("channel_name", sa.String),
        sa.Column("enabled", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "channel_id", name="uq_monitored_channels_workspace_channel"),
    )
    op.create_index("ix_monitored_channels_workspace_id", "monitored_channels", ["workspace_id"])

    # --- decisions ---
    op.create_table(
        "decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("summary", sa.Text),
        sa.Column("rationale", sa.Text),
        sa.Column("owner_slack_id", sa.String),
        sa.Column("owner_name", sa.String),
        sa.Column("source_type", sa.String),
        sa.Column("source_url", sa.Text),
        sa.Column("source_channel_id", sa.String),
        sa.Column("source_channel_name", sa.String),
        sa.Column("source_thread_ts", sa.String),
        sa.Column("tags", postgresql.ARRAY(sa.String)),
        sa.Column("impact_area", postgresql.ARRAY(sa.String)),
        sa.Column("category", sa.String),
        sa.Column("confidence", sa.Float),
        sa.Column("embedding", Vector(1024)),
        sa.Column("status", sa.String, server_default="pending"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("confirmed_by", sa.String),
        sa.Column("raw_context", postgresql.JSON),
        sa.Column("decision_made_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR,
            sa.Computed(
                "to_tsvector('english', coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(rationale, ''))"
            ),
        ),
    )
    op.create_index("ix_decisions_workspace_id", "decisions", ["workspace_id"])
    op.create_index("ix_decisions_tags", "decisions", ["tags"], postgresql_using="gin")
    op.create_index("ix_decisions_impact_area", "decisions", ["impact_area"], postgresql_using="gin")
    op.create_index("ix_decisions_search_vector", "decisions", ["search_vector"], postgresql_using="gin")
    op.execute(
        "CREATE INDEX ix_decisions_embedding ON decisions USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    # --- decision_links ---
    op.create_table(
        "decision_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("decisions.id"), nullable=False),
        sa.Column("link_type", sa.String),
        sa.Column("link_url", sa.Text, nullable=False),
        sa.Column("link_title", sa.String),
        sa.Column("link_metadata", postgresql.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_decision_links_decision_id", "decision_links", ["decision_id"])

    # --- raw_messages ---
    op.create_table(
        "raw_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("slack_message_id", sa.String),
        sa.Column("channel_id", sa.String),
        sa.Column("thread_ts", sa.String),
        sa.Column("user_slack_id", sa.String),
        sa.Column("text", sa.Text),
        sa.Column("message_ts", sa.String),
        sa.Column("processed", sa.Boolean, server_default="false"),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("decisions.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_raw_messages_workspace_id", "raw_messages", ["workspace_id"])
    op.create_index("ix_raw_messages_decision_id", "raw_messages", ["decision_id"])

    # --- query_logs ---
    op.create_table(
        "query_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("user_slack_id", sa.String),
        sa.Column("query_text", sa.Text),
        sa.Column("results_count", sa.Integer),
        sa.Column("response_time_ms", sa.Integer),
        sa.Column("source", sa.String),
        sa.Column("helpful", sa.Boolean, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_query_logs_workspace_id", "query_logs", ["workspace_id"])

    # --- pending_confirmations ---
    op.create_table(
        "pending_confirmations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("decisions.id"), nullable=False),
        sa.Column("slack_channel_id", sa.String),
        sa.Column("slack_message_ts", sa.String),
        sa.Column("target_user_slack_id", sa.String),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_pending_confirmations_workspace_id", "pending_confirmations", ["workspace_id"])
    op.create_index("ix_pending_confirmations_decision_id", "pending_confirmations", ["decision_id"])


def downgrade() -> None:
    op.drop_table("pending_confirmations")
    op.drop_table("query_logs")
    op.drop_table("raw_messages")
    op.drop_table("decision_links")
    op.execute("DROP INDEX IF EXISTS ix_decisions_embedding")
    op.drop_table("decisions")
    op.drop_table("monitored_channels")
    op.drop_table("users")
    op.drop_table("workspaces")
    op.execute("DROP EXTENSION IF EXISTS vector")
