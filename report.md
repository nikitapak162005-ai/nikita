# Replicated Counter Service — Test Report

**Course:** Distributed Systems
**Author:** Nikita
**Repository:** https://github.com/nikitapak162005-ai/nikita
**Date:** 8.10.2026


---

## 1. Overview

This report documents the testing of a replicated counter service built in three
stages: a gRPC counter service with RPC failure handling (Part A), Lamport
logical-clock instrumentation (Part B), and a three-replica group with
majority-acknowledged (quorum) writes (Part C). Every behavioral claim below is
backed by an executable test or a captured log line.

## 2. Requirements Under Test

| Task | Requirement | Verifying test(s) |
|------|-------------|-------------------|
| A2 | Increment applies delta; idempotency key suppresses duplicates; client retries with same key | `test_increment_applies_delta`, `test_duplicate_key_not_reapplied`, `test_retry_after_timeout_is_safe` |
| A2 | Get on unknown counter returns found = false | `test_get_missing_counter` |
| A3 | Concurrent clients produce exact totals (lock prevents lost updates) | `test_concurrent_increments_exact` |
| B1 | Lamport clocks attached to every message; max(local,received)+1 on receive | `logs/*.log`, `logs/trace_excerpt.txt` |
| C1 | Majority commit (2/3); below-majority not committed; replicas converge | `test_majority_commit_two_acks`, `test_no_commit_below_majority`, `test_replicas_converge` |
| C3 | Failure injection: crash, duplication, timeout+retry | `test_majority_commit_two_acks`, `test_duplicate_request_moves_value_once`, `test_timeout_then_retry_commits_once` |

## 3. Test Environment

- Operating System:  Windows 11 Pro 
- Python Version: Python 3.14.7     
- grpcio: 1.84.0                     
- grpcio-tools: 1.84.0
- pytest:  9.1.1



## 4. Test-Case Table

| Test ID | Purpose | Expected Result | Actual Result | Pass/Fail | Evidence |
|---------|---------|-----------------|---------------|-----------|----------|
| test_increment_applies_delta | One Increment applies exactly its delta | new_value = 5 | new_value = 5; was_duplicate = false | PASS | pytest output |
| test_duplicate_key_not_reapplied | Same key returns stored result, no re-apply | value = 5, was_duplicate = true | value remained 5; second request returned was_duplicate = true | PASS | pytest output |
| test_concurrent_increments_exact | 2×1000 concurrent increments | value = 2000 | final counter value = 2000 | PASS | pytest output |
| test_get_missing_counter | Get on unknown counter | found = false, value = 0 | found = false; value = 0 | PASS | pytest output |
| test_retry_after_timeout_is_safe | Timeout then retry with same key | counter moves exactly once | retry committed successfully; final counter value = 5 and was applied only once | PASS | pytest output |
| test_majority_commit_two_acks | 2 of 3 replicas ack | committed = true, acks = 2 | committed = true; acknowledgements = 2; value = 1 | PASS | pytest output |
| test_no_commit_below_majority | Only 1 of 3 acks | committed = false; replica applied locally | committed = false; acknowledgements = 1; surviving replica local value = 1 | PASS | pytest output |
| test_replicas_converge | Batch of quorum writes | all replicas equal | all three replicas converged to value = 20 | PASS | pytest output |

Raw pytest run:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\user\Desktop\nikitaRSas2\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\user\Desktop\nikitaRSas2
collecting ... collected 10 items

tests/test_counter.py::test_increment_applies_delta PASSED   [ 10%]
tests/test_counter.py::test_duplicate_key_not_reapplied PASSED   [ 20%]
tests/test_counter.py::test_concurrent_increments_exact PASSED   [ 30%]
tests/test_counter.py::test_get_missing_counter PASSED   [ 40%]
tests/test_counter.py::test_retry_after_timeout_is_safe PASSED   [ 50%]
tests/test_failures.py::test_majority_commit_two_acks PASSED   [ 60%]
tests/test_failures.py::test_no_commit_below_majority PASSED   [ 70%]
tests/test_failures.py::test_duplicate_request_moves_value_once PASSED   [ 80%]
tests/test_failures.py::test_timeout_then_retry_commits_once PASSED   [ 90%]
tests/test_failures.py::test_replicas_converge PASSED   [100%]

