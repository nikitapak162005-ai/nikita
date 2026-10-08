# Replicated Counter Service

A small distributed system built in three stages: a gRPC counter service with
failure handling (Part A), Lamport logical-clock instrumentation (Part B), and
a three-replica group with majority-acknowledged (quorum) writes plus a full
test suite (Part C).

- **Language / stack:** Python 3.9+, gRPC, Protocol Buffers, pytest
- **Replicas:** independent processes on ports 50051, 50052, 50053
- **Quorum:** a write commits only when a majority (2 of 3) replicas acknowledge

## Project layout

```
dcc-assignment2/
  counter.proto                 gRPC interface definition
  counter_pb2.py                generated (do not edit)
  counter_pb2_grpc.py           generated (do not edit)
  clocks.py                     Lamport logical clock
  server.py                     one replica; flags: --port --name --fault --delay-ms
  client.py                     incr / get / scenario; retry + quorum logic
  tests/
    test_counter.py             single-replica unit/integration tests
    test_failures.py            quorum + failure-injection tests
    perf_benchmark.py           latency benchmark (Task C4)
  logs/                         Lamport event logs + trace_excerpt.txt
  report.pdf                    test report (Task C5)
  README.md
```

## Setup (Windows PowerShell)

```powershell
# 1. From inside the project folder, create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate

# 2. Install dependencies
pip install grpcio grpcio-tools pytest

# 3. Generate the gRPC stubs from counter.proto
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. counter.proto
```

On macOS / Linux, activate with `source .venv/bin/activate`.

## Run one replica (Part A)

```powershell
# Terminal 1
python server.py --port 50051 --name replica-A

# Terminal 2
python client.py --replicas 127.0.0.1:50051 incr likes:post-42 --by 5
python client.py --replicas 127.0.0.1:50051 get likes:post-42     # value=5
```

### Idempotency demonstration

```powershell
python client.py --replicas 127.0.0.1:50051 incr x --by 5 --key demo-key
python client.py --replicas 127.0.0.1:50051 incr x --by 5 --key demo-key
# second call: duplicate: yes, value stays 5 (NOT 10)
```

## Run three replicas and the quorum client (Part C)

```powershell
# Terminal 1
python server.py --port 50051 --name replica-A
# Terminal 2
python server.py --port 50052 --name replica-B
# Terminal 3
python server.py --port 50053 --name replica-C
# Terminal 4
python client.py incr likes:post-42 --by 1       # OK committed (acked 3/3)
# Stop replica C (Ctrl+C) -> write still commits (acked 2/3)
# Stop replica B as well  -> FAILED not committed (acked 1/3)
```

## Lamport trace scenario (Part B)

```powershell
# Terminal 1
python server.py --port 50051 --name replica-A
# Terminals 2-4 (start close together)
python client.py --name client-1 --replicas 127.0.0.1:50051 scenario client-1
python client.py --name client-2 --replicas 127.0.0.1:50051 scenario client-2
python client.py --name client-3 --replicas 127.0.0.1:50051 scenario client-3
# Logs appear in logs\client-1.log, client-2.log, client-3.log, replica-A.log
```

## Run the tests

```powershell
pytest -v
# or
python -m pytest -v
```

## Run the performance benchmark

```powershell
python tests\perf_benchmark.py
```

The benchmark starts its own ephemeral replicas, runs 2000 logical Increment
operations per configuration, and prints median and p95 latency.
