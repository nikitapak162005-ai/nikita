import argparse
import os
import threading
import time
from concurrent import futures

import grpc

import counter_pb2
import counter_pb2_grpc
from clocks import LamportClock


class CounterServicer(counter_pb2_grpc.CounterServicer):
    def __init__(self, name="replica", fault=None, delay_ms=0, log_enabled=True):
        self._lock = threading.Lock()          # protects values AND seen together
        self._values = {}                      # counter_id -> int
        self._seen = {}                        # idempotency_key -> (counter_id, new_value)
        self._clock = LamportClock()
        self._name = name
        self._fault = fault
        self._delay_ms = delay_ms
        self._log_enabled = log_enabled
        self._first_request_handled = False    
        self._fault_lock = threading.Lock()

    
    def _log(self, line):
        if not self._log_enabled:
            return
        os.makedirs("logs", exist_ok=True)
        with open(os.path.join("logs", self._name + ".log"), "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    
    def _maybe_inject_fault(self, context):
        if self._fault == "drop-after-recv":
            time.sleep(3600)
            return

        if self._fault == "delay-first":
            with self._fault_lock:
                is_first = not self._first_request_handled
                self._first_request_handled = True
            if is_first:
                delay = self._delay_ms if self._delay_ms > 0 else 1500
                time.sleep(delay / 1000.0)
            return

        if self._delay_ms > 0:
            time.sleep(self._delay_ms / 1000.0)

    
    def Increment(self, request, context):
        recv_l = self._clock.receive(request.lamport_time)
        self._log("[%s] RECV   Increment(counter=%s, delta=%d) L=%d (received L=%d)"
                  % (self._name, request.counter_id, request.delta, recv_l, request.lamport_time))

        self._maybe_inject_fault(context)

        with self._lock:
            if request.idempotency_key and request.idempotency_key in self._seen:
                _, stored_value = self._seen[request.idempotency_key]
                send_l = self._clock.tick()   # SEND event
                self._log("[%s] SEND   IncrementReply(new_value=%d, duplicate=True) L=%d"
                          % (self._name, stored_value, send_l))
                return counter_pb2.IncrementReply(
                    new_value=stored_value, was_duplicate=True, lamport_time=send_l)

            new_value = self._values.get(request.counter_id, 0) + request.delta
            self._values[request.counter_id] = new_value
            if request.idempotency_key:
                self._seen[request.idempotency_key] = (request.counter_id, new_value)

            apply_l = self._clock.tick()      
            self._log("[%s] APPLY  counter=%s -> %d L=%d"
                      % (self._name, request.counter_id, new_value, apply_l))

            send_l = self._clock.tick()       
            self._log("[%s] SEND   IncrementReply(new_value=%d, duplicate=False) L=%d"
                      % (self._name, new_value, send_l))
            return counter_pb2.IncrementReply(
                new_value=new_value, was_duplicate=False, lamport_time=send_l)

    
    def Get(self, request, context):
        recv_l = self._clock.receive(request.lamport_time)
        self._log("[%s] RECV   Get(counter=%s) L=%d (received L=%d)"
                  % (self._name, request.counter_id, recv_l, request.lamport_time))

        with self._lock:
            found = request.counter_id in self._values
            value = self._values.get(request.counter_id, 0)

        send_l = self._clock.tick()
        self._log("[%s] SEND   GetReply(value=%d, found=%s) L=%d"
                  % (self._name, value, found, send_l))
        return counter_pb2.GetReply(value=value, found=found, lamport_time=send_l)


def create_server(port=0, name="replica", fault=None, delay_ms=0, log_enabled=True,
                  max_workers=8):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    servicer = CounterServicer(name=name, fault=fault, delay_ms=delay_ms,
                               log_enabled=log_enabled)
    counter_pb2_grpc.add_CounterServicer_to_server(servicer, server)
    actual_port = server.add_insecure_port("127.0.0.1:%d" % port)
    server.start()
    return server, actual_port, servicer


def main():
    parser = argparse.ArgumentParser(description="Replicated counter replica")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--name", type=str, default="replica-A")
    parser.add_argument("--fault", type=str, default=None,
                        choices=[None, "delay-first", "drop-after-recv"])
    parser.add_argument("--delay-ms", type=int, default=0)
    args = parser.parse_args()

    server, port, _ = create_server(
        port=args.port, name=args.name, fault=args.fault, delay_ms=args.delay_ms,
        log_enabled=True)
    print("[%s] listening on 127.0.0.1:%d (fault=%s, delay_ms=%d)"
          % (args.name, port, args.fault, args.delay_ms))
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("\n[%s] shutting down" % args.name)
        server.stop(0)


if __name__ == "__main__":
    main()