============================= 10 passed in 8.19s ==============================
```

## 5. Failure-Injection Results

| Scenario | Injected Fault | Expected Invariant | Actual Result | Evidence |
|----------|----------------|--------------------|---------------|----------|
| Replica crash | one replica unreachable | write still commits (2 acks), no exception escapes | committed = true; 2 of 3 replicas acknowledged the write | test_majority_commit_two_acks |
| Request duplication | same idempotency key sent twice | value moves once; 2nd reply was_duplicate = true | value remained 5 after the duplicate request; second response returned was_duplicate = true | test_duplicate_request_moves_value_once |
| Induced timeout + retry | replica delays first request past deadline (--fault delay-first) | retry succeeds; counter moves exactly once | first request exceeded the deadline; retry succeeded with the same idempotency key and final value = 5 | test_timeout_then_retry_commits_once |

Below-majority behavior (partial-write anomaly): with only one of three replicas
reachable the client reports **not committed** (1 ack < majority 2), yet that
replica has already applied the write locally. A real consensus protocol (e.g.
Raft) prevents this by committing only through a replicated log and a leader's
commit index, so a sub-majority write is never visible as applied.

## 6. Lamport Clock Analysis (Task B2)

**Rules implemented.** Local event: `L = L + 1` (before each send/apply).
Receive: `L = max(local, received) + 1`. Every message carries the sender's `L`.

**Happened-before.** If A → B then L(A) < L(B). The converse does not hold:
L(A) < L(B) alone does not imply A → B, because events in different processes
that never exchange a message are concurrent even if their L values differ.

Diagram (fill real values from your run):
```
client-1                         replica-A
SEND  L=1 ---------------------> RECV  L=2
                                   |
                                   v
                                  APPLY L=3
                                   |
                                   v
