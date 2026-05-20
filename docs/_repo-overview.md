# latte-graph-redis — Repo Overview

## Identity
| Field        | Value                          |
|--------------|--------------------------------|
| Repo         | latte-graph-redis              |
| Phase        | 1 — libs                       |
| Build Order  | 04 of 15                       |
| Version      | 2.x series                     |
| PyPI package | `latte-graph-redis`            |

## Purpose
Redis session state bounded context. Provides typed, async operations on the
`latte:{user_id}:session:*` keyspace. Owns key naming (`RedisKeyBuilder`), TTL management
(24h / 86,400s), session lifecycle (append, get, close), and Redis error classification.

Does NOT own: session rebuild orchestration (loading from PG on session start) — that belongs
to `latte-graph-memory` (4.x). Does not own domain models like `ChatMessage`, `QueryResult`,
`ChartSpec`. Works with raw JSON strings — serialization/deserialization is the caller's concern.

## Dependency Chain

**Depends on:**
- `latte-graph-shared` (^1.0) — `LatteGraphError`
- `redis[hiredis]` (^5.0) — async Redis client (`redis.asyncio`)

**Required by (unblocked after PR-204 DONE):**
- `latte-graph-memory` (4.x) — wraps `RedisSessionRepository` in high-level session orchestration
- `latte-graph-agent` (4.x) — agent state management via memory lib

## PRs in This Repo

| PR     | Title                    | BRD Series | Status  |
|--------|--------------------------|------------|---------|
| PR-204 | Session State Repository | PR-200     | pending |

Single PR — redis lib is a thin, cohesive layer with no complex sub-concerns.

**Gate rules:**
- PR-101 DONE (shared v1.0) → PR-204 may start
- PR-204 DONE → `latte-graph-redis` v2.0.0 published → unblocks `latte-graph-memory` (4.x)

## Redis Keyspace Owned

All keys user-scoped under `latte:{user_id}:session:*`. TTL = 24h (86,400s), reset on every write.

| Key | Redis Type | Purpose | Operation |
|-----|-----------|---------|-----------|
| `latte:{user_id}:session:messages` | List (max 20) | Chat message history (JSON strings) | RPUSH + LTRIM 20 |
| `latte:{user_id}:session:state` | Hash | Agent state machine fields | HSET / HGETALL |
| `latte:{user_id}:session:last_query` | String | Last QueryResult (JSON) | SET / GET |
| `latte:{user_id}:session:last_chart` | String | Last ChartSpec (JSON) | SET / GET |
| `latte:{user_id}:session:kg_cache` | String | NetworkX graph snapshot (JSON/bytes) | SET / GET |
| `latte:{user_id}:session:pending_kg` | List | Pending KG relations awaiting approval | RPUSH / LRANGE |
| `latte:{user_id}:session:active_datasets` | Set | Approved dataset UUIDs | SADD / SMEMBERS |

## Boundaries

**Owns:**
- `RedisUnavailableError` — fatal; raised on `redis.exceptions.ConnectionError`
- `SessionKeyError` — non-fatal; raised on key type mismatch or unexpected key errors
- `RedisKeyBuilder` — single source of truth for all key names; `SESSION_TTL = 86400`; `MESSAGE_CAP = 20`
- `RedisClientFactory` — creates async `Redis` client from URL; configures connection pool (`max_connections=20`, `decode_responses=True`)
- `RedisSessionRepository` — all typed async operations on session keyspace

**Does NOT own:**
- Session rebuild orchestration (load from PG → Redis on session start) — `latte-graph-memory`
- `ChatMessage`, `QueryResult`, `ChartSpec` domain models — respective libs
- Insight extraction or Qdrant operations — `latte-graph-memory` / `latte-graph-rag`
- Long-term PostgreSQL writes — `latte-graph-postgres`

## Module Structure

