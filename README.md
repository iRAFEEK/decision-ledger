# Decision Ledger

An AI-powered decision tracking system that automatically detects, extracts, and indexes engineering decisions from Slack conversations. Search your team's decision history using natural language and never lose track of why a decision was made.

## Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Slack App   │────▶│  FastAPI Backend  │────▶│  PostgreSQL     │
│  (Events)    │     │  (port 8000)      │     │  + pgvector     │
└──────────────┘     └──────┬───────────┘     │  (port 5499)    │
                            │                  └─────────────────┘
                            │
┌──────────────┐     ┌──────▼───────────┐     ┌─────────────────┐
│  Next.js     │────▶│  arq Worker      │────▶│  Redis          │
│  Frontend    │     │  (background)     │     │  (port 6379)    │
│  (port 3000) │     └──────┬───────────┘     └─────────────────┘
└──────────────┘            │
                     ┌──────▼───────────┐
                     │  Claude API      │
                     │  (detection,     │
                     │   extraction,    │
                     │   synthesis)     │
                     └──────┬───────────┘
                            │
                     ┌──────▼───────────┐
                     │  Voyage AI       │
                     │  (embeddings)    │
                     └──────────────────┘

External Integrations: Jira, GitHub (reference enrichment)
```

### Processing Pipeline

1. Slack message event received via webhook (typed messages and Huddle transcripts)
2. arq worker runs Claude-based decision detection (with huddle-specific prompts for voice conversations)
3. If a decision is detected, Claude extracts structured fields (title, summary, rationale, owner, tags, category, participants)
4. Voyage AI generates embeddings for vector search
5. Jira/GitHub references are enriched with metadata
6. Decisions are searchable via hybrid search (vector + full-text + tags)

### Huddle Support

When a Slack Huddle ends, its transcript is posted to the channel. Decision Ledger processes these transcripts using specialized AI prompts tuned for spoken conversation patterns — detecting verbal agreements, consensus-building, and action items. Huddle-sourced decisions include participant information and are displayed with a headphones icon in the dashboard.

## Prerequisites

- **Docker** and **Docker Compose** (for production deployment)
- **Python 3.13+** (for local development)
- **Node.js 20+** (for frontend development)
- **PostgreSQL 15** with pgvector extension
- **Redis 7+**

### API Keys Required

| Service | Purpose | Sign Up |
|---------|---------|---------|
| Slack App | Message events, OAuth | [api.slack.com/apps](https://api.slack.com/apps) |
| Anthropic | Decision detection, extraction, synthesis | [console.anthropic.com](https://console.anthropic.com) |
| Voyage AI | Text embeddings (optional, for semantic search) | [dash.voyageai.com](https://dash.voyageai.com) |

## Quick Start

### 1. Clone and configure

```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your API keys
```

### 2. Start with Docker Compose

```bash
docker compose -f docker-compose.production.yml up --build
```

### 3. Database migrations

The `migrate` service applies migrations before the API and worker start. Its configuration and scripts are included in the backend image. To inspect the current revision:

```bash
docker compose -f docker-compose.production.yml exec backend alembic current
```

### 4. Create your Slack App

See [Slack App Setup](#slack-app-setup) below.

### 5. Access the dashboard

Open [http://localhost:3000](http://localhost:3000) and click "Connect to Slack" to authenticate.

## Slack App Setup

### 1. Create a new Slack App

Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App** → **From scratch**.

### 2. OAuth & Permissions

Add these **Bot Token Scopes**:

- `channels:history` — Read messages in public channels
- `channels:read` — View basic channel info
- `chat:write` — Send messages as the bot
- `commands` — Add slash commands
- `users:read` — View user profiles

Set the **Redirect URL** to:
```
http://localhost:8000/auth/callback
```

### 3. Event Subscriptions

Enable events and set the **Request URL** to:
```
http://localhost:8000/slack/events
```

Subscribe to these **Bot Events**:
- `message.channels` — Messages in public channels

### 4. Slash Commands

Create a `/decision` command with the **Request URL**:
```
http://localhost:8000/slack/commands
```

### 5. Interactivity

Enable interactivity and set the **Request URL** to:
```
http://localhost:8000/slack/interactive
```

### 6. Install the app

Install the app to your workspace. Copy the **Client ID**, **Client Secret**, and **Signing Secret** into your `.env` file.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string (asyncpg) |
| `REDIS_URL` | Yes | Redis connection string |
| `SLACK_CLIENT_ID` | Yes | Slack app client ID |
| `SLACK_CLIENT_SECRET` | Yes | Slack app client secret |
| `SLACK_SIGNING_SECRET` | Yes | Slack request signing secret |
| `GEMINI_API_KEY` | Either AI key | Gemini key; takes priority when configured |
| `GEMINI_MODEL` | No | Defaults to `gemini-3.8-flash` |
| `ANTHROPIC_API_KEY` | Either AI key | Claude alternative when Gemini is not configured |
| `JWT_SECRET` | Yes | Secret for signing JWT tokens |
| `ENCRYPTION_KEY` | No | Key for encrypting stored credentials |
| `VOYAGE_API_KEY` | No | Voyage AI key for embeddings |
| `APP_URL` | No | Frontend URL (default: `http://localhost:3000`) |
| `API_URL` | No | Backend URL (default: `http://localhost:8000`) |
| `JIRA_DOMAIN` | No | Jira instance domain |
| `JIRA_EMAIL` | No | Jira account email |
| `JIRA_API_TOKEN` | No | Jira API token |
| `GITHUB_TOKEN` | No | GitHub personal access token |
| `GITHUB_ORG` | No | GitHub organization name |
| `GITHUB_REPO` | No | GitHub repository name |
| `NEXT_PUBLIC_API_URL` | No | API URL for frontend (default: `http://localhost:8000`) |

