"""Shared test fixtures for latte-graph-redis."""
import pytest
import fakeredis.aioredis as fakeredis_aio

from latte_graph_redis.infrastructure.session_repo import RedisSessionRepository

UID = "user-test-001"
UID_A = "user-test-A"
UID_B = "user-test-B"


@pytest.fixture
async def fake_client():
    """Return a fresh fakeredis async client with decode_responses=True."""
    client = fakeredis_aio.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
async def repo(fake_client):
    """Return a RedisSessionRepository backed by fakeredis."""
    return RedisSessionRepository(fake_client)
