from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit

import httpx

from tractor.core.deduplication import normalize_url
from tractor.credentials import RequestAuth, redact, redact_bytes
from tractor.network.throttling import RateLimiter
from tractor.storage.cache import ResponseCache

USER_AGENT = "TRACTOR/0.5 (+https://github.com/nightwarelabz/tractor; public research)"
SEARCH_HTML_HOSTS = frozenset({"html.duckduckgo.com"})
API_HOSTS = frozenset(
    {
        "api.github.com",
        "api.crossref.org",
        "archive.org",
        "commons.wikimedia.org",
        "www.wikidata.org",
        "www.ebi.ac.uk",
        "api.gdeltproject.org",
        "api.search.brave.com",
        "www.mojeek.com",
        "kagi.com",
        "api2.marginalia-search.com",
        "index.commoncrawl.org",
        *SEARCH_HTML_HOSTS,
    }
)


class NetworkPolicyError(ValueError):
    pass


class SourceUnavailable(RuntimeError):
    def __init__(
        self, message: str, *, status_code: int | None = None, category: str = "unavailable"
    ):
        super().__init__(redact(message))
        self.status_code = status_code
        self.category = category
        self.details: dict = {}


@dataclass
class RequestStats:
    network: int = 0
    cached: int = 0
    redirects: list[str] = field(default_factory=list)
    rate_limits: int = 0


class NetworkContext(Protocol):
    tor: bool

    async def get_json(self, url: str, params=None, **kwargs) -> Any: ...
    async def get_text(self, url: str, params=None, **kwargs) -> str: ...
    async def get_search_html(self, url: str, params=None, **kwargs) -> str: ...


