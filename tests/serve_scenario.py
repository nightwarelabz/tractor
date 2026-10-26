"""Standalone startup scenarios for the loopback search service.

Run by tests/test_search_service.py as separate processes, exactly the
way Orc launches the service: isolated processes, one shared port.
Prints a marker per phase; exits non-zero on the first failure.
On a readiness failure it prints diagnostics (last poll error, raw
connect result, pid-file presence, thread stacks) so a CI failure
explains itself.
"""

from __future__ import annotations

import faulthandler
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

BOOT = time.monotonic()
print(f"BOOT pid={os.getpid()}", flush=True)

from tractor.search_service import HOST, PORT, serve  # noqa: E402

print(f"IMPORTED +{time.monotonic() - BOOT:.2f}s", flush=True)


def wait_ready(timeout=20.0):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://{HOST}:{PORT}/search", timeout=2) as r:
                if r.status == 200:
                    print(f"READY +{time.monotonic() - BOOT:.2f}s", flush=True)
                    return True, None
        except Exception as exc:  # noqa: BLE001 - reported as diagnostics
            last_error = repr(exc)
            time.sleep(0.1)
    return False, last_error


def diagnose(data_dir: Path, last_error):
    probe = socket.socket()
    probe.settimeout(2)
    try:
        rc = probe.connect_ex((HOST, PORT))
        connect = f"connect_ex={rc}"
    except Exception as exc:  # noqa: BLE001
        connect = f"connect_ex raised {exc!r}"
    finally:
        probe.close()
    pid_file = data_dir / "search-service.pid"
    print(
        f"DIAG last_poll_error={last_error} {connect} "
        f"pid_file={'present' if pid_file.exists() else 'absent'}",
        flush=True,
    )
    faulthandler.dump_traceback(file=sys.stdout)


def short_lived_parent(seconds=20):
    parent = subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({seconds})"])
    # Reap the child when it exits, as init does for the real owner (the
    # Orc engine). An unreaped zombie still answers os.kill(pid, 0), so
    # without this the service would correctly see its owner as alive.
    threading.Thread(target=parent.wait, daemon=True).start()
    return parent


def serve_runner(data_dir: Path, parent_pid: int, result: dict):
    def run():
        try:
            result["rc"] = serve(data_dir, parent_pid)
        except Exception as exc:  # noqa: BLE001 - reported as a failure
            result["error"] = repr(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def fail(message):
    print(f"FAIL: {message}", flush=True)
    return 1


def outlive(data_dir: Path):
    holder = socket.socket()
    # The real predecessor is Tractor's own server socket, which sets
    # SO_REUSEADDR on non-Windows; mirror that. A second active
    # listener on the same address still conflicts, as it should.
    holder.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    holder.bind((HOST, PORT))
    holder.listen(1)
    parent = short_lived_parent()
    result = {}
    thread = serve_runner(data_dir, parent.pid, result)
    time.sleep(1.5)
    holder.close()  # the predecessor exits; the port frees mid-retry
    ready, last_error = wait_ready()
    if not ready:
        diagnose(data_dir, last_error)
        return fail(f"service never became ready after the port freed: {result}")
    thread.join(timeout=35)
    if thread.is_alive():
        return fail("service did not stop after its owner exited")
    if result.get("rc") != 0:
        return fail(f"serve returned {result}")
    print("STOPPED", flush=True)
    return 0


def register(data_dir: Path):
    parent = short_lived_parent()
    result = {}
    first = serve_runner(data_dir, parent.pid, result)
    ready, last_error = wait_ready()
    if not ready:
        diagnose(data_dir, last_error)
        return fail(f"first service never became ready: {result}")
    started = time.monotonic()
    rc = serve(data_dir, parent.pid)  # same data dir: joins, returns at once
    if rc != 0:
        return fail(f"second serve returned {rc}")
    if time.monotonic() - started > 10:
        return fail("second serve did not join promptly")
    print("JOINED", flush=True)
    first.join(timeout=35)
    if first.is_alive():
        return fail("service did not stop after its owner exited")
    print("STOPPED", flush=True)
    return 0


if __name__ == "__main__":
    mode, data = sys.argv[1], Path(sys.argv[2])
    data.mkdir(parents=True, exist_ok=True)
    sys.exit(outlive(data) if mode == "outlive" else register(data))
