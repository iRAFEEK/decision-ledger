from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# --- Decisions ---

class DecisionOut(BaseModel):
    id: UUID
    title: str
    summary: str | None = None
    rationale: str | None = None
    owner_slack_id: str | None = None
    owner_name: str | None = None
    source_type: str | None = None
    source_url: str | None = None
    source_channel_id: str | None = None
    source_channel_name: str | None = None
    tags: list[str] | None = None
    impact_area: list[str] | None = None
    category: str | None = None
    confidence: float | None = None
    status: str
    confirmed_at: datetime | None = None
    confirmed_by: str | None = None
    decision_made_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DecisionLinkOut(BaseModel):
    id: UUID
    link_type: str | None = None
    link_url: str
    link_title: str | None = None
    link_metadata: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DecisionDetailOut(DecisionOut):
    links: list[DecisionLinkOut] = []


class DecisionUpdateIn(BaseModel):
    title: str | None = None
    summary: str | None = None
    rationale: str | None = None
    tags: list[str] | None = None
    impact_area: list[str] | None = None
    category: str | None = None
    status: str | None = None


class PaginatedDecisions(BaseModel):
    items: list[DecisionOut]
    total: int
    page: int
    per_page: int


# --- Search ---

class SearchFilters(BaseModel):
    date_from: str | None = None
    date_to: str | None = None
    owner_slack_id: str | None = None
    categories: list[str] | None = None
    tags: list[str] | None = None
    status: str | None = None


class SearchRequest(BaseModel):
    query: str
    filters: SearchFilters | None = None
    limit: int = Field(default=5, ge=1, le=20)
    offset: int = Field(default=0, ge=0)


class SearchResultDecision(BaseModel):
    id: str
    title: str
    summary: str | None = None
    rationale: str | None = None
    owner_name: str | None = None
    tags: list[str] | None = None
    source_url: str | None = None
    created_at: str | None = None
    combined_score: float


class SearchResponse(BaseModel):
    answer: str
    decisions: list[SearchResultDecision]
    total_count: int
    response_time_ms: int


# --- Workspace ---

class WorkspaceOut(BaseModel):
    id: UUID
    slack_team_id: str
    team_name: str
    plan: str | None = None
    onboarding_complete: bool
    backfill_status: str | None = None
    jira_domain: str | None = None
    github_org: str | None = None
    github_repo: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceSettingsUpdate(BaseModel):
    settings: dict


class ChannelOut(BaseModel):
    id: UUID
    channel_id: str
    channel_name: str | None = None
    enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ChannelCreateIn(BaseModel):
    channel_id: str
    channel_name: str | None = None


class JiraConfigIn(BaseModel):
    domain: str
    email: str
    api_token: str


class GitHubConfigIn(BaseModel):
    org: str
    repo: str
    token: str


# --- Analytics ---

class TopOwner(BaseModel):
    owner_name: str | None
    owner_slack_id: str | None
    count: int


class CategoryCount(BaseModel):
    category: str | None
    count: int


class AnalyticsOverview(BaseModel):
    total_decisions: int
    decisions_this_week: int
    queries_this_week: int
    confirmation_rate: float
    top_owners: list[TopOwner]
    decisions_by_category: list[CategoryCount]
