SESSION_TTL: int = 86_400
"""Session key expiry in seconds (24 hours).

Hard-coded — non-configurable.  All session keys are set with this TTL on
every write so that an idle session expires automatically after 24 hours.

Security note: never expose TTL as a config value — it is a safety boundary.

Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
Source: PR-204 | BRD.Arch.002 §Redis-keyspace
Since: latte-graph-redis 2.0.0
"""

MESSAGE_CAP: int = 20
"""Maximum number of messages retained in the session message list.

Hard-coded — non-configurable.  Enforced via LTRIM after every RPUSH so the
list never grows beyond 20 entries (sliding window = last 20 messages).

Security note: never expose MESSAGE_CAP as a config value.

Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
Source: PR-204 | BRD.Arch.002 §Redis-keyspace
Since: latte-graph-redis 2.0.0
"""


class RedisKeyBuilder:
    """Builds all Redis key strings for the LatteGraph session keyspace.

    Every key follows the pattern ``latte:{user_id}:session:{name}``.
    All methods are static — no instance state required.

    The class is the single source of truth for key names.  Any consumer
    that needs a Redis key MUST call a method here; never construct key
    strings inline.

    Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
    Source: PR-204 | BRD.Arch.002 §Redis-keyspace
    Since: latte-graph-redis 2.0.0
    """

    PREFIX = "latte"

    @staticmethod
    def messages(user_id: str) -> str:
        """Return the Redis key for the session message list.

        Redis type: List (max ``MESSAGE_CAP`` = 20 entries, LTRIM on append).

        Args:
            user_id: Owning user identifier.

        Returns:
            Key string ``latte:{user_id}:session:messages``.

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Redis-keyspace
        Since: latte-graph-redis 2.0.0
        """
        return f"latte:{user_id}:session:messages"

    @staticmethod
    def state(user_id: str) -> str:
        """Return the Redis key for the agent state hash.

        Redis type: Hash (HSET / HGETALL).  Stores agent state machine fields
        as string-to-string pairs (e.g. ``phase``, ``intent``).

        Args:
            user_id: Owning user identifier.

        Returns:
            Key string ``latte:{user_id}:session:state``.

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Redis-keyspace
        Since: latte-graph-redis 2.0.0
        """
        return f"latte:{user_id}:session:state"

    @staticmethod
    def last_query(user_id: str) -> str:
        """Return the Redis key for the last natural-language query string.

        Redis type: String (SET / GET).  Stores the raw NL query submitted
        by the user in the previous turn so agents can provide context-aware
        follow-up answers.

        Args:
            user_id: Owning user identifier.

        Returns:
            Key string ``latte:{user_id}:session:last_query``.

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Redis-keyspace
        Since: latte-graph-redis 2.0.0
        """
        return f"latte:{user_id}:session:last_query"

    @staticmethod
    def last_chart(user_id: str) -> str:
        """Return the Redis key for the last chart specification string.

        Redis type: String (SET / GET).  Stores the serialized chart spec
        (JSON) so the UI can re-render the last chart without re-running
        the query.

        Args:
            user_id: Owning user identifier.

        Returns:
            Key string ``latte:{user_id}:session:last_chart``.

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Redis-keyspace
        Since: latte-graph-redis 2.0.0
        """
        return f"latte:{user_id}:session:last_chart"

    @staticmethod
    def kg_cache(user_id: str) -> str:
        """Return the Redis key for the knowledge-graph relation cache string.

        Redis type: String (SET / GET).  Stores the serialized KG snapshot
        (JSON) so the agent can inject graph context without rebuilding from
        PostgreSQL on every turn.  TTL = ``SESSION_TTL`` (1 h cache in agent,
        24 h here).

        Args:
            user_id: Owning user identifier.

        Returns:
            Key string ``latte:{user_id}:session:kg_cache``.

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Redis-keyspace
        Since: latte-graph-redis 2.0.0
        """
        return f"latte:{user_id}:session:kg_cache"

    @staticmethod
    def pending_kg(user_id: str) -> str:
        """Return the Redis key for the pending KG relations list.

        Redis type: List (RPUSH / LRANGE).  Stores JSON-serialized relation
        candidates awaiting user approval before being written to PostgreSQL.

        Args:
            user_id: Owning user identifier.

        Returns:
            Key string ``latte:{user_id}:session:pending_kg``.

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Redis-keyspace
        Since: latte-graph-redis 2.0.0
        """
        return f"latte:{user_id}:session:pending_kg"

    @staticmethod
    def active_datasets(user_id: str) -> str:
        """Return the Redis key for the active dataset IDs set.

        Redis type: Set (SADD / SMEMBERS).  Stores the UUIDs of datasets the
        user has approved and loaded into DuckDB for the current session.

        Args:
            user_id: Owning user identifier.

        Returns:
            Key string ``latte:{user_id}:session:active_datasets``.

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Redis-keyspace
        Since: latte-graph-redis 2.0.0
        """
        return f"latte:{user_id}:session:active_datasets"

    @classmethod
    def all_session_keys(cls, user_id: str) -> list[str]:
        """Return all 7 session keys for a given user in stable order.

        Used by ``close_session`` (DEL) and ``reset_ttl`` (pipelined EXPIRE).
        The order is fixed: messages, state, last_query, last_chart,
        kg_cache, pending_kg, active_datasets.

        Args:
            user_id: Owning user identifier.

        Returns:
            List of exactly 7 key strings.

        Spec: ``docs/superpowers/specs/2026-05-19-docstring-traceability-convention-design.md``
        Source: PR-204 | BRD.Arch.002 §Redis-keyspace
        Since: latte-graph-redis 2.0.0
        """
        return [
            cls.messages(user_id),
            cls.state(user_id),
            cls.last_query(user_id),
            cls.last_chart(user_id),
            cls.kg_cache(user_id),
            cls.pending_kg(user_id),
            cls.active_datasets(user_id),
        ]
