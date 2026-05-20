# latte-graph-redis

```
     ( (
      ) )
  .........
  |       |]   LatteGraph
  |  ~~~  |    Redis Session Store
  `-------'

  latte:{user_id}:session:*
  ┌──────────────────────────┐
  │  messages    [List  20]  │
  │  state       [Hash    ]  │──► agent state
  │  last_query  [String  ]  │──► NL query cache
  │  last_chart  [String  ]  │──► chart spec cache
  │  kg_cache    [String  ]  │──► KG snapshot
  │  pending_kg  [List    ]  │──► awaiting approval
  │  active_ds   [Set     ]  │──► loaded datasets
  └──────────────────────────┘
         TTL = 24h
```

**latte-graph-redis** is the Redis session state bounded context for the LatteGraph platform.

It provides typed, async operations on the `latte:{user_id}:session:*` keyspace — managing hot session state (message history, agent state, KG cache, active datasets) across all agents in a user's active conversation.

---

## What It Does

| Component | Purpose |
|-----------|---------|
| `RedisKeyBuilder` | Single source of truth for all 7 key names |
| `RedisClientFactory` | Creates async Redis client with connection pool |
| `RedisSessionRepository` | All typed async CRUD operations on session keys |
| `RedisUnavailableError` | Fatal — connection lost, surface to caller |
| `SessionKeyError` | Non-fatal — key type mismatch (schema drift), log + continue |

## Session Flow

```
User turn starts
      │
      ▼
reset_ttl(user_id)          ← keep session alive (24h sliding)
      │
      ▼
get_messages(user_id)       ← load last 20 messages for LLM context
get_state(user_id)          ← load agent state machine
get_kg_cache(user_id)       ← load KG snapshot (skip rebuild from PG)
get_active_datasets(user_id)← which datasets are loaded in DuckDB
      │
      ▼
   [agents run]
      │
      ▼
append_message(user_id, q)  ← save user question
set_state(user_id, fields)  ← update agent state
set_last_query(user_id, q)  ← save NL query for follow-up context
set_last_chart(user_id, c)  ← save chart spec for UI re-render
append_message(user_id, a)  ← save agent answer
      │
      ▼
User session ends
      │
      ▼
close_session(user_id)      ← DEL all 7 keys
```

## Keyspace

All keys follow `latte:{user_id}:session:{name}`. TTL = **86 400s (24h)** reset on every write.

| Key | Redis type | Purpose | Constraint |
|-----|-----------|---------|-----------|
| `messages` | List | Chat history | LTRIM to last 20 (MESSAGE_CAP) |
| `state` | Hash | Agent state machine fields | HSET mapping |
| `last_query` | String | Last NL query text | SET with ex=TTL |
| `last_chart` | String | Last chart spec (JSON) | SET with ex=TTL |
| `kg_cache` | String | KG snapshot (JSON) | SET with ex=TTL |
| `pending_kg` | List | Pending relation candidates | RPUSH, no cap |
| `active_datasets` | Set | Approved dataset UUIDs | SADD, deduplicated |

## Error Handling

| Exception | Severity | Trigger | Action |
|-----------|---------|---------|--------|
| `RedisUnavailableError` | **Fatal** | `redis.ConnectionError` | Surface to user — session cannot continue |
| `SessionKeyError` | Non-fatal | `WRONGTYPE` ResponseError | Log warning + continue — schema drift |

Both inherit from `LatteGraphError` (latte-graph-shared).

## Hard Rules (Non-Configurable)

| Constraint | Value | Reason |
|-----------|-------|--------|
| MESSAGE_CAP | 20 | LLM context window budget |
| SESSION_TTL | 86 400s (24h) | Idle session cleanup |
| max_connections | 20 | Connection pool bound |
| decode_responses | True | String values always, no bytes.decode() |
| Keyspace prefix | `latte:{uid}:session:*` | Multi-tenant isolation |

**These are security boundaries — never make them configurable.**

## DDD Architecture

```
latte-graph-redis/
├── src/latte_graph_redis/
│   ├── domain/
│   │   └── exceptions.py    # RedisUnavailableError, SessionKeyError
│   ├── infrastructure/
│   │   ├── keys.py          # RedisKeyBuilder, SESSION_TTL, MESSAGE_CAP
│   │   ├── client.py        # RedisClientFactory
│   │   └── session_repo.py  # RedisSessionRepository
│   └── interface/
│       └── __init__.py      # 7 public exports
├── tests/
│   ├── unit/                # fakeredis (no Docker)
│   ├── integration/         # testcontainers[redis] (real Redis)
│   └── contract/            # __all__ surface contract
└── pyproject.toml
```

No `application/` layer — this lib is **pure infrastructure** (typed Redis client wrapper). No use cases, no domain models beyond exceptions.

## Install

```bash
poetry add latte-graph-redis
```

Or with UV:
```bash
uv pip install latte-graph-redis
```

## Quick Start

```python
from latte_graph_redis.interface import (
    RedisClientFactory,
    RedisSessionRepository,
)

# Create client + repo
client = RedisClientFactory.create("redis://localhost:6379/0")
repo = RedisSessionRepository(client)

# Append a message
await repo.append_message("user-123", '{"role": "user", "content": "show revenue"}')

# Get last 20 messages
messages = await repo.get_messages("user-123")

# Save agent state
await repo.set_state("user-123", {"phase": "active", "intent": "query"})

# Add active dataset
await repo.add_active_dataset("user-123", "ds-abc-456")

# End session
await repo.close_session("user-123")
```

## Testing

```bash
# Unit tests (fakeredis, no Docker required)
poetry run pytest tests/unit/ tests/contract/ -v --cov=latte_graph_redis --cov-report=term-missing

# Integration tests (requires Docker)
poetry run pytest tests/integration/ -v

# Full suite + coverage gate (≥85%)
poetry run pytest -v
```

## Version Roadmap

| Version | What changes |
|---------|-------------|
| **2.0.0** (current) | 7-key session keyspace; async only; fakeredis unit tests |
| **2.1.0** | Add `remove_active_dataset()` + `clear_pending_kg()` operations |
| **2.2.0** | Pipeline optimization: batch get all 7 keys in single round-trip |
| **4.x** (memory lib) | `latte-graph-memory` wraps this lib with session rebuild orchestration (PG → Redis on first turn) |

## Where This Fits

```
latte-graph-shared (1.x)
        │
        ▼
latte-graph-redis (2.x)  ← this lib
        │
        ▼
latte-graph-memory (4.x)  ← session rebuild orchestration
        │
        ▼
latte-graph-agent (4.x)   ← agent session facade
```

**This lib does NOT own:**
- Session rebuild (loading PG history into Redis on session start) → `latte-graph-memory`
- Domain models like `ChatMessage`, `QueryResult`, `ChartSpec` → respective libs
- Long-term storage → `latte-graph-postgres`
- KG construction → `latte-graph-kg`

---

**Build order:** 04 of 15 | **Version:** 2.x | **Python:** ≥3.11 | **Coverage:** ≥85%
