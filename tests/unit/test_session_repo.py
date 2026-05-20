"""Unit tests for RedisSessionRepository using fakeredis."""
import pytest
from unittest.mock import AsyncMock, MagicMock

import redis.exceptions as redis_exc

from latte_graph_redis.domain.exceptions import RedisUnavailableError, SessionKeyError
from latte_graph_redis.infrastructure.session_repo import RedisSessionRepository

UID = "user-test-001"


# ============================================================
# Messages
# ============================================================

async def test_message_cap_enforced_after_25_appends(repo):
    """25 appends must result in exactly 20 messages (sliding window)."""
    for i in range(25):
        await repo.append_message(UID, f'{{"msg": {i}}}')
    messages = await repo.get_messages(UID)
    assert len(messages) == 20


async def test_message_cap_keeps_most_recent(repo):
    """After 25 appends, message 5 is the oldest retained (index 0)."""
    for i in range(25):
        await repo.append_message(UID, f'{{"msg": {i}}}')
    messages = await repo.get_messages(UID)
    # First retained message is #5 (0-indexed: 25 - 20 = 5)
    assert '"msg": 5' in messages[0]
    assert '"msg": 24' in messages[-1]


async def test_get_messages_empty_when_no_key(repo):
    assert await repo.get_messages("nonexistent-user") == []


async def test_append_and_retrieve_single_message(repo):
    await repo.append_message(UID, '{"role": "user", "content": "hello"}')
    messages = await repo.get_messages(UID)
    assert len(messages) == 1
    assert '"role": "user"' in messages[0]


# ============================================================
# Agent state
# ============================================================

async def test_set_get_state_round_trip(repo):
    await repo.set_state(UID, {"phase": "idle", "intent": "query"})
    state = await repo.get_state(UID)
    assert state["phase"] == "idle"
    assert state["intent"] == "query"


async def test_get_state_empty_when_no_key(repo):
    assert await repo.get_state("nonexistent-user") == {}


async def test_set_state_merges_fields(repo):
    await repo.set_state(UID, {"phase": "idle"})
    await repo.set_state(UID, {"intent": "query"})
    state = await repo.get_state(UID)
    assert state["phase"] == "idle"
    assert state["intent"] == "query"


# ============================================================
# String keys
# ============================================================

async def test_last_query_round_trip(repo):
    await repo.set_last_query(UID, "show total revenue by month")
    assert await repo.get_last_query(UID) == "show total revenue by month"


async def test_last_query_none_when_absent(repo):
    assert await repo.get_last_query("nonexistent-user") is None


async def test_last_chart_round_trip(repo):
    await repo.set_last_chart(UID, '{"type": "bar", "data": {}}')
    assert await repo.get_last_chart(UID) == '{"type": "bar", "data": {}}'


async def test_last_chart_none_when_absent(repo):
    assert await repo.get_last_chart("nonexistent-user") is None


async def test_kg_cache_round_trip(repo):
    await repo.set_kg_cache(UID, '{"nodes": [], "edges": []}')
    assert await repo.get_kg_cache(UID) == '{"nodes": [], "edges": []}'


async def test_kg_cache_none_when_absent(repo):
    assert await repo.get_kg_cache("nonexistent-user") is None


# ============================================================
# Active datasets
# ============================================================

async def test_add_get_active_datasets(repo):
    await repo.add_active_dataset(UID, "ds-001")
    await repo.add_active_dataset(UID, "ds-002")
    datasets = await repo.get_active_datasets(UID)
    assert {"ds-001", "ds-002"} == datasets


async def test_add_active_dataset_idempotent(repo):
    await repo.add_active_dataset(UID, "ds-001")
    await repo.add_active_dataset(UID, "ds-001")
    datasets = await repo.get_active_datasets(UID)
    assert len(datasets) == 1


async def test_get_active_datasets_empty_when_absent(repo):
    assert await repo.get_active_datasets("nonexistent-user") == set()


# ============================================================
# Pending KG
# ============================================================

