# Decision Ledger — Technical Architecture Walkthrough

## 1. What This Product Is

Decision Ledger is an AI-powered system that passively captures engineering decisions from Slack conversations, extracts structured metadata, and makes them searchable via natural language. It solves the problem of institutional knowledge loss — the "why did we choose X?" questions that plague engineering teams months after a decision was made in a Slack thread nobody can find.

The core loop:
1. A Slack message arrives in a monitored channel (including Huddle transcripts)
2. Claude determines if it contains a commitment-level decision (not a question, not speculation)
3. If yes, Claude extracts structured fields: title, summary, rationale, owner, tags, category, participants (for huddles)
4. The decision is posted back to Slack with Confirm/Edit/Ignore buttons
5. Once confirmed, Voyage AI generates embeddings and Jira/GitHub references are enriched
6. Engineers can search decisions via `/decision <query>` in Slack or the web dashboard

---

## 2. Complete Data Flow: Slack Message → Stored Decision

### Step 1: Slack sends an HTTP POST to the backend

When a message is posted in a Slack channel, Slack's Event Subscriptions deliver it to `POST /slack/events`.

**`backend/app/slack/events.py:17-92`** — `slack_events()` handles the request:
- Lines 19-26: Reads the raw body, extracts `X-Slack-Request-Timestamp` and `X-Slack-Signature` headers, verifies HMAC signature via `verify_slack_signature()` (`backend/app/slack/verify.py:6-18`). The signature is `v0=HMAC-SHA256(signing_secret, "v0:{timestamp}:{body}")`. Requests older than 5 minutes are rejected (line 12).
- Lines 30-34: Handles Slack's `url_verification` challenge (required during app setup — Slack sends a challenge string, you echo it back).
- Lines 39-44: Filters out bot messages and most subtypes (edits, joins, etc.) to avoid processing non-human messages. However, `huddle_thread` subtypes are allowed through — when a Slack Huddle ends, its transcript is posted as a message with `subtype: "huddle_thread"`. For huddle messages, `source_hint="huddle"` is set on the `RawMessage` to signal downstream processing to use huddle-specific AI prompts.
- Lines 43-66: Looks up the workspace by `team_id`, then checks if the message's channel is in `monitored_channels` with `enabled=True`. If either lookup fails, returns 200 (Slack requires 200 even for ignored events).
- Lines 68-80: Creates a `RawMessage` record with the message text, user ID, channel ID, thread timestamp, and `processed=False`.
- Line 90: **Currently commented out** — `await arq_pool.enqueue_job("process_message", str(raw_msg.id))`. This would enqueue the message for AI processing. The arq pool is not yet wired into the FastAPI lifespan.

### Step 2: The arq worker picks up the job

**`backend/app/jobs/tasks.py:34-171`** — `process_message(ctx, message_id)`:

- Lines 36-40: Fetches the `RawMessage` by ID. If already processed, returns early.
- Lines 45-54: Fetches the workspace. If no `bot_access_token`, marks as processed and returns.
- Lines 56-69: Verifies the channel is still monitored and enabled.
- Lines 72-78: Fetches the full thread context via `slack_client.conversations_replies()` (`backend/app/slack/client.py:80-87`), which calls `conversations.replies` with up to 50 messages. If the message isn't in a thread, it uses just the single message.
- Lines 80-88: Formats messages into `[{user_slack_id, user_name, text, message_ts}]` dicts.

### Step 3: AI Detection

- Line 90: Calls `detect_decision(formatted, system_prompt=...)` (`backend/app/ai/detector.py:28-57`).
  - For regular messages, uses `DECISION_DETECTION_SYSTEM_PROMPT`. For huddle transcripts (detected via `raw_msg.source_hint == "huddle"`), uses `HUDDLE_DECISION_DETECTION_SYSTEM_PROMPT` which is tuned for spoken conversation patterns (verbal agreements, consensus-building, action items).
  - `_format_conversation()` turns the message list into `[timestamp] name: text` format.
  - Sends to Claude Sonnet (`claude-sonnet-4-5-20250929`). Max 512 tokens.
  - Parses JSON response: `{is_decision: bool, confidence: float, reasoning: str}`.
  - If JSON parsing fails, returns `confidence=0.0` with the raw text in reasoning.