```
latte-graph-redis/
├── src/latte_graph_redis/
│   ├── domain/
│   │   └── exceptions.py    # RedisUnavailableError, SessionKeyError  [PR-204]
│   ├── infrastructure/
│   │   ├── keys.py          # RedisKeyBuilder, SESSION_TTL, MESSAGE_CAP  [PR-204]
│   │   ├── client.py        # RedisClientFactory  [PR-204]
│   │   └── session_repo.py  # RedisSessionRepository  [PR-204]
│   └── interface/
│       └── __init__.py      # public surface  [PR-204]
├── tests/
│   ├── unit/
│   │   ├── test_keys.py           # [PR-204]
│   │   └── test_session_repo.py   # fakeredis  [PR-204]
│   ├── integration/
│   │   └── test_redis_session.py  # real Redis via testcontainers  [PR-204]
│   ├── contract/
│   │   └── test_interface.py      # [PR-204]
│   └── conftest.py
├── pyproject.toml
└── .github/workflows/test.yml
```

Note: No `application/` layer — lib is pure infrastructure (typed Redis client wrapper).

## Security Hardcodes (non-configurable)

| Constraint | Value | Location |
|-----------|-------|----------|
| Message cap | `MESSAGE_CAP = 20` | `infrastructure/keys.py` |
| Session TTL | `SESSION_TTL = 86400` (24h) | `infrastructure/keys.py` |
| Key namespace | `latte:{user_id}:session:*` | `infrastructure/keys.py` |
| Connection pool | `max_connections=20`, `decode_responses=True` | `infrastructure/client.py` |

## Error Handling

| Exception | Severity | Trigger | Action |
|-----------|---------|---------|--------|
| `RedisUnavailableError` | **Fatal** | `redis.exceptions.ConnectionError` | Surface to user |
| `SessionKeyError` | Non-fatal | Key type mismatch, unexpected Redis errors | Log warning + continue |

## TDD Requirements

- Coverage ≥ 85%
- `test_keys.py`: each method returns correct `latte:{uid}:session:<name>` format; `all_session_keys` returns exactly 7 keys
- `test_session_repo.py` (fakeredis): LTRIM enforced after 25 appends (len ≤ 20); set/get_state round-trip; add/get_active_datasets; close_session deletes all keys; `ConnectionError` → `RedisUnavailableError`
- Integration: real Redis via `testcontainers[redis]`; full lifecycle; TTL verified via `TTL` command; cross-user isolation
- Contract: all `__all__` symbols importable; no private `_` symbols in `__all__`

## pyproject.toml Skeleton

```toml
[tool.poetry]
name = "latte-graph-redis"
version = "2.0.0"
description = "Redis session state repository — typed async operations on latte session keyspace"
packages = [{ include = "latte_graph_redis", from = "src" }]

[tool.poetry.dependencies]
python = ">=3.11"
latte-graph-shared = "^1.0"
redis = {extras = ["hiredis"], version = "^5.0"}

[tool.poetry.group.dev.dependencies]
pytest = ">=8.0"
pytest-cov = ">=5.0"
pytest-asyncio = ">=0.23"
fakeredis = {extras = ["aioredis"], version = ">=2.20"}
testcontainers = {extras = ["redis"], version = ">=4.0"}
import-linter = ">=2.0"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "--cov=latte_graph_redis --cov-fail-under=85"
asyncio_mode = "auto"
```

## BRD References

| Spec | Section | Topic |
|------|---------|-------|
| BRD.Master.001 | §PR-204 | PR assignment for redis lib |
| BRD.Arch.002 | §Redis keyspace | Key naming, TTL, session state fields |
| BRD.Arch.002 | §Session rebuild | Per-turn update flow, LTRIM 20, fire-and-forget |
| BRD.Arch.002 | §Error handling | Fatal vs non-fatal memory errors |
| BRD.Arch.001 | §TDD | ≥85% coverage per lib |

## Phase Gate

`latte-graph-redis v2.0.0` published (after PR-204 DONE) → unblocks:
- `latte-graph-memory` (4.x) — high-level session orchestration
- `latte-graph-agent` (4.x) — agent state management via memory lib
