"""Startup behaviour of the loopback search service Orc launches.

Regression coverage for the release-blocking race: a previous instance's
service can still hold the shared port (with a different data dir's
token) for a few seconds after its owner exits. A new instance must
outlive that predecessor instead of failing its single bind attempt,
and a same-data-dir sibling must join the running service by
registering rather than starting a second one.

Each scenario runs as its own process (tests/serve_scenario.py), the
way Orc actually launches the service, so no state leaks between them.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCENARIO = Path(__file__).with_name("serve_scenario.py")


def _wait_stack_clear(timeout=120.0):
    """Wait until the shared port can be bound again.

    A finished scenario leaves TIME_WAIT sockets behind; some network
    stacks hold those against new binds far longer than the standard
    interval. Probing with the same server socket the service uses
    keeps the handoff honest without creating new connections.
    """
    import time
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from tractor.search_service import HOST, PORT

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            probe = HTTPServer((HOST, PORT), BaseHTTPRequestHandler)
            probe.server_close()
            return
        except OSError:
            time.sleep(1)
    raise AssertionError("port never became bindable again")


def _run(mode: str, data_dir: Path):
    _wait_stack_clear()
    proc = subprocess.run(
        [sys.executable, str(SCENARIO), mode, str(data_dir)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"{mode} scenario failed:\n{proc.stdout}\n{proc.stderr}"
    return proc.stdout


def test_serve_outlives_foreign_port_holder(tmp_path):
    out = _run("outlive", tmp_path)
    assert "READY" in out and "STOPPED" in out


def test_second_instance_registers_with_running_service(tmp_path):
    out = _run("register", tmp_path)
    assert "JOINED" in out and "STOPPED" in out