## Application addresses and login

`APP_URL` is the frontend origin allowed by CORS. `API_URL` is the browser-reachable backend origin and determines the Slack callback URL. `NEXT_PUBLIC_API_URL` must match that backend origin; it is embedded in the frontend at build time. Never use the container hostname `backend` for the browser URL.

For Docker Compose, put backend settings in `backend/.env` and set the frontend build argument through a root `.env` or the shell:

```bash
NEXT_PUBLIC_API_URL=https://api.example.com docker compose -f docker-compose.production.yml up --build -d
```

Supported cookie setups are local HTTP on `localhost` for both services, or HTTPS on the same site (for example `app.example.com` and `api.example.com`). Unrelated frontend/API domains require a same-site reverse proxy; third-party cookie authentication is not supported. If using a tunnel for Slack login, use the tunneled API address consistently in `API_URL`, `NEXT_PUBLIC_API_URL`, and Slack's redirect configuration, and serve the frontend on the same site. Rebuild the frontend after changing its API URL.

OAuth now checks a state cookie and sets the session cookie directly on the callback response. The old token-in-query `/auth/set-session` endpoint is removed. HTTPS API origins receive Secure cookies.

## Development Setup (without Docker)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Start Postgres and Redis
docker compose -f ../docker-compose.yml up -d

# Run migrations
alembic upgrade head

# Start the API server
uvicorn app.main:app --reload --port 8000

# In another terminal, start the worker
python -m arq app.jobs.worker.WorkerSettings
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Run tests

Self-contained tests require no service credentials:

```bash
cd backend
pip install -e ".[dev]"
pytest -q
```

For integration tests, start disposable services from the repository root:

```bash
docker compose -f docker-compose.test.yml up -d --wait
cd backend
export TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:15499/decision_ledger_test
export TEST_REDIS_URL=redis://localhost:16379
DATABASE_URL="$TEST_DATABASE_URL" alembic upgrade head
pytest --integration -q
```

Only point `TEST_DATABASE_URL` at a disposable database. Tests create and remove unique schemas; Redis jobs use a unique queue. External Slack, Anthropic, and Voyage responses are mocked in these tests. They verify real persistence, queue execution, retrieval, and edits, but do not measure live model quality.

```bash
# From the repository root, after testing:
docker compose -f docker-compose.test.yml down
cd frontend
npm ci
npm run lint
npm run build
npm audit --omit=dev
```

GitHub Actions runs these checks plus the production Compose startup and migration smoke check.

### Local demo without Slack credentials

