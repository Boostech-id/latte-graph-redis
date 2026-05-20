"""Integration tests using real Redis via testcontainers.

These tests require Docker to be running.
Skip with: pytest tests/unit/ tests/contract/ (unit-only run)
"""
import pytest

try:
    from testcontainers.redis import RedisContainer
    HAS_TESTCONTAINERS = True
except ImportError:
    HAS_TESTCONTAINERS = False

from latte_graph_redis.infrastructure.client import RedisClientFactory
from latte_graph_redis.infrastructure.keys import SESSION_TTL, RedisKeyBuilder
from latte_graph_redis.infrastructure.session_repo import RedisSessionRepository

UID_A = "user-integ-A"
UID_B = "user-integ-B"

pytestmark = pytest.mark.skipif(
    not HAS_TESTCONTAINERS,
    reason="testcontainers not installed",
)


@pytest.fixture(scope="module")
def redis_url():
    with RedisContainer() as container:
        yield container.get_connection_url()


@pytest.fixture
async def repo(redis_url):
    client = RedisClientFactory.create(redis_url)
    r = RedisSessionRepository(client)
    # Clean up before each test
    await r.close_session(UID_A)
    await r.close_session(UID_B)
    yield r
    await client.aclose()


async def test_full_lifecycle(repo):
    """Append → get → close lifecycle."""
    await repo.append_message(UID_A, '{"role": "user", "content": "hello"}')
    msgs = await repo.get_messages(UID_A)
    assert len(msgs) == 1
    await repo.close_session(UID_A)
    assert await repo.get_messages(UID_A) == []


async def test_ttl_set_on_write(repo):
    """TTL must be set and > 0 after a write."""
    await repo.append_message(UID_A, '{}')
    client = repo._r
    ttl = await client.ttl(RedisKeyBuilder.messages(UID_A))
    assert 0 < ttl <= SESSION_TTL


async def test_cross_user_isolation(repo):
    """Messages written for user A must not be visible to user B."""
    await repo.append_message(UID_A, '{"msg": "A only"}')
    msgs_b = await repo.get_messages(UID_B)
    assert msgs_b == []


async def test_message_cap_real_redis(repo):
    """MESSAGE_CAP = 20 enforced with real Redis."""
    for i in range(25):
        await repo.append_message(UID_A, f'{{"i": {i}}}')
    msgs = await repo.get_messages(UID_A)
    assert len(msgs) == 20


async def test_state_persistence(repo):
    """State hash round-trip with real Redis."""
    await repo.set_state(UID_A, {"phase": "active", "intent": "query"})
    state = await repo.get_state(UID_A)
    assert state["phase"] == "active"


async def test_active_datasets_isolation(repo):
    """Active datasets for user A not visible to user B."""
    await repo.add_active_dataset(UID_A, "ds-A")
    assert await repo.get_active_datasets(UID_B) == set()
