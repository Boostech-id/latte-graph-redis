import functools
from typing import Any

import redis.exceptions as redis_exc
from redis.asyncio import Redis

from latte_graph_redis.domain.exceptions import RedisUnavailableError, SessionKeyError
from latte_graph_redis.infrastructure.keys import MESSAGE_CAP, SESSION_TTL, RedisKeyBuilder


def _map_redis_errors(fn: Any) -> Any:
    """Decorator that maps Redis client exceptions to domain exceptions.

    Applied to EVERY public method on ``RedisSessionRepository``.  Error
    mapping is uniform — never add try/except inside individual methods.

    Mapping rules:
    - ``redis.exceptions.ConnectionError`` → ``RedisUnavailableError`` (fatal).
    - ``redis.exceptions.ResponseError`` with ``"WRONGTYPE"`` token →
      ``SessionKeyError`` (non-fatal — schema/type drift).
    - All other ``ResponseError`` variants propagate unchanged.

    Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
    Source: PR-204 | BRD.Arch.002 §Error-handling
    Since: latte-graph-redis 2.0.0
    """

    @functools.wraps(fn)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(self, *args, **kwargs)
        except redis_exc.ConnectionError as exc:
            raise RedisUnavailableError(str(exc)) from exc
        except redis_exc.ResponseError as exc:
            if "WRONGTYPE" in str(exc).upper():
                raise SessionKeyError(str(exc)) from exc
            raise

    return wrapper