async def test_append_get_pending_kg(repo):
    await repo.append_pending_kg(UID, '{"from": "sales", "to": "customers"}')
    await repo.append_pending_kg(UID, '{"from": "orders", "to": "products"}')
    pending = await repo.get_pending_kg(UID)
    assert len(pending) == 2
    assert '"from": "sales"' in pending[0]


async def test_get_pending_kg_empty_when_absent(repo):
    assert await repo.get_pending_kg("nonexistent-user") == []


# ============================================================
# Session lifecycle
# ============================================================

async def test_close_session_deletes_all_keys(repo):
    await repo.append_message(UID, '{"msg": "hello"}')
    await repo.set_state(UID, {"phase": "idle"})
    await repo.add_active_dataset(UID, "ds-001")
    await repo.close_session(UID)
    assert await repo.get_messages(UID) == []
    assert await repo.get_state(UID) == {}
    assert await repo.get_active_datasets(UID) == set()


async def test_reset_ttl_does_not_raise(repo):
    """reset_ttl must not raise even if keys do not exist."""
    await repo.reset_ttl(UID)  # keys absent — EXPIRE on non-existent key is no-op


# ============================================================
# Error mapping
# ============================================================

@pytest.fixture
def failing_repo():
    """Repo whose client raises ConnectionError on every call."""
    client = MagicMock()
    err = redis_exc.ConnectionError("connection refused")
    for method in [
        "rpush", "lrange", "ltrim", "expire", "hset", "hgetall",
        "set", "get", "sadd", "smembers", "delete",
    ]:
        setattr(client, method, AsyncMock(side_effect=err))
    pipe_mock = MagicMock()
    pipe_mock.expire = MagicMock()
    pipe_mock.execute = AsyncMock(side_effect=err)
    client.pipeline = MagicMock(return_value=pipe_mock)
    return RedisSessionRepository(client)


async def test_all_methods_map_connection_error(failing_repo):
    r = failing_repo
    with pytest.raises(RedisUnavailableError):
        await r.append_message("u", "m")
    with pytest.raises(RedisUnavailableError):
        await r.get_messages("u")
    with pytest.raises(RedisUnavailableError):
        await r.set_state("u", {"k": "v"})
    with pytest.raises(RedisUnavailableError):
        await r.get_state("u")
    with pytest.raises(RedisUnavailableError):
        await r.set_last_query("u", "q")
    with pytest.raises(RedisUnavailableError):
        await r.get_last_query("u")
    with pytest.raises(RedisUnavailableError):
        await r.set_last_chart("u", "c")
    with pytest.raises(RedisUnavailableError):
        await r.get_last_chart("u")
    with pytest.raises(RedisUnavailableError):
        await r.set_kg_cache("u", "k")
    with pytest.raises(RedisUnavailableError):
        await r.get_kg_cache("u")
    with pytest.raises(RedisUnavailableError):
        await r.add_active_dataset("u", "d")
    with pytest.raises(RedisUnavailableError):
        await r.get_active_datasets("u")
    with pytest.raises(RedisUnavailableError):
        await r.append_pending_kg("u", "k")
    with pytest.raises(RedisUnavailableError):
        await r.get_pending_kg("u")
    with pytest.raises(RedisUnavailableError):
        await r.close_session("u")
    with pytest.raises(RedisUnavailableError):
        await r.reset_ttl("u")


async def test_wrongtype_response_raises_session_key_error():
    """WRONGTYPE ResponseError maps to non-fatal SessionKeyError."""
    client = MagicMock()
    client.lrange = AsyncMock(
        side_effect=redis_exc.ResponseError(
            "WRONGTYPE Operation against a key holding the wrong kind of value"
        )
    )
    repo = RedisSessionRepository(client)
    with pytest.raises(SessionKeyError):
        await repo.get_messages("u")


async def test_exceptions_inherit_latte_graph_error():
    from latte_graph_shared import LatteGraphError
    assert issubclass(RedisUnavailableError, LatteGraphError)
    assert issubclass(SessionKeyError, LatteGraphError)
