"""Capabilities describe implemented behavior, never a provider's entire product range."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCapabilities:
    web: bool = False
    images: bool = False
    news: bool = False
    academic: bool = False
    archive: bool = False
    code: bool = False
    onion: bool = False
    historical: bool = False
    pagination: bool = False
    languages: bool = False
    regions: bool = False
    freshness: bool = False
    site_filter: bool = False
    quoted_queries: bool = False
    requires_credentials: bool = False
    independent_index: bool = False


SPECIALIZED_CAPABILITIES = {
    "wikidata": ProviderCapabilities(pagination=True, languages=True),
    "crossref": ProviderCapabilities(academic=True, pagination=True),
    "europe_pmc": ProviderCapabilities(academic=True, pagination=True),
    "internet_archive": ProviderCapabilities(archive=True, historical=True, pagination=True),
    "github": ProviderCapabilities(code=True, pagination=True),
    "gdelt": ProviderCapabilities(news=True),
    "torch": ProviderCapabilities(onion=True, pagination=True, independent_index=True),
    "onion_searxng": ProviderCapabilities(onion=True, pagination=True, languages=True),
    "commons_images": ProviderCapabilities(images=True, pagination=True),
}


def capabilities(adapter) -> ProviderCapabilities:
    return getattr(
        adapter, "capabilities", SPECIALIZED_CAPABILITIES.get(adapter.id, ProviderCapabilities())
    )