class RedisSessionRepository:
    """Redis-backed session state store for active LatteGraph user sessions.

    Provides typed async operations on the ``latte:{user_id}:session:*``
    keyspace.  Each write resets the ``SESSION_TTL = 86 400s`` (24 h) expiry
    so that active sessions stay alive and idle sessions expire automatically.

    Keyspace summary (7 keys per user):

    +-----------------------+-----------+---------------------------------------------+
    | Key suffix            | Redis type| Purpose                                     |
    +=======================+===========+=============================================+
    | ``:messages``         | List      | Chat history — capped at MESSAGE_CAP = 20   |
    | ``:state``            | Hash      | Agent state machine fields (str → str)      |
    | ``:last_query``       | String    | Last NL query text                          |
    | ``:last_chart``       | String    | Last chart spec (JSON string)               |
    | ``:kg_cache``         | String    | KG snapshot (JSON string)                   |
    | ``:pending_kg``       | List      | Pending relation candidates (JSON strings)  |
    | ``:active_datasets``  | Set       | Approved dataset UUIDs                      |
    +-----------------------+-----------+---------------------------------------------+

    All methods raise ``RedisUnavailableError`` (fatal) on connection failure
    and ``SessionKeyError`` (non-fatal) on key-type mismatch, via the
    ``@_map_redis_errors`` decorator.

    This lib works with **raw JSON strings** — serialization/deserialization is
    the caller's responsibility.  Never import domain models from other libs here.

    Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
    Source: PR-204 | BRD.Arch.002 §Session-repository
    Since: latte-graph-redis 2.0.0
    """

    def __init__(self, client: Redis) -> None:
        """Initialise the repository with an async Redis client.

        Args:
            client: Configured ``redis.asyncio.Redis`` instance — use
                ``RedisClientFactory.create(url)`` for production or
                ``fakeredis.aioredis.FakeRedis`` for tests.

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        self._r = client
        self._k = RedisKeyBuilder

    # ------------------------------------------------------------------
    # Messages  (List, capped at MESSAGE_CAP)
    # ------------------------------------------------------------------

    @_map_redis_errors
    async def append_message(self, user_id: str, message_json: str) -> None:
        """Append a JSON message string to the session message list.

        Uses RPUSH + LTRIM to enforce ``MESSAGE_CAP = 20`` (sliding window —
        oldest messages are dropped).  Resets ``SESSION_TTL`` on the key.

        Args:
            user_id: Session owner identifier.
            message_json: JSON-serialized message string.  Caller handles
                serialization (e.g. ``json.dumps({"role": "user", ...})``).

        Raises:
            RedisUnavailableError: Redis connection failed (fatal).
            SessionKeyError: Key type mismatch — schema drift (non-fatal).

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        key = self._k.messages(user_id)
        await self._r.rpush(key, message_json)
        await self._r.ltrim(key, -MESSAGE_CAP, -1)
        await self._r.expire(key, SESSION_TTL)

    @_map_redis_errors
    async def get_messages(self, user_id: str) -> list[str]:
        """Return all messages in the session message list (LRANGE 0 -1).

        Args:
            user_id: Session owner identifier.

        Returns:
            List of JSON-serialized message strings in append order.
            Returns an empty list if the key does not exist.

        Raises:
            RedisUnavailableError: Redis connection failed (fatal).
            SessionKeyError: Key type mismatch — schema drift (non-fatal).

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        return await self._r.lrange(self._k.messages(user_id), 0, -1)

    # ------------------------------------------------------------------
    # Agent state  (Hash)
    # ------------------------------------------------------------------

    @_map_redis_errors
    async def set_state(self, user_id: str, fields: dict[str, str]) -> None:
        """Write agent state fields to the session state hash (HSET mapping).

        Merges ``fields`` into the existing hash — existing fields not in
        ``fields`` are preserved.  Resets ``SESSION_TTL``.

        Args:
            user_id: Session owner identifier.
            fields: String-to-string mapping of agent state fields.

        Raises:
            RedisUnavailableError: Redis connection failed (fatal).
            SessionKeyError: Key type mismatch — schema drift (non-fatal).

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        key = self._k.state(user_id)
        await self._r.hset(key, mapping=fields)
        await self._r.expire(key, SESSION_TTL)

    @_map_redis_errors
    async def get_state(self, user_id: str) -> dict[str, str]:
        """Return all agent state fields from the session state hash (HGETALL).

        Args:
            user_id: Session owner identifier.

        Returns:
            String-to-string dict of all hash fields.
            Returns an empty dict if the key does not exist.

        Raises:
            RedisUnavailableError: Redis connection failed (fatal).
            SessionKeyError: Key type mismatch — schema drift (non-fatal).

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        return await self._r.hgetall(self._k.state(user_id))

    # ------------------------------------------------------------------
    # String keys  (last_query, last_chart, kg_cache)
    # ------------------------------------------------------------------

    @_map_redis_errors
    async def set_last_query(self, user_id: str, value: str) -> None:
        """Persist the last natural-language query string (SET with SESSION_TTL).

        Args:
            user_id: Session owner identifier.
            value: Raw NL query string from the user's last turn.

        Raises:
            RedisUnavailableError: Redis connection failed (fatal).
            SessionKeyError: Key type mismatch — schema drift (non-fatal).

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        await self._r.set(self._k.last_query(user_id), value, ex=SESSION_TTL)

    @_map_redis_errors
    async def get_last_query(self, user_id: str) -> str | None:
        """Return the last natural-language query string, or None if absent.

        Args:
            user_id: Session owner identifier.

        Returns:
            Stored NL query string, or ``None`` if key does not exist.

        Raises:
            RedisUnavailableError: Redis connection failed (fatal).
            SessionKeyError: Key type mismatch — schema drift (non-fatal).

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        return await self._r.get(self._k.last_query(user_id))

    @_map_redis_errors
    async def set_last_chart(self, user_id: str, value: str) -> None:
        """Persist the last chart specification string (SET with SESSION_TTL).

        Args:
            user_id: Session owner identifier.
            value: Serialized chart spec string (JSON from latte-graph-viz).

        Raises:
            RedisUnavailableError: Redis connection failed (fatal).
            SessionKeyError: Key type mismatch — schema drift (non-fatal).

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        await self._r.set(self._k.last_chart(user_id), value, ex=SESSION_TTL)

    @_map_redis_errors
    async def get_last_chart(self, user_id: str) -> str | None:
        """Return the last chart specification string, or None if absent.

        Args:
            user_id: Session owner identifier.

        Returns:
            Stored chart spec string, or ``None`` if key does not exist.

        Raises:
            RedisUnavailableError: Redis connection failed (fatal).
            SessionKeyError: Key type mismatch — schema drift (non-fatal).

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        return await self._r.get(self._k.last_chart(user_id))

    @_map_redis_errors
    async def set_kg_cache(self, user_id: str, value: str) -> None:
        """Persist the knowledge-graph relation cache string (SET with SESSION_TTL).

        Args:
            user_id: Session owner identifier.
            value: Serialized KG snapshot string (JSON from latte-graph-kg).

        Raises:
            RedisUnavailableError: Redis connection failed (fatal).
            SessionKeyError: Key type mismatch — schema drift (non-fatal).

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        await self._r.set(self._k.kg_cache(user_id), value, ex=SESSION_TTL)

    @_map_redis_errors
    async def get_kg_cache(self, user_id: str) -> str | None:
        """Return the knowledge-graph relation cache string, or None if absent.

        Args:
            user_id: Session owner identifier.

        Returns:
            Stored KG cache string, or ``None`` if key does not exist.

        Raises:
            RedisUnavailableError: Redis connection failed (fatal).
            SessionKeyError: Key type mismatch — schema drift (non-fatal).

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        return await self._r.get(self._k.kg_cache(user_id))

    # ------------------------------------------------------------------
    # Active datasets  (Set)
    # ------------------------------------------------------------------

    @_map_redis_errors
    async def add_active_dataset(self, user_id: str, dataset_id: str) -> None:
        """Add a dataset ID to the session active-datasets set (SADD + EXPIRE).

        Idempotent — adding the same dataset ID twice is a no-op.
        Resets ``SESSION_TTL``.

        Args:
            user_id: Session owner identifier.
            dataset_id: UUID string of the approved dataset to add.

        Raises:
            RedisUnavailableError: Redis connection failed (fatal).
            SessionKeyError: Key type mismatch — schema drift (non-fatal).

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        key = self._k.active_datasets(user_id)
        await self._r.sadd(key, dataset_id)
        await self._r.expire(key, SESSION_TTL)

    @_map_redis_errors
    async def get_active_datasets(self, user_id: str) -> set[str]:
        """Return all active dataset IDs for the session (SMEMBERS).

        Args:
            user_id: Session owner identifier.

        Returns:
            Set of dataset ID strings.  Returns an empty set if key absent.

        Raises:
            RedisUnavailableError: Redis connection failed (fatal).
            SessionKeyError: Key type mismatch — schema drift (non-fatal).

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        return await self._r.smembers(self._k.active_datasets(user_id))

    # ------------------------------------------------------------------
    # Pending KG  (List)
    # ------------------------------------------------------------------

    @_map_redis_errors
    async def append_pending_kg(self, user_id: str, relation_json: str) -> None:
        """Append a JSON relation string to the pending KG list (RPUSH + EXPIRE).

        Args:
            user_id: Session owner identifier.
            relation_json: JSON-serialized relation candidate awaiting
                user approval (from latte-graph-kg).

        Raises:
            RedisUnavailableError: Redis connection failed (fatal).
            SessionKeyError: Key type mismatch — schema drift (non-fatal).

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        key = self._k.pending_kg(user_id)
        await self._r.rpush(key, relation_json)
        await self._r.expire(key, SESSION_TTL)

    @_map_redis_errors
    async def get_pending_kg(self, user_id: str) -> list[str]:
        """Return all pending KG relation strings (LRANGE 0 -1).

        Args:
            user_id: Session owner identifier.

        Returns:
            List of JSON-serialized relation strings in append order.
            Returns an empty list if key does not exist.

        Raises:
            RedisUnavailableError: Redis connection failed (fatal).
            SessionKeyError: Key type mismatch — schema drift (non-fatal).

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        return await self._r.lrange(self._k.pending_kg(user_id), 0, -1)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    @_map_redis_errors
    async def close_session(self, user_id: str) -> None:
        """Delete all 7 session keys for the user (DEL).

        After this call all GET methods return None/empty for the user.
        DEL is atomic — all keys are removed in a single command.

        Args:
            user_id: Session owner identifier.

        Raises:
            RedisUnavailableError: Redis connection failed (fatal).

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        keys = self._k.all_session_keys(user_id)
        if keys:
            await self._r.delete(*keys)

    @_map_redis_errors
    async def reset_ttl(self, user_id: str) -> None:
        """Reset SESSION_TTL on all 7 session keys via a pipelined EXPIRE.

        Uses a non-transactional pipeline to batch all 7 EXPIRE commands
        into a single round-trip.  Call this at the start of each turn to
        keep active sessions alive.

        Args:
            user_id: Session owner identifier.

        Raises:
            RedisUnavailableError: Redis connection failed (fatal).

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Session-repository
        Since: latte-graph-redis 2.0.0
        """
        pipe = self._r.pipeline(transaction=False)
        for key in self._k.all_session_keys(user_id):
            pipe.expire(key, SESSION_TTL)
        await pipe.execute()
