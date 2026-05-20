from redis.asyncio import Redis, ConnectionPool


class RedisClientFactory:
    """Factory that creates a configured async Redis client from a URL.

    Configures a connection pool with ``max_connections=20`` and
    ``decode_responses=True`` so all values are returned as Python strings
    (no manual ``bytes.decode()`` required).

    All methods are static — instantiation is not required.

    Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
    Source: PR-204 | BRD.Arch.002 §Redis-client
    Since: latte-graph-redis 2.0.0
    """

    @staticmethod
    def create(url: str = "redis://localhost:6379/0") -> Redis:
        """Create an async Redis client with a bounded connection pool.

        Args:
            url: Redis connection URL.  Defaults to
                ``redis://localhost:6379/0`` (local development).
                In production pass the value from environment / config.

        Returns:
            Configured ``redis.asyncio.Redis`` instance with
            ``decode_responses=True`` and ``max_connections=20``.

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Redis-client
        Since: latte-graph-redis 2.0.0
        """
        pool = ConnectionPool.from_url(
            url,
            max_connections=20,
            decode_responses=True,
        )
        return Redis(connection_pool=pool)
