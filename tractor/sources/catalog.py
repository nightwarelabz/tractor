"""One provider catalog for CLI, settings, configuration snapshots and profiles."""

from dataclasses import asdict

from tractor.credentials import PROVIDER_ENV, Credentials
from tractor.sources import default_adapters
from tractor.sources.capabilities import capabilities
from tractor.sources.common_crawl import CommonCrawl
from tractor.sources.images import CommonsImages
from tractor.sources.onion import OnionSearxNG, TorchSearch
from tractor.sources.search import search_adapters
from tractor.sources.web import SearxNG

PROVIDER_IDS = tuple(a.id for a in default_adapters()) + (
    "duckduckgo",
    "commons_images",
    "brave",
    "mojeek",
    "kagi",
    "marginalia",
    "searxng",
    "common_crawl",
    "torch",
    "onion_searxng",
)
PROFILES = {
    "General": {
        "duckduckgo", "commons_images", "brave", "mojeek", "kagi", "marginalia",
        "searxng", "wikidata", "gdelt",
    },
    "Academic": {"crossref", "europe_pmc", "wikidata", "brave", "searxng"},
    "Historical": {"internet_archive", "common_crawl", "wikidata", "brave", "mojeek"},
    "Code": {"github", "brave", "mojeek", "searxng"},
    "News": {"gdelt", "brave", "kagi", "searxng"},
    "Maximum coverage": set(PROVIDER_IDS),
}


def catalog(settings, base=None):
    credentials = Credentials()
    adapters = [
        *search_adapters(settings.search, credentials),
        CommonsImages(settings.search, credentials),
        *(default_adapters() if base is None else base),
        CommonCrawl(settings.search),
        TorchSearch(),
    ]
    if settings.web_endpoint:
        adapters.append(SearxNG(settings.web_endpoint, settings.search))
    if settings.onion_endpoint:
        adapters.append(OnionSearxNG(settings.onion_endpoint, settings.search))
    return adapters


def configuration(settings, selected=None) -> dict:
    selected = settings.sources if selected is None else selected
    available = {a.id: a for a in catalog(settings)}
    credentials = Credentials()
    result = {}
    for key in PROVIDER_IDS:
        adapter = available.get(key)
        state = "Configured" if adapter else "Server missing"
        if key in PROVIDER_ENV:
            state = credentials.status(key)
        if key == "mojeek" and state == "Configured" and not settings.search.mojeek_storage_allowed:
            state = "Storage eligibility required"
        result[key] = {
            "name": adapter.name if adapter else key,
            "enabled": key in selected,
            "configuration": state,
            "environment_variable": PROVIDER_ENV.get(key),
            "network": getattr(adapter, "network", "clearnet"),
            "capabilities": asdict(capabilities(adapter)) if adapter else {},
            "index_family": getattr(adapter, "index_family", ""),
        }
    return result


def select_profile(settings, profile):
    if profile not in PROFILES:
        raise ValueError("Unknown search profile.")
    configured = configuration(settings)
    return [
        key
        for key in PROVIDER_IDS
        if key in PROFILES[profile]
        and configured[key]["configuration"] in {"Configured", "Shared development key"}
    ]
