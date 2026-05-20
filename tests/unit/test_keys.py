"""Unit tests for RedisKeyBuilder, SESSION_TTL, MESSAGE_CAP."""
import pytest

from latte_graph_redis.infrastructure.keys import (
    MESSAGE_CAP,
    SESSION_TTL,
    RedisKeyBuilder,
)

UID = "user-abc-123"


def test_messages_key():
    assert RedisKeyBuilder.messages(UID) == f"latte:{UID}:session:messages"


def test_state_key():
    assert RedisKeyBuilder.state(UID) == f"latte:{UID}:session:state"


def test_last_query_key():
    assert RedisKeyBuilder.last_query(UID) == f"latte:{UID}:session:last_query"


def test_last_chart_key():
    assert RedisKeyBuilder.last_chart(UID) == f"latte:{UID}:session:last_chart"


def test_kg_cache_key():
    assert RedisKeyBuilder.kg_cache(UID) == f"latte:{UID}:session:kg_cache"


def test_pending_kg_key():
    assert RedisKeyBuilder.pending_kg(UID) == f"latte:{UID}:session:pending_kg"


def test_active_datasets_key():
    assert RedisKeyBuilder.active_datasets(UID) == f"latte:{UID}:session:active_datasets"


def test_all_session_keys_returns_7():
    keys = RedisKeyBuilder.all_session_keys(UID)
    assert len(keys) == 7


def test_all_session_keys_all_prefixed():
    keys = RedisKeyBuilder.all_session_keys(UID)
    assert all(k.startswith(f"latte:{UID}:session:") for k in keys)


def test_all_session_keys_all_unique():
    keys = RedisKeyBuilder.all_session_keys(UID)
    assert len(set(keys)) == 7


def test_session_ttl_value():
    assert SESSION_TTL == 86_400


def test_message_cap_value():
    assert MESSAGE_CAP == 20


def test_keys_differ_for_different_users():
    keys_a = set(RedisKeyBuilder.all_session_keys("alice"))
    keys_b = set(RedisKeyBuilder.all_session_keys("bob"))
    assert keys_a.isdisjoint(keys_b)
