"""Contract tests — verify public interface surface is stable."""
import inspect

import latte_graph_redis.interface as iface


EXPECTED_EXPORTS = {
    "RedisUnavailableError",
    "SessionKeyError",
    "RedisKeyBuilder",
    "SESSION_TTL",
    "MESSAGE_CAP",
    "RedisClientFactory",
    "RedisSessionRepository",
}


def test_all_exports_present():
    """Every expected symbol must be in __all__."""
    missing = EXPECTED_EXPORTS - set(iface.__all__)
    assert not missing, f"Missing from __all__: {missing}"


def test_no_private_symbols_in_all():
    """No private (_) symbols allowed in __all__."""
    private = [s for s in iface.__all__ if s.startswith("_")]
    assert private == [], f"Private symbols in __all__: {private}"


def test_all_symbols_importable():
    """Every symbol in __all__ must be accessible as attribute."""
    for name in iface.__all__:
        assert hasattr(iface, name), f"Symbol not importable: {name}"


def test_redis_unavailable_error_is_exception():
    assert inspect.isclass(iface.RedisUnavailableError)
    assert issubclass(iface.RedisUnavailableError, Exception)


def test_session_key_error_is_exception():
    assert inspect.isclass(iface.SessionKeyError)
    assert issubclass(iface.SessionKeyError, Exception)


def test_redis_key_builder_is_class():
    assert inspect.isclass(iface.RedisKeyBuilder)


def test_redis_client_factory_is_class():
    assert inspect.isclass(iface.RedisClientFactory)


def test_redis_session_repository_is_class():
    assert inspect.isclass(iface.RedisSessionRepository)


def test_session_ttl_is_int():
    assert isinstance(iface.SESSION_TTL, int)
    assert iface.SESSION_TTL == 86_400


def test_message_cap_is_int():
    assert isinstance(iface.MESSAGE_CAP, int)
    assert iface.MESSAGE_CAP == 20


def test_all_count_matches_expected():
    assert len(iface.__all__) == len(EXPECTED_EXPORTS)
