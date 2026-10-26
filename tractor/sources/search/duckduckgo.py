"""General web results from DuckDuckGo's public HTML search interface."""

from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from tractor.core.models import SourceType
from tractor.network.client import SourceUnavailable
from tractor.sources.base import SearchBatch
from tractor.sources.capabilities import ProviderCapabilities
from tractor.sources.parsing import plain_text
from tractor.sources.search.base import SearchProvider


class DuckDuckGoSearch(SearchProvider):
    id, name = "duckduckgo", "DuckDuckGo Web"
    description = "General web search through DuckDuckGo's public HTML results."
    endpoint = "https://html.duckduckgo.com/html/"
    index_family = "duckduckgo"
    capabilities = ProviderCapabilities(web=True, pagination=True, independent_index=True)

    async def search(self, query, context):
        try:
            page = int(context.cursor or "1")
        except (TypeError, ValueError):
            raise SourceUnavailable("Saved provider cursor is invalid", category="cursor") from None
        if not 1 <= page <= 100:
            raise SourceUnavailable("Saved provider cursor is invalid", category="cursor")
        html = await context.client.get_search_html(
            self.endpoint,
            {"q": query.value, "s": (page - 1) * 30, "kl": "us-en"},
            interval=2.0,
            ttl=600,
            stats=context.stats,
            provider=self.id,
        )
        soup = BeautifulSoup(html, "html.parser")
        results = []
        rows = soup.select(".result")
        for rank, item in enumerate(rows, start=(page - 1) * 30 + 1):
            link = item.select_one("a.result__a")
            if not link:
                continue
            url = link.get("href", "")
            parts = urlsplit(url)
            if parts.hostname == "duckduckgo.com" and parts.path.startswith("/l/"):
                url = parse_qs(parts.query).get("uddg", [""])[0]
            if not url.startswith(("https://", "http://")):
                continue
            snippet = item.select_one(".result__snippet")
            result = self.result(
                {
                    "title": plain_text(link.get_text(" ", strip=True)),
                    "url": url,
                    "description": plain_text(snippet.get_text(" ", strip=True)) if snippet else "",
                },
                query=query,
                page=page,
                rank=rank,
                snippet="description",
            )
            result.source_type = SourceType.WEB
            results.append(result)
            if len(results) >= context.limit:
                break
        more = len(rows) >= 10
        return SearchBatch(
            results,
            truncated=more,
            next_cursor=str(page + 1) if more else None,
            warnings=["Results are DuckDuckGo snippets; destination pages are not fetched."],
        )
