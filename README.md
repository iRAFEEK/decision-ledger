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

1. Slack message event received via webhook
2. arq worker runs Claude-based decision detection
3. If a decision is detected, Claude extracts structured fields (title, summary, rationale, owner, tags, category)
4. Voyage AI generates embeddings for vector search
5. Jira/GitHub references are enriched with metadata
6. Decisions are searchable via hybrid search (vector + full-text + tags)

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

### 3. Run database migrations

```bash
docker compose -f docker-compose.production.yml exec backend \
  alembic -c /app/alembic.ini upgrade head
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
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for Claude |
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

```bash
cd backend
pytest
```

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
