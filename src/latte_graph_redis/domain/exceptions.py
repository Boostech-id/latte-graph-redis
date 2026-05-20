from latte_graph_shared import LatteGraphError


class RedisUnavailableError(LatteGraphError):
    """Redis connection is unavailable — fatal, propagate to caller.

    Raised when ``redis.exceptions.ConnectionError`` is caught inside
    ``RedisSessionRepository``. Callers MUST surface this error — the session
    cannot proceed without a live Redis connection.

    Inherits from ``LatteGraphError`` (latte-graph-shared) so that the top-level
    error handler can distinguish platform errors from unexpected exceptions.

    Raised by: ``RedisSessionRepository`` (all public methods via ``@_map_redis_errors``).

    Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
    Source: PR-204 | BRD.Arch.002 §Error-handling
    Since: latte-graph-redis 2.0.0
    """

    def __init__(self, message: str = "Redis connection unavailable") -> None:
        super().__init__(message)


class SessionKeyError(LatteGraphError):
    """Redis key type mismatch — non-fatal schema drift.

    Raised when ``redis.exceptions.ResponseError`` contains the token
    ``"WRONGTYPE"``, indicating a key exists with a different Redis data
    structure than the caller expected (e.g. LRANGE on a String key).

    This is non-fatal: callers should log the warning and continue.  It
    typically indicates stale data from a schema migration.

    Raised by: ``RedisSessionRepository`` (all public methods via ``@_map_redis_errors``).

    Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
    Source: PR-204 | BRD.Arch.002 §Error-handling
    Since: latte-graph-redis 2.0.0
    """

    def __init__(self, message: str = "Redis key type mismatch") -> None:
        super().__init__(message)