- Lines 92-96 (tasks.py): If `confidence < 0.7`, marks the message as processed and returns. This threshold means only high-confidence detections proceed.

- Lines 98-113: Rate limiting — counts decisions created today for this workspace. If >= `MAX_DAILY_DETECTIONS` (5), stops processing to prevent runaway costs.

### Step 4: AI Extraction

- Line 115: Calls `extract_decision(formatted, system_prompt=...)` (`backend/app/ai/extractor.py:39-86`).
  - For regular messages, uses `DECISION_EXTRACTION_SYSTEM_PROMPT`. For huddle transcripts, uses `HUDDLE_DECISION_EXTRACTION_SYSTEM_PROMPT` which also extracts `participants` (all speakers in the huddle).
  - Sends the formatted conversation to Claude. Max 1024 tokens.
  - Validates `category` against the fixed set of 11 values. Invalid categories become `None`.
  - Returns structured dict with `title` (truncated to 100 chars), `summary`, `rationale`, `owner_slack_id`, `owner_name`, `tags`, `category`, `impact_area`, `referenced_tickets`, `referenced_prs`, `referenced_urls`, `participants`.

### Step 5: Create the Decision record

- Lines 117-138 (tasks.py): Creates a `Decision` ORM object with all extracted fields, `status="pending"`, `source_type="slack_thread"` (or `"huddle"` for huddle transcripts), `participants` (for huddles), and stores the raw thread messages as JSON in `raw_context`.

### Step 6: Create PendingConfirmation and post to Slack

- Lines 140-149: Creates a `PendingConfirmation` with a 48-hour expiry, targeted at the detected decision owner.
- Lines 151-157: Builds Block Kit message via `build_confirmation_blocks()` (`backend/app/slack/messages.py:4-59`) — header "Decision Detected", section with title+summary, context line with owner/channel/tags/confidence, and three action buttons: Confirm (primary), Edit, Ignore (danger). Posts to the channel via `slack_client.post_message()`.
- Lines 159-164: Stores the Slack message timestamp on the confirmation (for later message updates), marks the raw message as processed, links it to the decision.

---

## 3. Complete Search Flow: `/decision` Slash Command

### Step 1: Slack sends the command

**`backend/app/slack/commands.py:21-59`** — `slack_commands()`:
- Lines 23-30: Verifies HMAC signature.
- Lines 32-38: Parses form data: `command`, `text` (the query), `team_id`, `user_id`, `response_url`.
- Lines 40-41: If `/decision` with no text, returns usage instructions (lines 11-18).
- Lines 53-55: **Currently commented out** — would enqueue `process_query` job with `team_id`, `user_id`, `channel_id`, `text`, `response_url`.
- Lines 57-59: Returns ephemeral "Searching decisions..." message immediately (Slack requires a response within 3 seconds).

### Step 2: The worker processes the query

**`backend/app/jobs/tasks.py:174-196`** — `process_query()`:
- Lines 181-184: Calls `handle_decision_query()` (`backend/app/search/query_handler.py:15-73`).

### Step 3: Hybrid search

**`backend/app/search/query_handler.py:15-73`** — `handle_decision_query()`:
- Line 22: Starts a timer.
- Line 24: Calls `hybrid_search()` (`backend/app/search/engine.py:96-141`).

**`backend/app/search/engine.py:96-141`** — `hybrid_search()`:
- Lines 105-108: Generates a query embedding via `generate_query_embedding()` (`backend/app/ai/embeddings.py:38-39`), which calls Voyage AI with `input_type="query"` (as opposed to `"document"` for stored embeddings). Returns empty list if embedding fails.
- Line 110: Extracts crude query tags by splitting the query on spaces, keeping words longer than 2 characters, lowercased. Used for tag overlap scoring.
- Lines 112-123: Builds params dict with the embedding, workspace_id, query text, tags, and optional filters (date range, owner, categories, tags).
- Line 125: Executes `HYBRID_SEARCH_SQL` (lines 11-93) — a single SQL statement with 4 CTEs.

### Step 4: The SQL query (the heart of search)

**`backend/app/search/engine.py:11-93`** — `HYBRID_SEARCH_SQL`:

