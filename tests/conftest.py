"""Shared test helpers: start/stop replicas on ephemeral ports.

These helpers let every test start its own servers (on OS-assigned ports) and
shut them down afterwards, so the suite needs no manual `python server.py`.
"""
import os
import sys

# Make the project root importable (so `import server`, `import client` work)
# no matter which directory pytest is launched from.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from server import create_server   # noqa: E402


class Replica:
    """A running replica plus the client address that reaches it."""

    def __init__(self, server, port, servicer, name):
        self.server = server
        self.port = port
        self.servicer = servicer
        self.name = name
        self.address = "127.0.0.1:%d" % port

    def stop(self):
        self.server.stop(0)


def start_replica(name="replica", fault=None, delay_ms=0):
    """Start one replica on an ephemeral port with logging disabled."""
    server, port, servicer = create_server(
        port=0, name=name, fault=fault, delay_ms=delay_ms, log_enabled=False)
    return Replica(server, port, servicer, name)
