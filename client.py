"""Counter client: talks to one or more replicas over gRPC.

Key responsibilities:
  - every RPC carries a deadline (default 2.0 s);
  - on DEADLINE_EXCEEDED or UNAVAILABLE, retry at most 3 times with
    exponential backoff (0.2 s, 0.4 s, 0.8 s), REUSING the same idempotency key;
  - a quorum Increment is sent to all replicas and is committed only when a
    majority acknowledge it (2 of 3).

CLI:
    python client.py incr likes:post-42 --by 5
    python client.py get likes:post-42
    python client.py --replicas 127.0.0.1:50051 incr x --by 5 --key demo-key
    python client.py --name client-1 --replicas 127.0.0.1:50051 scenario client-1
"""
import argparse
import os
import time
import uuid
from concurrent import futures

import grpc

import counter_pb2
import counter_pb2_grpc
from clocks import LamportClock

DEFAULT_REPLICAS = ["127.0.0.1:50051", "127.0.0.1:50052", "127.0.0.1:50053"]

# gRPC status codes that are safe to retry (transient failures).
RETRYABLE = (grpc.StatusCode.DEADLINE_EXCEEDED, grpc.StatusCode.UNAVAILABLE)
BACKOFFS = [0.2, 0.4, 0.8]   # exponential backoff between the 3 retries


