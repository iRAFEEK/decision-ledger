export interface Decision {
  id: string;
  title: string;
  summary: string | null;
  rationale: string | null;
  owner_name: string | null;
  owner_slack_id: string | null;
  tags: string[] | null;
  category: string | null;
  impact_area: string[] | null;
  status: string;
  confidence: number | null;
  source_url: string | null;
  source_channel_name: string | null;
  created_at: string;
  confirmed_at: string | null;
  confirmed_by: string | null;
}

export interface DecisionLink {
  id: string;
  link_type: string | null;
  link_url: string;
  link_title: string | null;
  link_metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface DecisionDetail extends Decision {
  links: DecisionLink[];
}

export interface PaginatedDecisions {
  items: Decision[];
  total: number;
  page: number;
  per_page: number;
}

export interface SearchResult {
  answer: string;
  decisions: SearchDecision[];
  total_count: number;
  response_time_ms: number;
}

export interface SearchDecision {
  id: string;
  title: string;
  summary: string | null;
  rationale: string | null;
  owner_name: string | null;
  tags: string[] | null;
  source_url: string | null;
  created_at: string | null;
  combined_score: number;
}

export interface Workspace {
  id: string;
  slack_team_id: string;
  team_name: string;
  plan: string | null;
  onboarding_complete: boolean;
  backfill_status: string | null;
  jira_domain: string | null;
  github_org: string | null;
  github_repo: string | null;
  created_at: string;
  updated_at: string;
}

export interface Channel {
  id: string;
  channel_id: string;
  channel_name: string | null;
  enabled: boolean;
  created_at: string;
}

export interface TopOwner {
  owner_name: string | null;
  owner_slack_id: string | null;
  count: number;
}

export interface CategoryCount {
  category: string | null;
  count: number;
}

export interface AnalyticsOverview {
  total_decisions: number;
  decisions_this_week: number;
  queries_this_week: number;
  confirmation_rate: number;
  top_owners: TopOwner[];
  decisions_by_category: CategoryCount[];
}
