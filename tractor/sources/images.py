"""Image search through Wikimedia Commons with reusable license attribution."""

from tractor.core.models import SourceType
from tractor.network.client import SourceUnavailable
from tractor.sources.base import SearchBatch
from tractor.sources.capabilities import ProviderCapabilities
from tractor.sources.parsing import plain_text
from tractor.sources.search.base import SearchProvider


class CommonsImages(SearchProvider):
    id, name = "commons_images", "Wikimedia Commons Images"
    description = "Image files from Wikimedia Commons with license and creator attribution."
    endpoint = "https://commons.wikimedia.org/w/api.php"
    index_family = "wikimedia_commons"
    capabilities = ProviderCapabilities(images=True, pagination=True, independent_index=True)

    async def search(self, query, context):
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": query.value,
            "gsrnamespace": 6,
            "gsrlimit": min(context.limit, 20),
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "iiurlwidth": 640,
        }
        if context.cursor:
            params["gsroffset"] = context.cursor
        data = await context.client.get_json(
            self.endpoint,
            params,
            interval=1.0,
            ttl=1800,
            stats=context.stats,
            provider=self.id,
        )
        if not isinstance(data, dict) or not isinstance(data.get("query", {}), dict):
            raise SourceUnavailable(
                "Wikimedia Commons returned an invalid search response", category="contract"
            )
        pages = data.get("query", {}).get("pages", {})
        results = []
        for rank, item in enumerate(pages.values(), start=1):
            info = (item.get("imageinfo") or [{}])[0]
            original = info.get("url", "")
            thumbnail = info.get("thumburl", original)
            if not original.startswith("https://upload.wikimedia.org/"):
                continue
            if not thumbnail.startswith("https://upload.wikimedia.org/"):
                thumbnail = original
            metadata = info.get("extmetadata", {})

            def field(key, extmetadata=metadata):
                value = extmetadata.get(key, {})
                return plain_text(value.get("value", ""))[:500] if isinstance(value, dict) else ""

            title = item.get("title", "Image")
            result = self.result(
                {
                    "title": plain_text(title),
                    "url": original,
                    "description": field("ImageDescription"),
                },
                query=query,
                page=context.page,
                rank=rank,
                snippet="description",
                thumbnail_url=thumbnail,
                file_page="https://commons.wikimedia.org/wiki/" + title.replace(" ", "_"),
                license=field("LicenseShortName"),
                license_url=field("LicenseUrl"),
                artist=field("Artist"),
                credit=field("Credit"),
            )
            result.source_type = SourceType.IMAGE
            result.metadata["search_engine"] = self.id
            results.append(result)
        continuation = data.get("continue", {}).get("gsroffset")
        return SearchBatch(
            results,
            truncated=continuation is not None,
            next_cursor=str(continuation) if continuation is not None else None,
        )
