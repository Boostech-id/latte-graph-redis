# latte-graph-redis — Agentic Worker Instructions

## Read Order

1. `README.md` — purpose, keyspace, flow, version roadmap
2. `pyproject.toml` — dependencies, tool config, coverage gate
3. `src/latte_graph_redis/interface/__init__.py` — public contract (__all__)
4. `src/latte_graph_redis/domain/exceptions.py` — error hierarchy
5. `src/latte_graph_redis/infrastructure/keys.py` — RedisKeyBuilder, SESSION_TTL, MESSAGE_CAP
6. `src/latte_graph_redis/infrastructure/client.py` — RedisClientFactory
7. `src/latte_graph_redis/infrastructure/session_repo.py` — RedisSessionRepository
8. `tests/` — test suite (fakeredis unit, testcontainers integration, contract)

## Hard Rules

- **No application layer** — this lib is pure infrastructure. No use cases, no domain models beyond exceptions.
- **Raw JSON strings only** — this lib stores and returns strings. Serialization/deserialization is the caller's concern. NEVER parse JSON inside this lib.
- **`@_map_redis_errors` on EVERY public method** — never add try/except inside individual methods. Error mapping must be uniform.
- **`MESSAGE_CAP = 20` is non-configurable** — LTRIM enforced on every `append_message` call.
- **`SESSION_TTL = 86400` is non-configurable** — expire reset on every write.
- **Key namespace `latte:{user_id}:session:*` is non-negotiable** — never construct key strings outside `RedisKeyBuilder`.
- **`reset_ttl` uses pipelined EXPIRE** — single round-trip for all 7 keys, non-transactional.
- **All exceptions inherit `LatteGraphError`** — never raise plain `Exception`.
- **`RedisUnavailableError` is fatal** — propagate, do not catch.
- **`SessionKeyError` is non-fatal** — log warning + continue. Never re-raise.

## DI Pattern

Inject client via constructor — never import `redis.asyncio.Redis` directly in production callers:

```python
from latte_graph_redis.interface import RedisClientFactory, RedisSessionRepository

client = RedisClientFactory.create("redis://localhost:6379/0")
repo = RedisSessionRepository(client)
```

## Run Commands

```bash
# Install
poetry install --with dev

# Unit tests only (no Docker needed)
poetry run pytest tests/unit/ tests/contract/ -v --cov=latte_graph_redis --cov-report=term-missing

# Integration tests (Docker required for testcontainers)
poetry run pytest tests/integration/ -v

# Full suite + coverage gate (≥85%)
poetry run pytest -v

# Import boundaries
poetry run lint-imports
```

## Layer Boundaries (import-linter)

```
domain         → MUST NOT import from infrastructure
infrastructure → may import domain only
interface      → re-exports from domain + infrastructure (only exports, no logic)
```

## Session Keyspace (all 7 keys)

| Key | Redis type | Operation |
|-----|-----------|-----------|
| `latte:{uid}:session:messages` | List | RPUSH + LTRIM(20) + EXPIRE |
| `latte:{uid}:session:state` | Hash | HSET mapping + EXPIRE |
| `latte:{uid}:session:last_query` | String | SET ex=TTL |
| `latte:{uid}:session:last_chart` | String | SET ex=TTL |
| `latte:{uid}:session:kg_cache` | String | SET ex=TTL |
| `latte:{uid}:session:pending_kg` | List | RPUSH + EXPIRE |
| `latte:{uid}:session:active_datasets` | Set | SADD + EXPIRE |

## Test Strategy

| Suite | Tool | What it tests |
|-------|------|--------------|
| `tests/unit/` | `fakeredis[aioredis]` | All repo methods, error mapping, MESSAGE_CAP enforcement |
| `tests/integration/` | `testcontainers[redis]` | Real Redis: full lifecycle, TTL via `TTL` command, cross-user isolation |
| `tests/contract/` | pytest | `__all__` surface — all 7 symbols importable, no private symbols |

## PR Gate Chain

```
PR-101 (shared v1.0) DONE
  → PR-204 (this lib) → latte-graph-redis v2.0.0 published
      → latte-graph-memory (4.x) unblocked
      → latte-graph-agent (4.x) unblocked
```