**CTE 1: `vector_results` (lines 12-34)** — Cosine similarity search using pgvector:
- `(1 - (embedding <=> :query_embedding::vector))` computes cosine similarity (the `<=>` operator returns cosine distance, so 1 minus distance = similarity).
- Filters to `status = 'active'` and `embedding IS NOT NULL`.
- Orders by distance, limits to top 20.

**CTE 2: `keyword_results` (lines 35-57)** — PostgreSQL full-text search:
- Uses `plainto_tsquery('english', :query)` to parse the query into a tsquery.
- Matches against `search_vector`, which is a computed column (`backend/app/db/models.py:124-128`): `to_tsvector('english', coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(rationale, ''))`.
- Scores with `ts_rank()`. Limits to top 20.

**CTE 3: `combined` (lines 58-78)** — Full outer join of vector and keyword results:
- Uses `COALESCE` to merge fields from both sides.
- Adds a `tag_bonus`: 1.0 if the decision's `tags` array overlaps (`&&` operator) with the query-derived tags, else 0.0.

**Final SELECT (lines 79-93)** — Weighted combination:
- `combined_score = 0.6 * vector_score + 0.3 * keyword_score + 0.1 * tag_bonus`
- Applies optional filters: date range, owner, categories, tags.
- Orders by `combined_score DESC`, limits to `result_limit` (default 5).

### Step 5: Enrich results with links

**`backend/app/search/query_handler.py:26-44`**:
- For each search result, fetches `DecisionLink` records.
- Categorizes links into `referenced_tickets` (jira), `referenced_prs` (github_pr), and `referenced_urls` (anything else).

### Step 6: AI synthesis

- Line 46: Calls `synthesize_answer()` (`backend/app/ai/synthesizer.py:45-59`).
  - Lines 12-42: `_format_context()` builds a text block for each decision with title, summary, rationale, owner, date, source URL, and linked artifacts.
  - Lines 49-56: Sends to Claude with `ANSWER_SYNTHESIS_SYSTEM_PROMPT` (`backend/app/ai/prompts.py:55-70`) — instructions to answer concisely, cite decisions by title, use Slack-compatible markdown. Max 1024 tokens.

### Step 7: Log the query and return

- Lines 50-60 (query_handler.py): Creates a `QueryLog` record with workspace ID, user, query text, result count, response time in ms, and source ("slack" or "api").
- Lines 69-73: Returns `{answer, decisions, response_time_ms}`.

### Step 8: Post results back to Slack

**`backend/app/jobs/tasks.py:186-196`**:
- Line 186: Builds Block Kit blocks via `build_search_result_blocks()` (`backend/app/slack/messages.py:109-135`) — the AI answer as a section, then a divider, then up to 5 decision summaries with titles, truncated summaries, and tags.
- Lines 188-196: POSTs to the Slack `response_url` (a one-time webhook URL) as an ephemeral message (only visible to the user who ran `/decision`).

---

## 4. The AI Pipeline in Detail

### Detection (`backend/app/ai/detector.py`)

**Purpose:** Binary classification — is this conversation a decision or not?

- Model: `claude-sonnet-4-5-20250929` (line 34)
- Accepts optional `system_prompt` parameter to override the default prompt.
- Default system prompt (`prompts.py:1-28`): Defines what IS a decision (commitment to an approach, finalized design choice, deprecation announcement, dependency selection, process change) vs what is NOT (questions, speculation, status updates, social chat, suggestions without commitment, existing behavior descriptions).
- Huddle prompt (`prompts.py` `HUDDLE_DECISION_DETECTION_SYSTEM_PROMPT`): Adapted for spoken conversation — detects verbal agreements ("yeah let's go with that"), consensus-building, and action items with decisions baked in.
- Output: `{is_decision: bool, confidence: float [0.0-1.0], reasoning: str}`
- Confidence guidance: >= 0.8 for clear commitments, 0.5-0.7 for ambiguous, < 0.5 for unlikely.
- The pipeline uses 0.7 as the threshold (`tasks.py:92`).

### Extraction (`backend/app/ai/extractor.py`)

**Purpose:** Given a conversation that IS a decision, extract structured fields.

