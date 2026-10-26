import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from tractor.core.convergence import Budget
from tractor.core.deduplication import normalize_url
from tractor.credentials import redact
from tractor.network.tor import onion_host, validate_proxy
from tractor.sources import default_adapters
from tractor.sources.base import SearchOptions
from tractor.storage.atomic import atomic_text


def validate_web_endpoint(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    parts = urlsplit(value)
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Use a server URL without credentials, query parameters, or fragments.")
    normalized = normalize_url(value)
    parts = urlsplit(normalized)
    if (parts.hostname or "").endswith(".onion"):
        raise ValueError("This setting accepts clearnet servers. Onion routing is separate.")
    if parts.scheme != "https" and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Use HTTPS, or HTTP for a server running on this computer.")
    return normalized.rstrip("/")


def endpoint_origin(endpoint: str) -> str:
    parts = urlsplit(endpoint)
    return f"{parts.scheme}://{parts.netloc}"


def validate_onion_endpoint(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    parts = urlsplit(value)
    onion_host(value)
    if (
        parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or parts.port not in (None, 80, 443)
    ):
        raise ValueError(
            "Use an onion server URL on port 80 or 443, without credentials or query parameters."
        )
    return normalize_url(value).rstrip("/")


@dataclass
class Settings:
    sources: list[str] = field(
        default_factory=lambda: (
            [a.id for a in default_adapters()] + ["duckduckgo", "commons_images", "torch"]
        )
    )
    web_endpoint: str = ""
    tor_proxy: str = ""
    tor_autostart: bool = True
    onion_endpoint: str = ""
    schema_version: int = 5
    search: SearchOptions = field(default_factory=SearchOptions)
    budget: Budget = field(default_factory=Budget)
    profile: str = "Custom"

    @classmethod
    def load(cls, data_dir: Path) -> "Settings":
        try:
            data = json.loads((data_dir / "settings.json").read_text(encoding="utf-8"))
            endpoint = validate_web_endpoint(data.get("web_endpoint", ""))
            onion = validate_onion_endpoint(data.get("onion_endpoint", ""))
            proxy = validate_proxy(data.get("tor_proxy", ""))
            defaults = {a.id for a in default_adapters()}
            valid = (
                defaults
                | {
                    "torch",
                    "duckduckgo",
                    "commons_images",
                    "brave",
                    "mojeek",
                    "kagi",
                    "marginalia",
                    "common_crawl",
                }
                | ({"searxng"} if endpoint else set())
            )
            valid |= {"onion_searxng"} if onion else set()
            selected = list(dict.fromkeys(key for key in data.get("sources", []) if key in valid))
            # Add the new default to an unchanged old default selection, preserving custom choices.
            if data.get("schema_version", 1) < 3 and defaults.issubset(selected):
                selected.append("torch")
            if data.get("schema_version", 1) < 5 and defaults.issubset(selected):
                selected.extend(
                    key for key in ("duckduckgo", "commons_images") if key not in selected
                )
            return cls(
                selected or cls().sources,
                endpoint,
                proxy,
                data.get("tor_autostart", True) is True,
                onion,
                search=SearchOptions(**data.get("search", {})),
                budget=Budget(**data.get("budget", {})),
                profile=data.get("profile", "Custom"),
            )
        except (OSError, ValueError, TypeError, AttributeError):
            return cls()

    def save(self, data_dir: Path) -> None:
        self.web_endpoint = validate_web_endpoint(self.web_endpoint)
        self.onion_endpoint = validate_onion_endpoint(self.onion_endpoint)
        self.tor_proxy = validate_proxy(self.tor_proxy)
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with atomic_text(data_dir / "settings.json") as file:
            json.dump(redact(asdict(self)), file, indent=2)

    @property
    def allowed_origins(self) -> frozenset[str]:
        return frozenset({endpoint_origin(self.web_endpoint)} if self.web_endpoint else set())
