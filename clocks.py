"""Lamport logical clock, shared by the client and every replica.

A Lamport clock is just a per-process integer counter. It does not measure
real (wall-clock) time; it only orders events so that if event A happened
before event B, then L(A) < L(B).
"""
import threading


class LamportClock:
    """Thread-safe Lamport logical clock."""

    def __init__(self):
        self._value = 0
        self._lock = threading.Lock()

    def tick(self):
        """Advance the clock before a local event (send / apply). Returns the new value."""
        with self._lock:
            self._value += 1
            return self._value

    def receive(self, received_time):
        """Update the clock when a message arrives: L = max(local, received) + 1.

        Returns the new value.
        """
        with self._lock:
            self._value = max(self._value, int(received_time)) + 1
            return self._value

    def value(self):
        """Return the current clock value without advancing it."""
        with self._lock:
            return self._value
