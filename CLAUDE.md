# latte-graph-redis — Claude Project Memory

Read `AGENTS.md` first. It contains read order, hard rules, DI pattern, run commands, and layer boundaries.

## Development Status

**v2.0.0 — PR-204 complete.**

| PR | What was built | Tests | Status |
|----|----------------|-------|--------|
| PR-204 | Full session state repository: exceptions, keys, client factory, session repo, interface | unit (fakeredis) + integration (testcontainers) + contract | ✅ done |

## Key Facts

- **Package**: `latte-graph-redis` (build order 04/15)
- **Version**: 2.0.0
- **Build system**: Poetry + hatchling
- **Coverage**: target ≥85%
- **No application layer** — pure infrastructure

## Important Implementation Notes

- `_map_redis_errors` decorator wraps every public method — NEVER add try/except inside methods
- `fakeredis[aioredis]` for unit tests; `testcontainers[redis]` for integration
- `asyncio_mode = "auto"` in pytest config — no `@pytest.mark.asyncio` needed on individual tests
- `decode_responses=True` on all clients — values always strings, never bytes
- `reset_ttl` uses `pipeline(transaction=False)` — non-transactional batch EXPIRE
- `close_session` uses `delete(*keys)` with spread — single DEL command for all 7 keys

## Scope

This lib owns:
- `RedisKeyBuilder` — all 7 key names + SESSION_TTL + MESSAGE_CAP constants
- `RedisClientFactory` — async Redis client factory
- `RedisSessionRepository` — all async operations on session keyspace
- `RedisUnavailableError` (fatal) + `SessionKeyError` (non-fatal)

This lib does NOT own:
- Session rebuild orchestration (PG → Redis on session start) → `latte-graph-memory`
- Domain models `ChatMessage`, `QueryResult`, `ChartSpec` → respective libs
- Long-term PostgreSQL writes → `latte-graph-postgres`
- KG construction → `latte-graph-kg`
- Insight extraction → `latte-graph-memory`

## Error Handling Pattern

```python
# Correct — errors surface from @_map_redis_errors decorator:
async def append_message(self, user_id: str, message_json: str) -> None:
    key = self._k.messages(user_id)
    await self._r.rpush(key, message_json)
    await self._r.ltrim(key, -MESSAGE_CAP, -1)
    await self._r.expire(key, SESSION_TTL)

# WRONG — never add try/except inside methods:
async def append_message(self, user_id: str, message_json: str) -> None:
    try:  # ← NEVER do this
        ...
    except redis.ConnectionError:
        raise RedisUnavailableError(...)
```

## Next Steps

1. Publish to private PyPI / test.pypi.org
2. Tag `v2.0.0`
3. Wire into `latte-graph-memory` (4.x) once memory lib is started
4. Add `remove_active_dataset()` + `clear_pending_kg()` in v2.1.0