class CounterClient:
    def __init__(self, replicas=None, name="client", timeout=2.0,
                 max_retries=3, log_enabled=True):
        self._replicas = list(replicas) if replicas else list(DEFAULT_REPLICAS)
        self._name = name
        self._timeout = timeout
        self._max_retries = max_retries
        self._log_enabled = log_enabled
        self._clock = LamportClock()
        self._channels = [grpc.insecure_channel(addr) for addr in self._replicas]
        self._stubs = [counter_pb2_grpc.CounterStub(ch) for ch in self._channels]

    # ---- logging -------------------------------------------------------
    def _log(self, line):
        if not self._log_enabled:
            return
        os.makedirs("logs", exist_ok=True)
        with open(os.path.join("logs", self._name + ".log"), "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def majority(self):
        return len(self._replicas) // 2 + 1

    # ---- one RPC against one replica, with retries ---------------------
    def _increment_on_stub(self, stub, counter_id, delta, key):
        """Send Increment to one replica. Retry on transient errors with the SAME key.

        Returns the IncrementReply, or None if every attempt failed.
        """
        attempts = self._max_retries + 1          # initial attempt + N retries
        for attempt in range(attempts):
            send_l = self._clock.tick()            # SEND event
            request = counter_pb2.IncrementRequest(
                counter_id=counter_id, delta=delta,
                idempotency_key=key, lamport_time=send_l)
            self._log("[%s] SEND   Increment(counter=%s, delta=%d) L=%d"
                      % (self._name, counter_id, delta, send_l))
            try:
                reply = stub.Increment(request, timeout=self._timeout)
                recv_l = self._clock.receive(reply.lamport_time)   # RECV event
                self._log("[%s] RECV   IncrementReply(new_value=%d) L=%d (received L=%d)"
                          % (self._name, reply.new_value, recv_l, reply.lamport_time))
                return reply
            except grpc.RpcError as err:
                if err.code() in RETRYABLE and attempt < attempts - 1:
                    time.sleep(BACKOFFS[min(attempt, len(BACKOFFS) - 1)])
                    continue
                return None
        return None

    def increment_single(self, counter_id, delta, key=None):
        """Increment against the FIRST replica only. Returns the reply or None."""
        if key is None:
            key = str(uuid.uuid4())
        return self._increment_on_stub(self._stubs[0], counter_id, delta, key)

    def quorum_increment(self, counter_id, delta, key=None):
        """Send Increment to ALL replicas in parallel; commit on a majority of acks.

        Returns a dict: committed, value, acks, total, was_duplicate.
        """
        if key is None:
            key = str(uuid.uuid4())   # one key per logical operation, reused on retries
        results = []
        with futures.ThreadPoolExecutor(max_workers=len(self._stubs)) as pool:
            running = [pool.submit(self._increment_on_stub, stub, counter_id, delta, key)
                       for stub in self._stubs]
            for fut in running:
                results.append(fut.result())

        acks = [r for r in results if r is not None]
        committed = len(acks) >= self.majority()
        value = acks[0].new_value if acks else None
        was_duplicate = acks[0].was_duplicate if acks else False
        return {
            "committed": committed,
            "value": value,
            "acks": len(acks),
            "total": len(self._stubs),
            "was_duplicate": was_duplicate,
        }

    # increment_one is an alias for the quorum path (one logical operation).
    def increment_one(self, counter_id, delta, key=None):
        return self.quorum_increment(counter_id, delta, key=key)

    def get(self, counter_id):
        """Read the counter from any single reachable replica.

        Returns a dict: value, found, replica (address) or None if none reachable.
        """
        for stub, addr in zip(self._stubs, self._replicas):
            send_l = self._clock.tick()
            request = counter_pb2.GetRequest(counter_id=counter_id, lamport_time=send_l)
            self._log("[%s] SEND   Get(counter=%s) L=%d" % (self._name, counter_id, send_l))
            try:
                reply = stub.Get(request, timeout=self._timeout)
                recv_l = self._clock.receive(reply.lamport_time)
                self._log("[%s] RECV   GetReply(value=%d, found=%s) L=%d (received L=%d)"
                          % (self._name, reply.value, reply.found, recv_l, reply.lamport_time))
                return {"value": reply.value, "found": reply.found, "replica": addr}
            except grpc.RpcError:
                continue
        return None

    def close(self):
        for ch in self._channels:
            ch.close()


def run_scenario(client, who):
    """Lamport-trace scenario. client-1/2 do two increments; client-3 only Gets."""
    if who == "client-1":
        client.quorum_increment("x", 1)
        client.quorum_increment("x", 1)
    elif who == "client-2":
        client.quorum_increment("y", 1)
        client.quorum_increment("y", 1)
    elif who == "client-3":
        client.get("x")
        client.get("y")
    else:
        print("unknown scenario role: %s" % who)


def main():
    parser = argparse.ArgumentParser(description="Counter client")
    parser.add_argument("--replicas", type=str, default=None,
                        help="comma-separated host:port list; default = 3 local replicas")
    parser.add_argument("--name", type=str, default="client")
    parser.add_argument("--timeout", type=float, default=2.0)
    sub = parser.add_subparsers(dest="command", required=True)

    p_incr = sub.add_parser("incr", help="increment a counter (quorum write)")
    p_incr.add_argument("counter_id")
    p_incr.add_argument("--by", type=int, default=1)
    p_incr.add_argument("--key", type=str, default=None)

    p_get = sub.add_parser("get", help="read a counter")
    p_get.add_argument("counter_id")

    p_scn = sub.add_parser("scenario", help="run a Lamport-trace scenario role")
    p_scn.add_argument("role", choices=["client-1", "client-2", "client-3"])

    args = parser.parse_args()
    replicas = [r.strip() for r in args.replicas.split(",")] if args.replicas else None
    client = CounterClient(replicas=replicas, name=args.name, timeout=args.timeout)

    try:
        if args.command == "incr":
            res = client.quorum_increment(args.counter_id, args.by, key=args.key)
            dup = "yes" if res["was_duplicate"] else "no"
            if res["committed"]:
                print("OK committed value=%s (replicas acked: %d/%d, duplicate: %s)"
                      % (res["value"], res["acks"], res["total"], dup))
            else:
                print("FAILED not committed (replicas acked: %d/%d)"
                      % (res["acks"], res["total"]))
        elif args.command == "get":
            res = client.get(args.counter_id)
            if res is None:
                print("ERROR no replica reachable")
            else:
                print("value=%d" % res["value"])
        elif args.command == "scenario":
            run_scenario(client, args.role)
            print("scenario %s done" % args.role)
    finally:
        client.close()


if __name__ == "__main__":
    main()