RECV  L=5 <--------------------- SEND  L=4
```

**Causally ordered pair #1:** `client-1 SEND Increment(counter=x, delta=1) L=1` → `replica-A RECV Increment(counter=x, delta=1) L=2`.

Chain: the client SEND event happens-before the corresponding server RECV event through the RPC message-delivery edge. Therefore, L(SEND) = 1 < L(RECV) = 2.

**Causally ordered pair #2:** `replica-A SEND IncrementReply(new_value=1) L=4` → `client-1 RECV IncrementReply(new_value=1) L=5`.

The server SEND event happens-before the corresponding client RECV event through the reply message. Therefore, L(SEND) = 4 < L(RECV) = 5.

**Concurrent pair:** `client-1 SEND Increment(counter=x, delta=1) L=1` and `client-2 SEND Increment(counter=y, delta=1) L=1`.

These two events were generated independently by different client processes, and there is no local-order or message-delivery chain from one event to the other. Therefore, neither event happened-before the other; they are concurrent. Their Lamport timestamps also demonstrate that logical-clock values alone do not establish a causal relationship.

**Limitation.** Lamport clocks cannot detect concurrency from timestamp values
alone (L(A) < L(B) does not prove causality). Vector clocks attach one counter
per process, which lets a reader decide, for any two events, whether one
happened-before the other or they are concurrent.

A ~30-line excerpt of the real merged trace is in Appendix B / `logs/trace_excerpt.txt`.

## 7. Performance Results (Task C4)

At least 2000 logical Increment operations per configuration. A quorum logical
operation sends 3 RPCs but counts as one operation. p95 = sorted value at index
`ceil(0.95 * n)`.

| Configuration | Median Latency (ms) | p95 Latency (ms) | Requests |
|---------------|---------------------|------------------|----------|
| Single replica, 1 client | 1.090 | 2.672 | 2000 |
| Single replica, 16 clients | 15.543 | 22.506 | 2000 |
| Quorum (3 replicas), 1 client | 2.768 | 3.869 | 2000 |
| Quorum (3 replicas), 16 clients | 44.919 | 54.082 | 2000 |

**Interpretation.** The measurements show that quorum writes introduce additional latency compared with single-replica writes. With one client, the median latency increased from 1.090 ms for a single replica to 2.768 ms for quorum writes, while p95 increased from 2.672 ms to 3.869 ms. The difference became larger under concurrency: with 16 clients, median latency increased from 15.543 ms for a single replica to 44.919 ms for quorum, and p95 increased from 22.506 ms to 54.082 ms. This occurs because each quorum operation communicates with three replicas and must collect a majority of acknowledgements. Higher concurrency also increases contention for server threads and the shared state lock. The p95 values show that the slower tail requests are affected more strongly than a typical request represented by the median.

## 8. Known Limitations

1. **In-memory counter state** — all values are lost when a replica restarts.
2. **In-memory idempotency store** — deduplication history is lost on restart, so
   a replayed key after restart could be applied again.
3. **No full consensus** — no leader election, no durable replicated log, no
   commit index, no recovery/catch-up; a sub-majority write can partially apply.
4. **Replicas can diverge** — a replica that was unavailable misses writes until
   new ones arrive.
5. **Stale reads** — Get reads from a single replica, which may return an
   out-of-date value if that replica missed writes.

## 9. Reflection Questions

**1. After a timeout, why can't the client tell "request lost" from "reply lost",
and how does idempotency make this harmless?**
A timeout only tells the client that no reply arrived in time; the request may
never have reached the server, or it may have executed with the reply lost or
delayed. The client cannot distinguish these. Reusing the same idempotency key on
retry makes the ambiguity harmless: if the first attempt did apply, the retry
returns the stored result with `was_duplicate = true` and does not apply again, so
the mutation happens at most once.

**2. Your trace has a concurrent pair whose Lamport values differ. Why does the
smaller value not mean that event happened first?**
Lamport clocks only guarantee that if A → B then L(A) < L(B). For concurrent
events (no chain of local-order and message edges between them) the values are
unrelated to real-time order; a smaller value can simply reflect a process that
had seen fewer events, not an earlier occurrence.

**3. With three replicas and majority commit, which failures are tolerated while
preserving every committed write, and which breaks the guarantee? (safety vs
liveness)**
One replica crash is tolerated: a majority (2 of 3) still acknowledges, so every
committed write survives — this preserves **safety** and keeps the service
available (**liveness**). Two crashes break the guarantee for new writes: a
majority is impossible, so no new write can commit (liveness lost), though already
committed writes on the survivor remain correct (safety is not violated).

**4. To survive replica restarts without losing committed writes, what is the
smallest change, and which Week-6 mechanism does it anticipate?**
Persist the counter state and the idempotency store to disk before acknowledging a
write (a write-ahead log), so a restarted replica recovers its committed state.
This anticipates the durable replicated log and commit index of a real consensus
protocol such as Raft.

## 10. Conclusion

This assignment implemented and tested a replicated counter service using gRPC communication, idempotent request handling, retry logic, concurrency control, Lamport logical clocks, and majority-based writes across three replicas. All ten automated tests completed successfully on the local test environment, including concurrency, retry safety, quorum behavior, failure injection, and replica convergence. The performance measurements demonstrated the additional latency introduced by quorum-based writes, especially under concurrent load. The project also demonstrated the limitations of a simplified replicated system without a full consensus protocol, including partial writes, stale replicas, and the loss of in-memory state after restart.

## Appendix A — `pip freeze`

```
colorama==0.4.6
grpcio==1.84.0
grpcio-tools==1.84.0
iniconfig==2.3.1
packaging==26.3
pluggy==1.6.0
protobuf==7.36.2
Pygments==2.21.0
pytest==9.1.1
setuptools==84.0.0
typing_extensions==4.16.0
```

## Appendix B — Lamport trace excerpt (~30 lines)

```text
[client-1] SEND   Increment(counter=x, delta=1) L=1
[client-1] SEND   Increment(counter=x, delta=1) L=1
[client-3] SEND   Get(counter=x) L=1
[replica-A] RECV   Increment(counter=x, delta=1) L=2 (received L=1)
[replica-A] APPLY  counter=x -> 1 L=3
[replica-A] SEND   IncrementReply(new_value=1, duplicate=False) L=4
[client-1] RECV   IncrementReply(new_value=1) L=5 (received L=4)
[client-1] SEND   Increment(counter=x, delta=1) L=6
[replica-A] RECV   Increment(counter=x, delta=1) L=7 (received L=6)
[replica-A] APPLY  counter=x -> 2 L=8
[replica-A] SEND   IncrementReply(new_value=2, duplicate=False) L=9
[client-1] RECV   IncrementReply(new_value=2) L=10 (received L=9)
[replica-A] RECV   Increment(counter=x, delta=1) L=10 (received L=1)
[replica-A] APPLY  counter=x -> 3 L=11
[replica-A] SEND   IncrementReply(new_value=3, duplicate=False) L=12
[client-1] RECV   IncrementReply(new_value=3) L=13 (received L=12)
[client-1] SEND   Increment(counter=x, delta=1) L=14
[replica-A] RECV   Increment(counter=x, delta=1) L=15 (received L=14)
[replica-A] APPLY  counter=x -> 4 L=16
[replica-A] SEND   IncrementReply(new_value=4, duplicate=False) L=17
[client-1] RECV   IncrementReply(new_value=4) L=18 (received L=17)
[replica-A] RECV   Get(counter=x) L=18 (received L=1)
[replica-A] SEND   GetReply(value=4, found=True) L=19
[client-3] RECV   GetReply(value=4, found=True) L=20 (received L=19)
[client-3] SEND   Get(counter=y) L=21
[replica-A] RECV   Get(counter=y) L=22 (received L=21)
[replica-A] SEND   GetReply(value=0, found=False) L=23
[client-3] RECV   GetReply(value=0, found=False) L=24 (received L=23)
[client-2] SEND   Increment(counter=y,delta=1) L=1
[client-2] RECV   IncrementReply(new_value=1) L=13 (received L=12)
[client-2] SEND   Increment(counter=y,delta=1) L=14
[client-2] RECV   IncrementReply(new_value=2) L=18 (received L=17)
```   
## Appendix C — Automated Test Output

```text
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Users\user\Desktop\nikitaRSas2\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\user\Desktop\nikitaRSas2
collecting ... collected 10 items