- Same model, higher token limit (1024 vs 512).
- Accepts optional `system_prompt` parameter to override the default prompt.
- Default system prompt (`prompts.py:30-53`): Detailed rules per field:
  - `title`: Imperative style, max 100 chars. "Use PostgreSQL for event store" not "Database discussion".
  - `tags`: Lowercase hyphenated, 2-5 tags.
  - `category`: Must be one of 11 values (architecture, schema, api, infrastructure, deprecation, dependency, naming, process, security, performance, tooling).
  - `impact_area`: Specific system parts affected.
  - Also extracts `referenced_tickets`, `referenced_prs`, `referenced_urls` directly from conversation text.
- Huddle prompt (`prompts.py` `HUDDLE_DECISION_EXTRACTION_SYSTEM_PROMPT`): Same extraction rules but additionally extracts `participants` — all speakers in the huddle conversation.
- Title is hard-truncated to 100 characters.
- Category validation — if Claude returns an invalid category, it becomes `None`.

### Embeddings (`backend/app/ai/embeddings.py`)

**Purpose:** Generate 1024-dimensional vectors for semantic search.

- Calls Voyage AI's `voyage-3` model via REST API (line 21).
- Two functions with different `input_type` parameters:
  - `generate_embedding(text)` — `input_type="document"` (line 35). Used when storing a decision.
  - `generate_query_embedding(query)` — `input_type="query"` (line 39). Used at search time.
- The different input types tell Voyage to optimize the embedding for its role (document embeddings are optimized for being found, query embeddings for finding).

### Synthesis (`backend/app/ai/synthesizer.py`)

**Purpose:** Given a user's question and retrieved decisions, generate a concise answer.

- System prompt (`prompts.py:55-70`): Answer concisely, reference decisions by title, include owner and date when useful, note conflicts or superseded decisions, don't fabricate, use Slack-compatible markdown.
- `_format_context()` (lines 12-42) builds a numbered text block per decision including all metadata and linked artifacts.
- Falls back to "Sorry, I encountered an error" on any exception (line 59).

---

## 5. How Hybrid Search Combines Vector and Keyword Search

The search engine at `backend/app/search/engine.py` uses a single SQL query (lines 11-93) that runs three independent retrieval strategies and combines them with fixed weights.

### Vector Search (60% weight)
- Uses pgvector's `<=>` operator for cosine distance on the `embedding` column (Vector(1024)).
- The `embedding` column has an IVFFlat index (`backend/alembic/versions/001_initial_schema.py:111-113`) with 100 lists, using `vector_cosine_ops`.
- Score is `1 - cosine_distance` (so identical vectors score 1.0, orthogonal score 0.0).
- Retrieves top 20 candidates.

### Keyword Search (30% weight)
- Uses PostgreSQL's built-in full-text search via the `search_vector` computed column (`backend/app/db/models.py:124-128`).
- The column is auto-maintained: `to_tsvector('english', coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(rationale, ''))`.
- Has a GIN index (`001_initial_schema.py:110`).
- Ranked with `ts_rank()`, retrieves top 20 candidates.

### Tag Overlap (10% weight)
- Query words (> 2 chars, lowercased) are treated as pseudo-tags.
- The `&&` (overlap) operator checks if the decision's `tags` array shares any elements with the query tags.
- Binary: 1.0 if any overlap, 0.0 if none.

### Combination
The three strategies are joined via `FULL OUTER JOIN` (line 77), so a decision found by either vector OR keyword search is included. The final score is:

```
combined_score = 0.6 * vector_score + 0.3 * keyword_score + 0.1 * tag_bonus
```

This means a decision can score up to 1.0 if it's a perfect vector match (0.6), perfect keyword match (0.3), and has tag overlap (0.1). In practice, vector search dominates for semantic queries ("what database did we choose?"), keyword search catches exact terms the embedding might miss, and tag overlap provides a small boost for well-tagged decisions.

Post-combination filters (lines 86-90) apply optional date range, owner, category, and tag constraints.

---

## 6. Background Jobs

All jobs are defined in `backend/app/jobs/tasks.py` and registered in `backend/app/jobs/worker.py`.

### `process_message(ctx, message_id)` — Lines 34-171
**Trigger:** Enqueued when a Slack message arrives (currently commented out at `events.py:90`).
**What it does:** Full pipeline — fetch thread context, detect decision, extract structured data, create Decision + PendingConfirmation, post confirmation message to Slack.
**Key details:** 0.7 confidence threshold, 5 decisions/day rate limit per workspace, 48-hour confirmation expiry.

