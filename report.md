# Replicated Counter Service — Test Report

**Course:** Distributed Systems
**Author:** [YOUR NAME]
**Repository:** [YOUR GITHUB URL]
**Date:** [DATE]

> Replace every `[PASTE REAL ... HERE]` placeholder with results produced on your
> machine. Do not invent results. Export this file to `report.pdf` when complete.

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

- Operating System: [PASTE REAL WINDOWS VERSION HERE]  <!-- PowerShell: (Get-CimInstance Win32_OperatingSystem).Caption -->
- Python Version: [PASTE REAL PYTHON VERSION HERE]      <!-- python --version -->
- Machine: [PASTE REAL MACHINE INFO HERE]               <!-- CPU / RAM -->
- grpcio: [PASTE REAL VERSION HERE]                      <!-- pip show grpcio -->
- grpcio-tools: [PASTE REAL VERSION HERE]
- pytest: [PASTE REAL VERSION HERE]

Full `pip freeze` output is in Appendix A.

## 4. Test-Case Table

| Test ID | Purpose | Expected Result | Actual Result | Pass/Fail | Evidence |
|---------|---------|-----------------|---------------|-----------|----------|
| test_increment_applies_delta | One Increment applies exactly its delta | new_value = 5 | [PASTE REAL RESULT HERE] | [PASS/FAIL] | pytest output |
| test_duplicate_key_not_reapplied | Same key returns stored result, no re-apply | value = 5, was_duplicate = true | [PASTE REAL RESULT HERE] | [PASS/FAIL] | pytest output |
| test_concurrent_increments_exact | 2×1000 concurrent increments | value = 2000 | [PASTE REAL RESULT HERE] | [PASS/FAIL] | pytest output |
| test_get_missing_counter | Get on unknown counter | found = false, value = 0 | [PASTE REAL RESULT HERE] | [PASS/FAIL] | pytest output |
| test_retry_after_timeout_is_safe | Timeout then retry with same key | counter moves exactly once | [PASTE REAL RESULT HERE] | [PASS/FAIL] | pytest output |
| test_majority_commit_two_acks | 2 of 3 replicas ack | committed = true, acks = 2 | [PASTE REAL RESULT HERE] | [PASS/FAIL] | pytest output |
| test_no_commit_below_majority | Only 1 of 3 acks | committed = false; replica applied locally | [PASTE REAL RESULT HERE] | [PASS/FAIL] | pytest output |
| test_replicas_converge | Batch of quorum writes | all replicas equal | [PASTE REAL RESULT HERE] | [PASS/FAIL] | pytest output |

Raw pytest run:

```
[PASTE REAL PYTEST -v OUTPUT HERE]
```

## 5. Failure-Injection Results

| Scenario | Injected Fault | Expected Invariant | Actual Result | Evidence |
|----------|----------------|--------------------|---------------|----------|
| Replica crash | one replica unreachable | write still commits (2 acks), no exception escapes | [PASTE REAL RESULT HERE] | test_majority_commit_two_acks |
| Request duplication | same idempotency key sent twice | value moves once; 2nd reply was_duplicate = true | [PASTE REAL RESULT HERE] | test_duplicate_request_moves_value_once |
| Induced timeout + retry | replica delays first request past deadline (--fault delay-first) | retry succeeds; counter moves exactly once | [PASTE REAL RESULT HERE] | test_timeout_then_retry_commits_once |

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
SEND  L=[REAL] ----------------> RECV  L=[REAL]
                                   |
                                   v
                                 APPLY L=[REAL]
                                   |
                                   v
RECV  L=[REAL] <---------------- SEND  L=[REAL]
```

**Causally ordered pair #1:** [INSERT REAL EVENT PAIR FROM LOG HERE]
Chain: [local-before edge] → [message send/receive edge] → ...

**Causally ordered pair #2:** [INSERT REAL EVENT PAIR FROM LOG HERE]

**Concurrent pair:** [INSERT REAL CONCURRENT EVENTS HERE]
These two events never exchange a message, so neither happened-before the other;
their Lamport values cannot tell us which occurred first in real time.

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
| Single replica, 1 client | [PASTE REAL MEDIAN HERE] | [PASTE REAL P95 HERE] | 2000 |
| Single replica, 16 clients | [PASTE REAL MEDIAN HERE] | [PASTE REAL P95 HERE] | 2000 |
| Quorum (3 replicas), 1 client | [PASTE REAL MEDIAN HERE] | [PASTE REAL P95 HERE] | 2000 |
| Quorum (3 replicas), 16 clients | [PASTE REAL MEDIAN HERE] | [PASTE REAL P95 HERE] | 2000 |

**Interpretation.** The quorum path is slower than a single replica because a
logical operation must wait for a majority of acknowledgements rather than one,
so its latency is bounded by the slower of the required replicas plus the cost of
issuing several parallel RPCs. Under 16 concurrent clients both median and p95
rise as requests contend for server threads and the state lock, and the p95 tail
grows faster than the median because the slowest requests are the ones that queue
behind others. For a like-counter workload this added latency is acceptable: the
operation stays in the low-milliseconds range and the durability benefit of
surviving one replica crash outweighs the extra round trips.

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

## Appendix A — `pip freeze`

```
[PASTE REAL pip freeze OUTPUT HERE]
```

## Appendix B — Lamport trace excerpt (~30 lines)

```
[PASTE REAL logs/trace_excerpt.txt CONTENT HERE]
```
