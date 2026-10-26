"""Loopback-only search endpoint used by the Orc browser integration."""

from __future__ import annotations

import asyncio
import errno
import json
import logging
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from tractor.core.engine import InvestigationEngine
from tractor.network.session import configured_adapters, network_session
from tractor.settings import Settings
from tractor.sources import default_adapters
from tractor.storage.cache import ResponseCache
from tractor.storage.database import Database

HOST = "127.0.0.1"
PORT = 45873
ORIGIN = f"http://{HOST}:{PORT}"
MAX_QUERY_LENGTH = 500
MAX_BODY = 8192
log = logging.getLogger("tractor.search_service")


class SearchService(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, data_dir: Path, token: str, parent_pid: int | None):
        self.data_dir = data_dir
        self.token = token
        self.jobs: dict[str, dict] = {}
        self.jobs_lock = threading.RLock()
        self.owners = {parent_pid} if parent_pid else set()
        self.owners_lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tractor-search")
        super().__init__((HOST, PORT), SearchHandler)


class SearchHandler(BaseHTTPRequestHandler):
    server: SearchService
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Never write user queries or source URLs into the service log.
        log.info("http %s", args[1] if len(args) > 1 else "request")

    def _headers(self, content_type="application/json; charset=utf-8"):
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' https://upload.wikimedia.org; "
            "style-src 'self'; script-src 'self'; connect-src 'self'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
        )
        self.send_header("X-Frame-Options", "DENY")

    def _send(self, status, payload, content_type="application/json; charset=utf-8"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._headers(content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _safe_request(self):
        if self.headers.get("Host", "").lower() != f"{HOST}:{PORT}":
            self._send(400, {"error": "Invalid local host"})
            return False
        origin = self.headers.get("Origin")
        if origin and origin != ORIGIN:
            self._send(403, {"error": "Cross-origin requests are not allowed"})
            return False
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            self._send(403, {"error": "Cross-origin requests are not allowed"})
            return False
        return True

    def _authorized(self):
        if not self._safe_request():
            return False
        if self.headers.get("X-Tractor-Token", "") != self.server.token:
            self._send(403, {"error": "Search service authorization failed"})
            return False
        if self.headers.get("X-Requested-With") != "TractorSearch":
            self._send(403, {"error": "Search service authorization failed"})
            return False
        return True

    def _body(self):
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._send(415, {"error": "JSON requests are required"})
            return None
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = MAX_BODY + 1
        if not 0 < length <= MAX_BODY:
            self._send(413, {"error": "Search request is too large"})
            return None
        try:
            value = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError):
            self._send(400, {"error": "Invalid JSON request"})
            return None
        if not isinstance(value, dict):
            self._send(400, {"error": "Invalid search request"})
            return None
        return value

    def do_GET(self):
        if not self._safe_request():
            return
        path = urlsplit(self.path).path
        if path == "/search":
            page = files("tractor").joinpath("search_ui/index.html").read_bytes()
            return self._send(200, page, "text/html; charset=utf-8")
        if path == "/search-ui/app.js":
            page = files("tractor").joinpath("search_ui/app.js").read_bytes()
            return self._send(200, page, "text/javascript; charset=utf-8")
        if path == "/search-ui/style.css":
            page = files("tractor").joinpath("search_ui/style.css").read_bytes()
            return self._send(200, page, "text/css; charset=utf-8")
        if path == "/assets/icon.svg":
            image = files("tractor").joinpath("assets/icon.svg").read_bytes()
            return self._send(200, image, "image/svg+xml")
        if path == "/api/bootstrap":
            return self._send(200, {"token": self.server.token})
        if not self._authorized():
            return
        if path.startswith("/api/jobs/"):
            job_id = path.removeprefix("/api/jobs/")
            if len(job_id) != 32 or any(ch not in "0123456789abcdef" for ch in job_id):
                return self._send(404, {"error": "Search not found"})
            with self.server.jobs_lock:
                job = self.server.jobs.get(job_id)
                if not job:
                    return self._send(404, {"error": "Search not found"})
                return self._send(200, _job_view(job))
        return self._send(404, {"error": "Not found"})

    def do_POST(self):
        if not self._safe_request():
            return
        path = urlsplit(self.path).path
        if path == "/internal/register":
            token = self.headers.get("X-Tractor-Token", "")
            if self.client_address[0] != HOST or token != self.server.token:
                return self._send(403, {"error": "Registration rejected"})
            data = self._body()
            if data is None:
                return
            try:
                parent_pid = int(data.get("parent_pid", 0))
            except (ValueError, TypeError):
                parent_pid = 0
            if parent_pid <= 0:
                return self._send(400, {"error": "Invalid parent process"})
            with self.server.owners_lock:
                self.server.owners.add(parent_pid)
            return self._send(200, {"registered": True})
        if not self._authorized():
            return
        if path != "/api/search":
            return self._send(404, {"error": "Not found"})
        data = self._body()
        if data is None:
            return
        query = data.get("query")
        if not isinstance(query, str) or not query.strip():
            return self._send(400, {"error": "Enter a search query"})
        query = query.strip()[:MAX_QUERY_LENGTH]
        job_id = uuid4().hex
        job = {
            "id": job_id,
            "query": query,
            "status": "queued",
            "snapshot": None,
            "cancelled": threading.Event(),
            "error": "",
            "created_at": time.time(),
        }
        with self.server.jobs_lock:
            self.server.jobs[job_id] = job
            # Bound the in-memory job table while leaving current searches alone.
            completed = sorted(
                (
                    item
                    for item in self.server.jobs.values()
                    if item["status"] not in {"queued", "running"}
                ),
                key=lambda item: item["created_at"],
            )
            for stale in completed[:-40]:
                self.server.jobs.pop(stale["id"], None)
        self.server.pool.submit(_run_search, self.server, job_id, query)
        return self._send(202, {"id": job_id})

    def do_DELETE(self):
        if not self._authorized():
            return
        path = urlsplit(self.path).path
        if not path.startswith("/api/jobs/"):
            return self._send(404, {"error": "Not found"})
        job_id = path.removeprefix("/api/jobs/")
        with self.server.jobs_lock:
            job = self.server.jobs.get(job_id)
            if not job:
                return self._send(404, {"error": "Search not found"})
            job["cancelled"].set()
        return self._send(202, {"stopping": True})


def _job_view(job):
    snapshot = job.get("snapshot") or {}
    results = []
    for item in snapshot.get("results", []):
        metadata = item.get("metadata", {})
        url = item.get("url", "")
        if urlsplit(url).scheme not in {"http", "https"}:
            continue
        thumbnail = metadata.get("thumbnail_url", "")
        if not thumbnail.startswith("https://upload.wikimedia.org/"):
            thumbnail = ""
        file_page = metadata.get("file_page", "")
        if urlsplit(file_page).hostname != "commons.wikimedia.org":
            file_page = ""
        license_url = metadata.get("license_url", "")
        if urlsplit(license_url).scheme not in {"http", "https"}:
            license_url = ""
        results.append(
            {
                "title": item.get("title") or url,
                "url": url,
                "excerpt": item.get("excerpt") or item.get("original_text") or "",
                "source_type": item.get("source_type", "WEB"),
                "source_provider": item.get("source_provider", "tractor"),
                "thumbnail_url": thumbnail,
                "file_page": file_page,
                "license": metadata.get("license", ""),
                "license_url": license_url,
                "artist": metadata.get("artist", ""),
            }
        )
    coverage = snapshot.get("coverage", {})
    return {
        "id": job["id"],
        "status": snapshot.get("status", job.get("status", "queued")),
        "stop_reason": snapshot.get("stop_reason", ""),
        "results": results,
        "providers": coverage.get("sources_attempted", 0),
        "error": job.get("error", ""),
    }


def _run_search(server: SearchService, job_id: str, query: str):
    with server.jobs_lock:
        job = server.jobs.get(job_id)
        if not job:
            return
        job["status"] = "running"

    def event(name, payload):
        if name == "snapshot":
            with server.jobs_lock:
                current = server.jobs.get(job_id)
                if current:
                    current["snapshot"] = payload
                    current["status"] = payload.get("status", "running")

    try:
        asyncio.run(_run_engine(server.data_dir, query, job_id, job["cancelled"], event))
    except Exception as exc:
        log.error("Search job %s failed (%s)", job_id, type(exc).__name__)
        with server.jobs_lock:
            current = server.jobs.get(job_id)
            if current:
                current["status"] = "failed"
                current["error"] = (
                    "Tractor could not complete this search. Check local history for details."
                )
    finally:
        with server.jobs_lock:
            current = server.jobs.get(job_id)
            if current and current["status"] in {"queued", "running"}:
                current["status"] = "failed"
                current["error"] = "Search ended before a result snapshot was available."


async def _run_engine(data_dir, query, job_id, cancelled, on_event):
    settings = Settings.load(data_dir)
    # Orc's default browser search is clearnet. Onion providers remain available in Tractor's
    # desktop app, where the user can configure Tor and choose them explicitly.
    selected = [key for key in settings.sources if key not in {"torch", "onion_searxng"}]
    for key in ("duckduckgo", "commons_images"):
        if key not in selected:
            selected.append(key)
    adapters = configured_adapters(settings, default_adapters(), selected)
    with Database(data_dir / "investigations.sqlite3") as database:
        async with network_session(
            settings,
            adapters,
            data_dir,
            ResponseCache(database.connection),
        ) as (client, contexts):
            engine = InvestigationEngine(
                adapters,
                client,
                database,
                cancelled=cancelled,
                network_contexts=contexts,
                search_options={
                    "language": settings.search.language,
                    "region": settings.search.region,
                    "freshness": settings.search.freshness,
                    "category": settings.search.category,
                },
                profile=settings.profile,
                on_event=on_event,
            )
            await engine.run(query, investigation_id=job_id)


def _read_or_create_token(data_dir: Path) -> str:
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = data_dir / "search-service.token"
    for _ in range(20):
        try:
            token = path.read_text(encoding="ascii").strip()
        except FileNotFoundError:
            break
        except OSError:
            token = ""
        if len(token) >= 40:
            os.chmod(path, 0o600)
            return token
        time.sleep(0.025)
    token = secrets.token_urlsafe(48)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # A peer created the file a moment ago and may not have written
        # it yet; an empty read inside that window is a race, not damage.
        for _ in range(20):
            token = path.read_text(encoding="ascii").strip()
            if len(token) >= 40:
                return token
            time.sleep(0.025)
        raise RuntimeError("Tractor's local search token is damaged") from None
    with os.fdopen(fd, "w", encoding="ascii") as stream:
        stream.write(token)
    return token


def _register_existing(data_dir: Path, parent_pid: int | None) -> bool:
    if not parent_pid:
        return False
    try:
        token = (data_dir / "search-service.token").read_text(encoding="ascii").strip()
        request = urllib.request.Request(
            f"{ORIGIN}/internal/register",
            data=json.dumps({"parent_pid": parent_pid}).encode("utf-8"),
            headers={
                "Host": f"{HOST}:{PORT}",
                "Content-Type": "application/json",
                "X-Tractor-Token": token,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError, ValueError):
        return False


def _write_pid(path: Path):
    staging = path.with_name(f".search-service-pid-{os.getpid()}")
    staging.write_text(str(os.getpid()), encoding="ascii")
    os.replace(staging, path)


def _parent_alive(pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_process.restype = wintypes.HANDLE
        wait_for_single_object = kernel32.WaitForSingleObject
        wait_for_single_object.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        wait_for_single_object.restype = wintypes.DWORD
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL
        handle = open_process(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            return wait_for_single_object(handle, 0) == 0x00000102  # WAIT_TIMEOUT
        finally:
            close_handle(handle)
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def serve(data_dir: Path, parent_pid: int | None = None):
    token = _read_or_create_token(data_dir)
    # The port is shared by every Orc instance on this machine, and a
    # previous instance's service can hold it briefly after its owner
    # exits (its reaper polls every 2 s). A same-token sibling service
    # is joined by registering; a foreign-token predecessor cannot be
    # joined, only outlived. Either way a single bind attempt is not
    # enough: retry until the deadline before declaring failure.
    deadline = time.monotonic() + 30
    while True:
        try:
            server = SearchService(data_dir, token, parent_pid)
            break
        except OSError as exc:
            if exc.errno not in {errno.EADDRINUSE, 48, 10048}:
                raise
            if _register_existing(data_dir, parent_pid):
                return 0
            if time.monotonic() >= deadline:
                raise RuntimeError("Tractor search could not bind its local service port") from None
            time.sleep(0.25)

    pid_file = data_dir / "search-service.pid"
    _write_pid(pid_file)

    def reap_closed_parents():
        while True:
            time.sleep(2)
            with server.owners_lock:
                server.owners = {pid for pid in server.owners if _parent_alive(pid)}
                empty = not server.owners
            if empty:
                server.shutdown()
                return

    if parent_pid:
        threading.Thread(
            target=reap_closed_parents, name="tractor-owner-watch", daemon=True
        ).start()
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.pool.shutdown(wait=False, cancel_futures=True)
        server.server_close()
        try:
            if pid_file.read_text(encoding="ascii").strip() == str(os.getpid()):
                pid_file.unlink()
        except OSError:
            pass
    return 0