### `process_query(ctx, workspace_id, query_text, user_slack_id, response_url)` — Lines 174-196
**Trigger:** Enqueued when `/decision <query>` slash command is used (currently commented out at `commands.py:53-55`).
**What it does:** Runs hybrid search + AI synthesis, posts results back to Slack via `response_url`.

### `enrich_decision(ctx, decision_id)` — Lines 199-264
**Trigger:** Enqueued when a decision is confirmed (currently commented out at `interactive.py:99` and `decisions.py:167`).
**What it does:** Scans the decision's summary, rationale, and raw context for Jira ticket references (`PROJ-123`) and GitHub PR references (`#123`, full URLs). For each reference, calls the respective API to fetch metadata (title, status, assignee for Jira; title, state, author, merged status for GitHub). Creates `DecisionLink` records.
**Jira:** Uses `JiraClient` (`backend/app/integrations/jira/client.py:7-34`) — REST API v3, basic auth.
**GitHub:** Uses `GitHubClient` (`backend/app/integrations/github/client.py:7-46`) — REST API, Bearer token.
**Reference extraction:** Jira regex (`backend/app/integrations/jira/references.py:3`): `\b([A-Z][A-Z0-9]+-\d+)\b`. GitHub regex (`backend/app/integrations/github/references.py:3-5`): full URLs via `https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)`, short refs via `(?<!\w)#(\d+)\b`.

### `generate_embedding_task(ctx, decision_id)` — Lines 267-291
**Trigger:** Enqueued alongside `enrich_decision` when a decision is confirmed.
**What it does:** Concatenates `title + summary + rationale`, calls `generate_embedding()` (Voyage AI, `input_type="document"`), stores the 1024-dim vector in the `embedding` column.

### `expire_confirmations(ctx)` — Lines 294-318
**Trigger:** arq cron job, runs every hour at minute 0 (`worker.py:24`).
**What it does:** Finds all `PendingConfirmation` records where `expires_at < now` and `status == "pending"`. Sets them to "expired". Also sets the linked `Decision` status to "expired" if it's still "pending".

### `backfill_history(ctx, workspace_id, days=90)` — Lines 321-432
**Trigger:** Enqueued when user clicks "Start Backfill" in settings (currently commented out at `workspace.py:221`).
**What it does:** For each monitored channel, paginates through `conversations.history` going back `days` days. For each non-bot message with replies, fetches the thread, runs detection, and if confidence >= 0.7, runs extraction, creates the Decision with `status="active"` and `source_type="backfill"`, generates embedding inline. Sleeps 1 second between API calls to respect Slack rate limits. Sets `workspace.backfill_status` to "complete" when done.

### Worker Configuration (`backend/app/jobs/worker.py`)
- `max_jobs = 10` — up to 10 concurrent jobs.
- `job_timeout = 60` — jobs killed after 60 seconds.
- Redis connection parsed from `settings.redis_url` via `RedisSettings.from_dsn()`.

---

## 7. How Auth Works

### Slack OAuth Flow

**`backend/app/auth/oauth.py:40-48`** — `GET /auth/slack`:
- Redirects to `https://slack.com/oauth/v2/authorize` with `client_id`, bot scopes (channels:history, channels:read, chat:write, commands, groups:history, groups:read, users:read, users:read.email), user scopes (channels:history, groups:history, search:read), and `redirect_uri` pointing to `/auth/callback`.

**`backend/app/auth/oauth.py:51-179`** — `GET /auth/callback`:
- Receives the `code` parameter from Slack.
- Exchanges it for tokens via `POST https://slack.com/api/oauth.v2.access` (lines 57-66).
- Extracts `team_id`, `team_name`, `bot_token`, `user_token`, `user_slack_id`.
- Fetches user profile via `users.info` API (lines 83-97) for display name, email, avatar.
- Upserts workspace: creates if new, updates tokens if existing (lines 99-121).
- Upserts user: creates with `is_admin=True` if new, updates profile if existing (lines 123-151).
- Generates JWT (lines 156-166).
- Sets `session` cookie and redirects to `/dashboard` (lines 168-178).

### JWT Token

