"""Standalone startup scenarios for the loopback search service.

Run by tests/test_search_service.py as separate processes, exactly the
way Orc launches the service: isolated processes, one shared port.
Prints a marker per phase; exits non-zero on the first failure.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from tractor.search_service import HOST, PORT, serve


def wait_ready(timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://{HOST}:{PORT}/search", timeout=2) as r:
                if r.status == 200:
                    return True
        except OSError:
            time.sleep(0.1)
    return False


def short_lived_parent(seconds=6):
    parent = subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({seconds})"])
    # Reap the child when it exits, as init does for the real owner (the
    # Orc engine). An unreaped zombie still answers os.kill(pid, 0), so
    # without this the service would correctly see its owner as alive.
    threading.Thread(target=parent.wait, daemon=True).start()
    return parent


def fail(message):
    print(f"FAIL: {message}", flush=True)
    return 1


def outlive(data_dir: Path):
    holder = socket.socket()
    # The real predecessor is Tractor's own server socket, which sets
    # SO_REUSEADDR (http.server default); mirror that. A second active
    # listener on the same address still conflicts, as it should.
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind((HOST, PORT))
    holder.listen(1)
    parent = short_lived_parent()
    result = {}

    def run():
        try:
            result["rc"] = serve(data_dir, parent.pid)
        except Exception as exc:  # noqa: BLE001 - reported as a failure
            result["error"] = repr(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    time.sleep(1.5)
    holder.close()  # the predecessor exits; the port frees mid-retry
    if not wait_ready():
        return fail(f"service never became ready after the port freed: {result}")
    print("READY", flush=True)
    thread.join(timeout=25)
    if thread.is_alive():
        return fail("service did not stop after its owner exited")
    if result.get("rc") != 0:
        return fail(f"serve returned {result}")
    print("STOPPED", flush=True)
    return 0


def register(data_dir: Path):
    parent = short_lived_parent()
    first = threading.Thread(target=lambda: serve(data_dir, parent.pid), daemon=True)
    first.start()
    if not wait_ready():
        return fail("first service never became ready")
    print("READY", flush=True)
    started = time.monotonic()
    rc = serve(data_dir, parent.pid)  # same data dir: joins, returns at once
    if rc != 0:
        return fail(f"second serve returned {rc}")
    if time.monotonic() - started > 10:
        return fail("second serve did not join promptly")
    print("JOINED", flush=True)
    first.join(timeout=25)
    if first.is_alive():
        return fail("service did not stop after its owner exited")
    print("STOPPED", flush=True)
    return 0


if __name__ == "__main__":
    mode, data = sys.argv[1], Path(sys.argv[2])
    data.mkdir(parents=True, exist_ok=True)
    sys.exit(outlive(data) if mode == "outlive" else register(data))