With the API and database configured and migrated, run `DATABASE_URL=... python scripts/seed_demo.py` from `backend`, then open `http://localhost:8000/auth/dev-login`. The seed command preserves existing demo data on subsequent runs. Demo login is available only when `APP_URL` has a loopback hostname. Demo decisions support keyword search without AI keys; they do not include live semantic embeddings.

### Search behavior

Search defaults to active decisions in the current workspace. The API accepts date bounds, owner, categories, tags, and status (`active`, `pending`, `ignored`, `expired`), plus `limit` (1–20) and `offset`. Dates filter `created_at`, bounds are inclusive, and dates without a timezone use UTC. Date-only upper bounds mean midnight; send a timestamp for the end of a whole day.

Filters apply before ranking. Results have deterministic ordering, and `total_count` counts all filtered candidates before pagination, including when the requested page is empty. With an embedding, candidates include vector-bearing decisions plus keyword/tag matches; without one, they are keyword/tag matches only. Exact ranking/counting favors correctness for the current small dataset; large workspaces should benchmark this query before changing it to approximate retrieval.

Voyage is optional: missing credentials or an embedding request failure falls back to keyword/tag retrieval. AI summary failures preserve retrieved decisions and show a readable fallback. Slack edits are allowed for the decision owner or a workspace admin, persist before acknowledgement, and queue slower message and embedding refreshes.

### Dependency audit

Next.js and its matching lint configuration were updated to 16.4.0, along with compatible transitive patches. The October 7, 2026 runtime audit reported zero vulnerabilities. The full audit still reports five high-severity entries along the development-only `braces` → `micromatch` → `fast-glob` → Next lint tooling chain. The suggested forced fix downgrades the Next lint configuration to 14.x; it has not been applied. Recheck upstream fixes before changing that tooling.

## API Endpoints

### Health
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Database connectivity check |

### Auth
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/auth/slack` | Initiate Slack OAuth flow |
| `GET` | `/auth/callback` | Slack OAuth callback |

### Slack Webhooks
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/slack/events` | Slack event subscriptions |
| `POST` | `/slack/commands` | Slash command handler |
| `POST` | `/slack/interactive` | Interactive component handler |

### Decisions (requires auth)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/decisions` | List decisions (paginated, filterable) |
| `GET` | `/api/decisions/:id` | Get decision detail with links |
| `PATCH` | `/api/decisions/:id` | Update decision fields |
| `DELETE` | `/api/decisions/:id` | Soft-delete a decision |
| `POST` | `/api/decisions/:id/confirm` | Confirm a detected decision |
| `POST` | `/api/decisions/:id/ignore` | Ignore a detected decision |

### Search (requires auth)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/search` | Hybrid search with AI synthesis |

### Analytics (requires auth)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/analytics/overview` | Dashboard statistics |

### Workspace (requires auth)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/workspace` | Workspace info |
| `PATCH` | `/api/workspace/settings` | Update workspace settings |
| `GET` | `/api/workspace/channels` | List monitored channels |
| `POST` | `/api/workspace/channels` | Add monitored channel |
| `DELETE` | `/api/workspace/channels/:id` | Remove monitored channel |
| `POST` | `/api/workspace/integrations/jira` | Configure Jira integration |
| `POST` | `/api/workspace/integrations/github` | Configure GitHub integration |
| `POST` | `/api/workspace/backfill` | Trigger channel history backfill |

### Gemini and channel setup

Create a Gemini key in Google AI Studio and set `GEMINI_API_KEY` in `backend/.env` (or the host secret settings). Restart both API and worker after changing keys. Detection, extraction, and summaries use Gemini; Voyage embeddings remain optional, with keyword search available without them. Never commit `.env`.

After Slack installation, invite the bot to the desired channel and add its channel ID (the final `C...` segment of the Slack URL) under Settings → Monitored Channels. The name is optional. Run History Backfill to scan existing engineering decisions. Live messages require Slack Event Subscriptions pointing to the publicly reachable `/slack/events` endpoint, plus interactive callbacks at `/slack/interactive`. Temporary Gemini HTTP failures are retried; Slack and AI failures mark backfill as failed rather than complete. Repeated backfills skip already saved source threads.