**Structure** (defined at `oauth.py:156-163`):
```json
{
  "sub": "<user UUID>",
  "workspace_id": "<workspace UUID>",
  "slack_user_id": "<Slack user ID>",
  "is_admin": true/false,
  "exp": "<7 days from now>"
}
```
- Algorithm: HS256, secret: `settings.jwt_secret`.
- Stored as httpOnly cookie named `session`, `samesite=lax`, `secure=False` (localhost), max age 7 days.

### JWT Extraction on Every Request

**`backend/app/auth/middleware.py:7-48`**:
- `_extract_token()` (lines 7-13): Checks for `session` cookie first, then `Authorization: Bearer` header.
- `_decode_token()` (lines 16-23): Decodes JWT with `python-jose`, returns `{user_id, workspace_id, slack_user_id, is_admin}`.
- `get_current_user()` (lines 26-35): FastAPI dependency. Returns 401 if no token or invalid token.
- `get_optional_user()` (lines 38-48): Returns `None` instead of 401 — for endpoints that work with or without auth.

### Dev Login

**`backend/app/auth/oauth.py:182-228`** — `GET /auth/dev-login`:
- Only works when `settings.app_url` contains "localhost" (line 184).
- Looks up workspace with `slack_team_id="T_DEMO"`.
- Finds or creates a demo user (U_DEMO, admin).
- Issues the same JWT cookie as the real OAuth flow.
- Redirects to `/dashboard`.

---

## 8. Every API Endpoint

### Health (`backend/app/main.py:54-58`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Executes `SELECT 1` against PostgreSQL. Returns `{"status": "ok"}`. |

### Auth (`backend/app/auth/oauth.py`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/auth/slack` | No | Redirects to Slack OAuth authorize URL with bot+user scopes. |
| GET | `/auth/callback` | No | Handles OAuth code exchange, upserts workspace+user, sets JWT cookie, redirects to `/dashboard`. |
| GET | `/auth/dev-login` | No | Dev-only: creates JWT for demo workspace, redirects to `/dashboard`. |

### Slack Webhooks (`backend/app/slack/`)
| Method | Path | Auth | HMAC | Description |
|--------|------|------|------|-------------|
| POST | `/slack/events` | No | Yes | Receives message events. Handles `url_verification` challenge. Stores `RawMessage` for monitored channels. |
| POST | `/slack/commands` | No | Yes | Handles `/decision <query>` slash command. Returns usage if no query. |
| POST | `/slack/interactive` | No | Yes | Handles block_actions: `confirm_decision`, `edit_decision`, `ignore_decision`. |

### Decisions (`backend/app/api/decisions.py`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/decisions` | JWT | Paginated list. Filters: `status`, `category`, `owner_slack_id`, `tag`, `channel_id`, `date_from`, `date_to`. Default 20/page. |
| GET | `/api/decisions/{id}` | JWT | Decision detail with eager-loaded `links`. |
| PATCH | `/api/decisions/{id}` | JWT | Update fields: title, summary, rationale, tags, impact_area, category, status. |
| DELETE | `/api/decisions/{id}` | JWT | Soft-delete: sets `status="deleted"`. Returns 204. |
| POST | `/api/decisions/{id}/confirm` | JWT | Sets `status="active"`, records `confirmed_at` and `confirmed_by`. |
| POST | `/api/decisions/{id}/ignore` | JWT | Sets `status="ignored"`. |

### Search (`backend/app/api/search.py`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/search` | JWT | Body: `{query, filters?, limit, offset}`. Returns `{answer, decisions[], total_count, response_time_ms}`. Filters: date_from, date_to, owner_slack_id, categories, tags, status. |

### Analytics (`backend/app/api/analytics.py`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/analytics/overview` | JWT | Returns: total active decisions, decisions this week, queries this week, confirmation rate (active / (active + ignored)), top 5 owners by count, decisions grouped by category. |

