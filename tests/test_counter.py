"""Task C2 unit and integration tests (single-replica correctness)."""
import threading

import pytest

from conftest import start_replica
from client import CounterClient


@pytest.fixture
def replica():
    r = start_replica(name="test-replica")
    yield r
    r.stop()


def make_client(addresses, timeout=2.0, max_retries=3):
    return CounterClient(replicas=addresses, name="test-client",
                         timeout=timeout, max_retries=max_retries, log_enabled=False)


def test_increment_applies_delta(replica):
    # Arrange
    client = make_client([replica.address])
    # Act
    reply = client.increment_single("x", 5, key="k-apply")
    # Assert
    assert reply is not None
    assert reply.new_value == 5
    assert reply.was_duplicate is False
    client.close()


def test_duplicate_key_not_reapplied(replica):
    # Arrange
    client = make_client([replica.address])
    # Act
    r1 = client.increment_single("x", 5, key="k-dup")
    r2 = client.increment_single("x", 5, key="k-dup")   # same key -> retry
    # Assert
    assert r1.new_value == 5
    assert r2.new_value == 5          # NOT 10
    assert r2.was_duplicate is True
    client.close()


def test_concurrent_increments_exact(replica):
    # Arrange: two threads, 1000 increments each, same counter, unique keys.
    client = make_client([replica.address])

    def worker():
        for _ in range(1000):
            client.increment_single("c", 1)   # unique uuid key each time

    # Act
    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start(); t2.start()
    t1.join(); t2.join()

    # Assert: exactly 2000, proving the lock prevents lost updates.
    res = client.get("c")
    assert res is not None and res["value"] == 2000
    client.close()


def test_get_missing_counter(replica):
    # Arrange
    client = make_client([replica.address])
    # Act
    res = client.get("does-not-exist")
    # Assert
    assert res is not None
    assert res["found"] is False
    assert res["value"] == 0
    client.close()


def test_retry_after_timeout_is_safe():
    # Arrange: a replica that delays only the FIRST request past the deadline.
    r = start_replica(name="slow-replica", fault="delay-first", delay_ms=1500)
    client = make_client([r.address], timeout=0.5)   # deadline < first-request delay
    try:
        # Act: first attempt times out, client retries with the SAME key.
        res = client.quorum_increment("x", 5, key="k-retry")
        # Assert: the write committed and the counter moved exactly once.
        assert res["committed"] is True
        assert res["value"] == 5
        final = client.get("x")
        assert final["value"] == 5     # moved once, not twice
    finally:
        client.close()
        r.stop()
