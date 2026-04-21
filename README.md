# Agent Discovery + Usage Platform

A mini agent registry with usage tracking, built with FastAPI + SQLite.

## Setup

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the interactive Swagger UI.

Create a `.env` file with:

GEMINI_API_KEY=your-key-here

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | /agents | Register a new agent (tags auto-generated via Gemini) |
| GET | /agents | List all agents |
| GET | /search?q=... | Search agents by name, description, or tags (case-insensitive) |
| POST | /usage | Log a call between agents (idempotent via request_id) |
| GET | /usage-summary | Aggregated units consumed per target agent |

## Design Decisions

- **SQLite** for zero-setup persistence; SQLAlchemy ORM means swapping to Postgres is a one-line change.
- **Gemini** (gemini-2.5-flash-lite) for tag generation. Falls back to `"general"` if the LLM is unavailable, so agent registration never fails on an external dependency.
- **Idempotency** uses `request_id` as the primary key on the usage table. Duplicate IDs with identical payloads are silently ignored; duplicate IDs with mismatched payloads return 409 Conflict to catch client bugs.
- **Aggregation** is done in SQL (`GROUP BY`) rather than Python to scale with data size.

## Edge Cases Handled

- Duplicate agent name → 400
- Usage logged for unknown caller or target → 404
- Caller and target identical → 400
- Same `request_id` reused with different payload → 409
- LLM failure during tag generation → falls back to `"general"`
- Missing required fields → 422 (Pydantic validation)

## Design Questions

### 1. How would you extend this to support billing without double charging?

The existing `request_id` idempotency is the foundation — same ID always maps to the same billed event. For billing specifically, I'd add a `billed_at` timestamp and a separate `invoices` table so each usage row is marked as billed exactly once. A nightly job aggregates unbilled usage per caller into an invoice inside a DB transaction, flipping `billed_at` atomically. If the job crashes mid-run, it can safely re-run because already-billed rows are skipped. For stronger guarantees I'd wrap the billing job in a distributed lock (e.g., Redis) so two workers can't bill the same window simultaneously.

### 2. How would you store this data at 100K agents scale?

SQLite won't hold up I'd move to Postgres with indexes on `agents.name`, `usage.target`, and `usage.request_id`. Substring search on description doesn't scale, so I'd switch to Postgres full-text search (`tsvector`) or a dedicated search layer like OpenSearch/Elasticsearch for description + tag search. Usage rows grow fastest, so I'd partition the `usage` table by month and move old partitions to cold storage. For the aggregation endpoint, I'd maintain a rollup table (`daily_usage_per_target`) updated incrementally rather than scanning every row on each request. If usage volume gets truly large (millions/day), a write-optimized store like ClickHouse for analytics and Postgres for the agent registry is the clean split.