### Workspace (`backend/app/api/workspace.py`)
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/workspace` | JWT | Returns workspace info (team name, Slack ID, backfill status, integration status). |
| PATCH | `/api/workspace/settings` | JWT | Updates workspace `settings` JSONB column. |
| GET | `/api/workspace/channels` | JWT | Lists all monitored channels, ordered by creation date. |
| POST | `/api/workspace/channels` | JWT | Adds a monitored channel. Returns 409 if already exists. |
| DELETE | `/api/workspace/channels/{channel_id}` | JWT | Removes a monitored channel. |
| POST | `/api/workspace/integrations/jira` | JWT | Saves Jira credentials (domain, email, api_token). Test-calls `GET /rest/api/3/issue/TEST-1` to validate. |
| POST | `/api/workspace/integrations/github` | JWT | Saves GitHub credentials (org, repo, token). Test-calls `GET /repos/{org}/{repo}/pulls/1` to validate. |
| POST | `/api/workspace/backfill` | JWT | Triggers history backfill. Returns 409 if already running. |

---

## 9. Every Frontend Page

The frontend is a Next.js 16 app using React 19, Tailwind CSS v4, and Lucide icons. All API calls go through `frontend/src/lib/api.ts`, which uses `fetch()` with `credentials: "include"` for cookie-based auth.

### Landing Page (`frontend/src/app/page.tsx`)
- Full-screen centered layout with "Decision Ledger" heading, tagline, and "Connect to Slack" button.
- The button links to `{NEXT_PUBLIC_API_URL}/auth/slack` to start OAuth.
- Three feature cards below: "Passive Capture", "Natural Language Search", "Full Context".

### Root Layout (`frontend/src/app/layout.tsx`)
- Inter font from Google Fonts.
- Dark theme: `<html className="dark">`, body with `bg-zinc-950 text-zinc-100`.

### Dashboard Layout (`frontend/src/app/dashboard/layout.tsx`)
- Responsive sidebar with 4 nav items: Dashboard, Decisions, Search, Settings.
- Desktop: fixed 224px sidebar. Mobile: hamburger menu with overlay.
- Active state highlighting based on `usePathname()`.

### Dashboard Page (`frontend/src/app/dashboard/page.tsx`)
- Fetches `GET /api/analytics/overview` on mount.
- Displays 4 stat cards: Total Decisions, This Week, Queries This Week, Confirmation Rate.
- Two panels: Top Decision Owners (list with count badges), Decisions by Category (horizontal bar chart using percentage-width divs).

### Decisions Page (`frontend/src/app/dashboard/decisions/page.tsx`)
- Fetches `GET /api/decisions` with pagination, status filter, category filter, and tag search.
- Each decision is a card showing title, summary (2-line clamp), tags, owner name, date, and status badge (color-coded: yellow=pending, green=active, gray=ignored, red=expired).
- Click to expand: shows rationale, source channel, linked Jira/GitHub items.
- Pending decisions show Confirm (green) and Ignore (gray) buttons that call `POST /api/decisions/{id}/confirm` or `/ignore`.
- Pagination controls at bottom.

### Search Page (`frontend/src/app/dashboard/search/page.tsx`)
- Search input with Lucide Search icon.
- Submits `POST /api/search` with `{query, limit: 5}`.
- Displays AI-synthesized answer in a blue-tinted card.
- Below: response time, then "Source Decisions" list showing title, summary, tags, owner, and `combined_score` as a percentage badge.

### Settings Page (`frontend/src/app/dashboard/settings/page.tsx`)
- **Workspace info section:** Team name, Slack Team ID, backfill status.
- **Monitored Channels:** List with remove buttons. Add form with Channel ID and optional name.
- **Jira Integration:** Connection status badge. Form with domain, email, API token. Calls `POST /api/workspace/integrations/jira`.
- **GitHub Integration:** Connection status badge. Form with org, repo, PAT. Calls `POST /api/workspace/integrations/github`.
- **History Backfill:** Description text, "Start Backfill" button (disabled while running). Calls `POST /api/workspace/backfill`.

### TypeScript Types (`frontend/src/lib/types.ts`)
Mirrors the backend Pydantic schemas: `Decision`, `DecisionLink`, `DecisionDetail`, `PaginatedDecisions`, `SearchResult`, `SearchDecision`, `Workspace`, `Channel`, `TopOwner`, `CategoryCount`, `AnalyticsOverview`.

### API Client (`frontend/src/lib/api.ts`)
Generic `request<T>()` function that prepends `NEXT_PUBLIC_API_URL`, includes credentials, sets JSON content type, throws on non-OK responses with `"${status}: ${body}"`. Exports `apiGet`, `apiPost`, `apiPatch`, `apiDelete`.

---

## 10. Database Schema

8 tables, all using UUID primary keys and timezone-aware timestamps.

### `workspaces`
The root entity. One per Slack workspace.
- Stores Slack tokens (`bot_access_token`, `user_access_token`).
- Stores integration credentials (`jira_domain/email/api_token`, `github_org/repo/token`).
- `settings` JSONB for workspace-level configuration.
- `backfill_status` tracks history import progress.

**Relationships:** Has many `users`, `monitored_channels`, `decisions`, `raw_messages`, `query_logs`, `pending_confirmations`.

### `users`
One per Slack user per workspace.
- `slack_user_id` + `workspace_id` is unique (constraint `uq_users_workspace_slack`).
- `is_admin` for access control.
- Created during OAuth callback.

### `monitored_channels`
Which Slack channels the bot watches.
- `channel_id` + `workspace_id` is unique (constraint `uq_monitored_channels_workspace_channel`).
- `enabled` flag to temporarily pause monitoring without deleting.

### `decisions`
The core table. Every detected engineering decision.
- **Content:** `title`, `summary`, `rationale`.
- **Ownership:** `owner_slack_id`, `owner_name`.
- **Source:** `source_type` (slack_thread, huddle, backfill), `source_channel_id`, `source_channel_name`, `source_thread_ts`, `source_url`.
- **Participants:** `participants` (varchar[]) — for huddle-sourced decisions, lists all speakers who were part of the call.
- **Classification:** `tags` (varchar[]), `impact_area` (varchar[]), `category` (varchar).
- **AI:** `confidence` (float), `embedding` (Vector(1024)), `raw_context` (JSON — original messages).
- **Lifecycle:** `status` (pending → active/ignored/expired/deleted), `confirmed_at`, `confirmed_by`, `decision_made_at`.
- **Search:** `search_vector` (TSVECTOR, computed column for full-text search).

**Indexes:**
- `ix_decisions_workspace_id` — B-tree on `workspace_id`.
- `ix_decisions_tags` — GIN on `tags` array (supports `&&` overlap and `@>` containment).
- `ix_decisions_impact_area` — GIN on `impact_area` array.
- `ix_decisions_participants` — GIN on `participants` array.
- `ix_decisions_search_vector` — GIN on `search_vector` (full-text search).
- `ix_decisions_embedding` — IVFFlat on `embedding` with `vector_cosine_ops`, 100 lists (approximate nearest neighbor).

### `decision_links`
External references attached to decisions.
- `link_type`: "jira", "github_pr", or other.
- `link_url`: The external URL.
- `link_title`: Human-readable label like "PROJ-123: Fix auth bug" or "#87: Add pgvector migration".
- `link_metadata`: Full API response JSON from Jira/GitHub (status, assignee, merged state, etc.).

**Relationship:** Belongs to one `decision`.

### `raw_messages`
Every Slack message received from monitored channels.
- Stores the original text, user, channel, timestamps.
- `source_hint` (varchar, nullable) — set to `"huddle"` for messages originating from Slack Huddle transcripts. Used by the worker to select huddle-specific AI prompts.
- `processed` flag prevents re-processing.
- `decision_id` links to the decision created from this message (nullable — most messages won't produce decisions).

### `query_logs`
Every search query, from both Slack and web.
- `source`: "slack" or "api".
- `results_count`, `response_time_ms` for performance monitoring.
- `helpful`: Boolean feedback (nullable, not yet wired to UI).

### `pending_confirmations`
Tracks Slack confirmation messages awaiting user action.
- `slack_channel_id` + `slack_message_ts` identify the Slack message to update.
- `target_user_slack_id`: The decision owner who should confirm.
- `expires_at`: 48 hours from creation. The `expire_confirmations` cron job cleans these up.
- `status`: pending → expired (by cron) or implicitly resolved when the decision is confirmed/ignored.

### Entity Relationship Summary

```
workspaces ─┬─< users
             ├─< monitored_channels
             ├─< decisions ──< decision_links
             │        └──< raw_messages
             │        └──< pending_confirmations
             ├─< raw_messages
             ├─< query_logs
             └─< pending_confirmations
```

All tables cascade through `workspace_id` — every record belongs to exactly one workspace, enforcing multi-tenant isolation. The `decisions` table is the hub, with `decision_links`, `raw_messages`, and `pending_confirmations` hanging off it.

