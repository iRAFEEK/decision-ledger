import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.dialects.postgresql import ARRAY, JSON, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slack_team_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    team_name: Mapped[str] = mapped_column(String, nullable=False)
    bot_access_token: Mapped[str | None] = mapped_column(Text)
    user_access_token: Mapped[str | None] = mapped_column(Text)
    settings: Mapped[dict | None] = mapped_column(JSONB)
    plan: Mapped[str | None] = mapped_column(String)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    backfill_status: Mapped[str | None] = mapped_column(String)
    jira_domain: Mapped[str | None] = mapped_column(String)
    jira_email: Mapped[str | None] = mapped_column(String)
    jira_api_token: Mapped[str | None] = mapped_column(Text)
    github_org: Mapped[str | None] = mapped_column(String)
    github_repo: Mapped[str | None] = mapped_column(String)
    github_token: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="workspace")
    monitored_channels: Mapped[list["MonitoredChannel"]] = relationship(back_populates="workspace")
    decisions: Mapped[list["Decision"]] = relationship(back_populates="workspace")
    raw_messages: Mapped[list["RawMessage"]] = relationship(back_populates="workspace")
    query_logs: Mapped[list["QueryLog"]] = relationship(back_populates="workspace")
    pending_confirmations: Mapped[list["PendingConfirmation"]] = relationship(back_populates="workspace")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("workspace_id", "slack_user_id", name="uq_users_workspace_slack"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    slack_user_id: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String)
    avatar_url: Mapped[str | None] = mapped_column(String)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped["Workspace"] = relationship(back_populates="users")


class MonitoredChannel(Base):
    __tablename__ = "monitored_channels"
    __table_args__ = (
        UniqueConstraint("workspace_id", "channel_id", name="uq_monitored_channels_workspace_channel"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    channel_id: Mapped[str] = mapped_column(String, nullable=False)
    channel_name: Mapped[str | None] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped["Workspace"] = relationship(back_populates="monitored_channels")


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        Index("ix_decisions_tags", "tags", postgresql_using="gin"),
        Index("ix_decisions_impact_area", "impact_area", postgresql_using="gin"),
        Index("ix_decisions_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_decisions_workspace_id", "workspace_id"),
        Index("ix_decisions_participants", "participants", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    owner_slack_id: Mapped[str | None] = mapped_column(String)
    owner_name: Mapped[str | None] = mapped_column(String)
    source_type: Mapped[str | None] = mapped_column(String)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_channel_id: Mapped[str | None] = mapped_column(String)
    source_channel_name: Mapped[str | None] = mapped_column(String)
    source_thread_ts: Mapped[str | None] = mapped_column(String)
    tags = mapped_column(ARRAY(String), nullable=True)
    impact_area = mapped_column(ARRAY(String), nullable=True)
    category: Mapped[str | None] = mapped_column(String)
    confidence: Mapped[float | None] = mapped_column(Float)
    embedding = mapped_column(Vector(1024), nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[str | None] = mapped_column(String)
    participants = mapped_column(ARRAY(String), nullable=True)
    raw_context = mapped_column(JSON, nullable=True)
    decision_made_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    search_vector = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(rationale, ''))"),
        nullable=True,
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="decisions")
    links: Mapped[list["DecisionLink"]] = relationship(back_populates="decision")
    raw_messages: Mapped[list["RawMessage"]] = relationship(back_populates="decision")
    pending_confirmations: Mapped[list["PendingConfirmation"]] = relationship(back_populates="decision")


class DecisionLink(Base):
    __tablename__ = "decision_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("decisions.id"), nullable=False, index=True)
    link_type: Mapped[str | None] = mapped_column(String)
    link_url: Mapped[str] = mapped_column(Text, nullable=False)
    link_title: Mapped[str | None] = mapped_column(String)
    link_metadata = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    decision: Mapped["Decision"] = relationship(back_populates="links")


class RawMessage(Base):
    __tablename__ = "raw_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False, index=True)
    slack_message_id: Mapped[str | None] = mapped_column(String)
    channel_id: Mapped[str | None] = mapped_column(String)
    thread_ts: Mapped[str | None] = mapped_column(String)
    user_slack_id: Mapped[str | None] = mapped_column(String)
    text: Mapped[str | None] = mapped_column(Text)
    message_ts: Mapped[str | None] = mapped_column(String)
    source_hint: Mapped[str | None] = mapped_column(String, nullable=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("decisions.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped["Workspace"] = relationship(back_populates="raw_messages")
    decision: Mapped["Decision | None"] = relationship(back_populates="raw_messages")


class QueryLog(Base):
    __tablename__ = "query_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False, index=True)
    user_slack_id: Mapped[str | None] = mapped_column(String)
    query_text: Mapped[str | None] = mapped_column(Text)
    results_count: Mapped[int | None] = mapped_column(Integer)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(String)
    helpful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped["Workspace"] = relationship(back_populates="query_logs")


class PendingConfirmation(Base):
    __tablename__ = "pending_confirmations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False, index=True)
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("decisions.id"), nullable=False, index=True)
    slack_channel_id: Mapped[str | None] = mapped_column(String)
    slack_message_ts: Mapped[str | None] = mapped_column(String)
    target_user_slack_id: Mapped[str | None] = mapped_column(String)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped["Workspace"] = relationship(back_populates="pending_confirmations")
    decision: Mapped["Decision"] = relationship(back_populates="pending_confirmations")
