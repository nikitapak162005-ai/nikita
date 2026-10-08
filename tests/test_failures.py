"""Task C3 failure-injection tests and quorum behaviour.

Scenarios:
  1. Replica failure  -> test_majority_commit_two_acks (2 of 3 still commits)
  2. Below majority   -> test_no_commit_below_majority (1 of 3 fails; partial apply shown)
  3. Duplicate request -> test_duplicate_request_moves_value_once
  4. Timeout + retry  -> test_timeout_then_retry_commits_once
  5. Convergence      -> test_replicas_converge
"""
from conftest import start_replica
from client import CounterClient


def make_client(addresses, timeout=2.0, max_retries=3):
    return CounterClient(replicas=addresses, name="fail-client",
                         timeout=timeout, max_retries=max_retries, log_enabled=False)


def test_majority_commit_two_acks():
    # Arrange: 2 live replicas + 1 unreachable address (the "crashed" replica).
    a = start_replica(name="A")
    b = start_replica(name="B")
    dead = "127.0.0.1:59999"   # no server here
    client = make_client([a.address, b.address, dead], max_retries=1)
    try:
        # Act
        res = client.quorum_increment("x", 1, key="k-maj")
        # Assert: 2 of 3 acknowledged -> committed.
        assert res["acks"] == 2
        assert res["committed"] is True
        assert res["value"] == 1
    finally:
        client.close(); a.stop(); b.stop()


def test_no_commit_below_majority():
    # Arrange: only 1 live replica + 2 unreachable addresses.
    a = start_replica(name="A")
    client = make_client([a.address, "127.0.0.1:59998", "127.0.0.1:59997"],
                         max_retries=1)
    try:
        # Act
        res = client.quorum_increment("x", 1, key="k-nomaj")
        # Assert: only 1 ack < majority(2) -> NOT committed...
        assert res["acks"] == 1
        assert res["committed"] is False
        # ...but the surviving replica DID apply the write locally: the
        # partial-write anomaly. A direct read of that replica shows value=1.
        direct = make_client([a.address], max_retries=1)
        local = direct.get("x")
        assert local["value"] == 1
        direct.close()
    finally:
        client.close(); a.stop()


def test_duplicate_request_moves_value_once():
    # Arrange
    a = start_replica(name="A")
    b = start_replica(name="B")
    c = start_replica(name="C")
    client = make_client([a.address, b.address, c.address])
    try:
        # Act: send the same idempotency key twice.
        r1 = client.quorum_increment("x", 5, key="k-once")
        r2 = client.quorum_increment("x", 5, key="k-once")
        # Assert: value moved once; second reply is a duplicate.
        assert r1["value"] == 5
        assert r2["value"] == 5
        assert r2["was_duplicate"] is True
    finally:
        client.close(); a.stop(); b.stop(); c.stop()


def test_timeout_then_retry_commits_once():
    # Arrange: one replica delays its first request past the deadline.
    a = start_replica(name="A", fault="delay-first", delay_ms=1500)
    client = make_client([a.address], timeout=0.5)
    try:
        # Act
        res = client.quorum_increment("x", 5, key="k-timeout")
        # Assert: retry succeeded and the counter moved exactly once.
        assert res["committed"] is True
        assert client.get("x")["value"] == 5
    finally:
        client.close(); a.stop()


def test_replicas_converge():
    # Arrange: 3 live replicas.
    a = start_replica(name="A")
    b = start_replica(name="B")
    c = start_replica(name="C")
    client = make_client([a.address, b.address, c.address])
    try:
        # Act: a batch of quorum writes.
        for i in range(20):
            client.quorum_increment("x", 1, key="batch-%d" % i)
        # Assert: every live replica holds the same value.
        values = []
        for addr in (a.address, b.address, c.address):
            dc = make_client([addr])
            values.append(dc.get("x")["value"])
            dc.close()
        assert values == [20, 20, 20]
    finally:
        client.close(); a.stop(); b.stop(); c.stop()
