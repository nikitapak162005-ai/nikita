"""Task C4 performance benchmark.

Measures median and p95 latency of a LOGICAL Increment operation for four
configurations:
    1. Single replica, 1 client
    2. Single replica, 16 clients
    3. Quorum (3 replicas), 1 client
    4. Quorum (3 replicas), 16 clients

A quorum logical operation sends 3 RPCs but counts as ONE operation.
Each configuration runs at least 2000 logical operations.

Run:  python tests/perf_benchmark.py
"""
import math
import os
import statistics
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from server import create_server
from client import CounterClient

TOTAL_OPS = 2000
N_CONCURRENT = 16


def start_replicas(n):
    reps = []
    for i in range(n):
        server, port, _ = create_server(port=0, name="bench-%d" % i, log_enabled=False)
        reps.append((server, "127.0.0.1:%d" % port))
    return reps


def p95(latencies):
    """p95 = value at index ceil(0.95 * n), converted to a zero-based index."""
    ordered = sorted(latencies)
    n = len(ordered)
    idx = math.ceil(0.95 * n) - 1          # 1-based position -> 0-based index
    idx = max(0, min(idx, n - 1))
    return ordered[idx]


def run_single_client(addresses, total_ops):
    client = CounterClient(replicas=addresses, name="bench", log_enabled=False,
                           max_retries=3)
    latencies = []
    for i in range(total_ops):
        start = time.perf_counter()
        client.quorum_increment("bench", 1, key="op-%d" % i)
        latencies.append((time.perf_counter() - start) * 1000.0)   # ms
    client.close()
    return latencies


def run_concurrent_clients(addresses, total_ops, n_clients):
    per_client = total_ops // n_clients          # 2000 / 16 = 125 -> 2000 total
    latencies = []
    lock = threading.Lock()

    def worker(worker_id):
        client = CounterClient(replicas=addresses, name="bench", log_enabled=False,
                               max_retries=3)
        local = []
        for i in range(per_client):
            start = time.perf_counter()
            client.quorum_increment("bench", 1, key="w%d-op%d" % (worker_id, i))
            local.append((time.perf_counter() - start) * 1000.0)
        client.close()
        with lock:
            latencies.extend(local)

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(n_clients)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return latencies


def report(name, latencies):
    med = statistics.median(latencies)
    p = p95(latencies)
    print("%-32s | %10.3f | %10.3f | %d"
          % (name, med, p, len(latencies)))
    return med, p


def main():
    print("Configuration                    | Median(ms) |   p95(ms)  | Requests")
    print("-" * 74)

    # Single replica
    reps = start_replicas(1)
    single = [reps[0][1]]
    report("Single replica, 1 client",
           run_single_client(single, TOTAL_OPS))
    report("Single replica, 16 clients",
           run_concurrent_clients(single, TOTAL_OPS, N_CONCURRENT))
    for server, _ in reps:
        server.stop(0)

    # Quorum (3 replicas)
    reps = start_replicas(3)
    quorum = [addr for _, addr in reps]
    report("Quorum (3 replicas), 1 client",
           run_single_client(quorum, TOTAL_OPS))
    report("Quorum (3 replicas), 16 clients",
           run_concurrent_clients(quorum, TOTAL_OPS, N_CONCURRENT))
    for server, _ in reps:
        server.stop(0)


if __name__ == "__main__":
    main()