class NetworkClient:
    def __init__(
        self,
        cache: ResponseCache | None = None,
        *,
        allowed_hosts: frozenset[str] = API_HOSTS,
        allowed_origins: frozenset[str] = frozenset(),
        transport: httpx.AsyncBaseTransport | None = None,
        proxy: str | None = None,
        tor: bool = False,
        timeout: httpx.Timeout | None = None,
    ):
        self.cache, self.allowed_hosts, self.allowed_origins = cache, allowed_hosts, allowed_origins
        self.tor = tor
        if tor and (not proxy or not proxy.startswith("socks5h://")):
            raise NetworkPolicyError("Tor requires an explicit socks5h proxy with remote DNS.")
        self.limiter = RateLimiter()
        # Authenticated responses never enter the persistent HTTP cache. This small, per-run
        # cache avoids paying again when a large provider page is consumed in local chunks.
        self._private_cache: dict[str, tuple[float, bytes, dict[str, str]]] = {}
        self.http = httpx.AsyncClient(
            timeout=timeout or httpx.Timeout(15, connect=8),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            proxy=proxy if transport is None else None,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Accept-Language": "en",
            },
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )

    def validate(self, url: str) -> str:
        normalized = normalize_url(url)
        parts = urlsplit(normalized)
        host = parts.hostname or ""
        if self.tor != host.endswith(".onion"):
            raise NetworkPolicyError("Onion and clearnet requests require separate clients.")
        if not self.tor and f"{parts.scheme}://{parts.netloc}" in self.allowed_origins:
            return normalized
        if host not in self.allowed_hosts:
            raise NetworkPolicyError("Host is not registered in this network context.")
        if parts.port not in (None, 80, 443):
            raise NetworkPolicyError("Nonstandard remote ports are not allowed.")
        if not self.tor and parts.scheme != "https":
            raise NetworkPolicyError("Public API requests require HTTPS.")
        return normalized

    async def get_json(
        self,
        url: str,
        params=None,
        *,
        interval=1.0,
        ttl=3600,
        stats=None,
        auth: RequestAuth | None = None,
        body=None,
        provider="",
    ) -> Any:
        raw, _ = await self._get(
            url,
            params,
            interval=interval,
            ttl=ttl,
            stats=stats,
            kind="json",
            accepted={"application/json", "text/json"}
            | ({"text/x-cdxj"} if urlsplit(url).hostname == "index.commoncrawl.org" else set()),
            max_bytes=4 * 1024 * 1024,
            auth=auth,
            body=body,
            provider=provider,
        )
        try:
            return redact(json.loads(raw))
        except (json.JSONDecodeError, UnicodeError):
            raise SourceUnavailable("Invalid JSON response", category="contract") from None

    async def get_ndjson(self, url: str, params=None, *, interval=2.0, ttl=3600, stats=None):
        # Only the registered index API exposes this path; this does not enable page retrieval.
        if self.tor or urlsplit(url).hostname != "index.commoncrawl.org":
            raise NetworkPolicyError("NDJSON is restricted to the Common Crawl index API.")
        raw, _ = await self._get(
            url,
            params,
            interval=interval,
            ttl=ttl,
            stats=stats,
            kind="ndjson",
            accepted={"application/json", "application/x-ndjson", "text/x-ndjson", "text/x-cdxj"},
            max_bytes=4 * 1024 * 1024,
        )
        try:
            rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        except (ValueError, UnicodeError):
            raise SourceUnavailable("Invalid index response", category="contract") from None
        if any(not isinstance(row, dict) for row in rows):
            raise SourceUnavailable("Invalid index records", category="contract")
        return redact(rows)

    async def get_text(self, url: str, params=None, *, interval=2.0, ttl=900, stats=None) -> str:
        if not self.tor:
            raise NetworkPolicyError("HTML retrieval requires an explicit Tor source context.")
        raw, headers = await self._get(
            url,
            params,
            interval=interval,
            ttl=ttl,
            stats=stats,
            kind="text",
            accepted={"text/html", "text/plain", "application/xhtml+xml"},
            max_bytes=2 * 1024 * 1024,
        )
        return redact(
            httpx.Response(
                200,
                content=raw,
                headers={"content-type": headers.get("content-type", "text/plain")},
            ).text
        )

    async def get_search_html(
        self, url: str, params=None, *, interval=2.0, ttl=900, stats=None, provider=""
    ) -> str:
        """Read only registered public search-result pages, never destination websites."""
        parts = urlsplit(url)
        host = parts.hostname or ""
        if self.tor or host not in SEARCH_HTML_HOSTS or parts.path != "/html/":
            raise NetworkPolicyError(
                "HTML search requests are restricted to registered search hosts."
            )
        raw, headers = await self._get(
            url,
            params,
            interval=interval,
            ttl=ttl,
            stats=stats,
            kind="search_html",
            accepted={"text/html", "application/xhtml+xml"},
            max_bytes=2 * 1024 * 1024,
            provider=provider,
        )
        return redact(
            httpx.Response(
                200,
                content=raw,
                headers={"content-type": headers.get("content-type", "text/html")},
            ).text
        )

    async def _get(
        self,
        url,
        params,
        *,
        interval,
        ttl,
        stats,
        kind,
        accepted,
        max_bytes,
        auth=None,
        body=None,
        provider="",
    ):
        stats = stats if stats is not None else RequestStats()
        params = dict(params or {})
        url = self.validate(url)
        origin = "{0.scheme}://{0.netloc}".format(urlsplit(url))
        headers = {"Accept": ", ".join(sorted(accepted))}
        private_scope = ""
        if auth:
            if self.tor or origin != auth.origin or urlsplit(url).scheme != "https":
                raise NetworkPolicyError(
                    "Credentials are restricted to the provider's HTTPS origin."
                )
            secret = auth.credential.value
            private_scope = hashlib.sha256(secret.encode()).hexdigest()
            if auth.query_parameter:
                params[auth.query_parameter] = secret
            else:
                headers[auth.header] = auth.prefix + secret
        current = self.validate(str(httpx.URL(url, params=params or None)))
        key = hashlib.sha256(
            json.dumps(
                ["tor" if self.tor else "clear", provider, kind, current, body, private_scope],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        if ttl > 0:
            if auth:
                cached = self._private_cache.get(key)
                if cached and cached[0] > time.monotonic():
                    stats.cached += 1
                    return cached[1], cached[2]
            else:
                cached = self.cache.get(key) if self.cache else None
                if cached:
                    stats.cached += 1
                    return cached.body, cached.headers
        # Total timeout includes connection, body, retries and throttling; the engine also
        # bounds an investigation. Slow Tor has its own outer deadline.
        try:
            async with asyncio.timeout(75 if self.tor else 60):
                return await self._request(
                    current,
                    headers,
                    body,
                    auth,
                    key,
                    kind,
                    accepted,
                    max_bytes,
                    interval,
                    ttl,
                    stats,
                )
        except TimeoutError:
            raise SourceUnavailable(
                "Source request deadline exceeded", category="timeout"
            ) from None

    async def _request(
        self, current, headers, body, auth, key, kind, accepted, max_bytes, interval, ttl, stats
    ):
        for _redirect in range(5):
            self.validate(current)
            for attempt in range(3):
                await self.limiter.wait(urlsplit(current).hostname or "", interval)
                try:
                    stats.network += 1
                    async with self.http.stream(
                        "POST" if body is not None else "GET", current, headers=headers, json=body
                    ) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise SourceUnavailable(
                                    "Redirect without a destination", category="contract"
                                )
                            target = self.validate(urljoin(current, location))
                            if auth:
                                raise NetworkPolicyError(
                                    "Authenticated API redirects are disabled."
                                )
                            current = target
                            stats.redirects.append(redact(current))
                            break
                        if response.status_code == 429:
                            stats.rate_limits += 1
                        if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                            retry = response.headers.get("retry-after", "")
                            delay = float(retry) if retry.isdigit() else 2**attempt
                            if delay > 20:
                                raise SourceUnavailable(
                                    "Provider requested a longer cooldown",
                                    status_code=response.status_code,
                                    category="rate_limited",
                                )
                            await asyncio.sleep(max(delay, 2**attempt))
                            continue
                        error_details = {}
                        if response.status_code >= 400:
                            error_body = b""
                            async for chunk in response.aiter_bytes():
                                error_body += chunk[: max(0, 4096 - len(error_body))]
                                if len(error_body) >= 4096:
                                    break
                            try:
                                candidate = json.loads(error_body)
                                error_details = (
                                    redact(candidate) if isinstance(candidate, dict) else {}
                                )
                            except (ValueError, UnicodeError):
                                pass
                        response.raise_for_status()
                        content_type = (
                            response.headers.get("content-type", "").split(";")[0].lower().strip()
                        )
                        if content_type not in accepted:
                            raise SourceUnavailable(
                                "Provider returned an unsupported content type", category="contract"
                            )
                        chunks, size = [], 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > max_bytes:
                                raise SourceUnavailable(
                                    "Response exceeded the source size limit", category="size_limit"
                                )
                            chunks.append(chunk)
                        raw = b"".join(chunks)
                        if kind == "json":
                            # Remove credential echoes before caching or parsing.
                            raw = json.dumps(redact(json.loads(raw)), ensure_ascii=False).encode()
                        elif kind == "ndjson":
                            raw = b"\n".join(
                                json.dumps(redact(json.loads(line)), ensure_ascii=False).encode()
                                for line in raw.splitlines()
                                if line.strip()
                            )
                        else:
                            raw = redact_bytes(raw)
                        safe_headers = {
                            "content-type": response.headers.get("content-type", ""),
                            "cache-control": response.headers.get("cache-control", ""),
                        }
                        safe_headers = redact(safe_headers)
                        if auth:
                            control = safe_headers["cache-control"].lower()
                            if ttl > 0 and not any(v in control for v in ("no-store", "no-cache")):
                                if len(self._private_cache) >= 32:
                                    self._private_cache.pop(next(iter(self._private_cache)))
                                self._private_cache[key] = (
                                    time.monotonic() + min(ttl, 900, self._max_age(control)),
                                    raw,
                                    safe_headers,
                                )
                        elif self.cache:
                            self.cache.put(key, raw, safe_headers, ttl)
                        return raw, safe_headers
                except (httpx.TimeoutException, httpx.NetworkError, httpx.ProxyError) as exc:
                    if attempt == 2:
                        category = (
                            "timeout" if isinstance(exc, httpx.TimeoutException) else "network"
                        )
                        raise SourceUnavailable(type(exc).__name__, category=category) from None
                    await asyncio.sleep(2**attempt)
                except httpx.HTTPStatusError as exc:
                    code = exc.response.status_code
                    category = (
                        "credential"
                        if code in {401, 403}
                        else "rate_limited"
                        if code == 429
                        else "unavailable"
                    )
                    failure = SourceUnavailable(f"HTTP {code}", status_code=code, category=category)
                    failure.details = error_details
                    raise failure from None
                except (json.JSONDecodeError, UnicodeError, httpx.DecodingError):
                    raise SourceUnavailable(
                        "Invalid provider response", category="contract"
                    ) from None
            else:
                raise SourceUnavailable("Request retry limit reached")
        raise SourceUnavailable("Redirect limit reached", category="redirect")

    @staticmethod
    def _max_age(control):
        import re

        match = re.search(r'(?:^|,)\s*max-age\s*=\s*"?(\d+)', control)
        return int(match[1]) if match else 900

    async def close(self):
        self._private_cache.clear()
        await self.http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.close()