tests/test_counter.py::test_increment_applies_delta PASSED   [ 10%]
tests/test_counter.py::test_duplicate_key_not_reapplied PASSED   [ 20%]
tests/test_counter.py::test_concurrent_increments_exact PASSED   [ 30%]
tests/test_counter.py::test_get_missing_counter PASSED   [ 40%]
tests/test_counter.py::test_retry_after_timeout_is_safe PASSED   [ 50%]
tests/test_failures.py::test_majority_commit_two_acks PASSED   [ 60%]
tests/test_failures.py::test_no_commit_below_majority PASSED   [ 70%]
tests/test_failures.py::test_duplicate_request_moves_value_once PASSED   [ 80%]
tests/test_failures.py::test_timeout_then_retry_commits_once PASSED   [ 90%]
tests/test_failures.py::test_replicas_converge PASSED   [100%]

============================= 10 passed in 8.19s ==============================
```

## Appendix D — Performance Benchmark Output

```text
Configuration                    | Median(ms) |   p95(ms)  | Requests
--------------------------------------------------------------------------
Single replica, 1 client         |      1.090 |      2.672 | 2000
Single replica, 16 clients       |     15.543 |     22.506 | 2000
Quorum (3 replicas), 1 client    |      2.768 |      3.869 | 2000
Quorum (3 replicas), 16 clients  |     44.919 |     54.082 | 2000
```