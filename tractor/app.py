import argparse
import asyncio
import json
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path

from platformdirs import user_data_path

from tractor.core.convergence import Budget
from tractor.core.engine import InvestigationEngine
from tractor.core.models import QueryVariant
from tractor.credentials import redact
from tractor.export.csv_export import export_csv
from tractor.export.json_export import export_json
from tractor.export.report import export_markdown
from tractor.logging_config import configure_logging
from tractor.network.client import SourceUnavailable
from tractor.network.session import configured_adapters, network_session
from tractor.settings import Settings
from tractor.sources import default_adapters
from tractor.sources.base import SearchContext
from tractor.sources.catalog import PROFILES, PROVIDER_IDS, configuration, select_profile
from tractor.storage.cache import ResponseCache
from tractor.storage.database import Database
from tractor.storage.health import provider_health


async def headless(
    query: str,
    data_dir: Path,
    output: Path | None,
    *,
    resume_id: str | None = None,
    sources: list[str] | None = None,
    tor_proxy: str | None = None,
    settings: Settings | None = None,
    markdown: Path | None = None,
    csv: Path | None = None,
    refresh_id: str | None = None,
) -> int:
    settings = settings or Settings.load(data_dir)
    selected = sources if sources is not None else settings.sources
    if tor_proxy is not None:
        from tractor.network.tor import validate_proxy

        settings.tor_proxy = validate_proxy(tor_proxy)
    adapters = configured_adapters(settings, default_adapters(), selected)
    with Database(data_dir / "investigations.sqlite3") as database:
        resume = database.load(resume_id) if resume_id else None
        if refresh_id:
            query = database.load(refresh_id).query
        async with network_session(
            settings,
            adapters,
            data_dir,
            None if refresh_id else ResponseCache(database.connection),
            on_status=lambda message: print(message, flush=True),
        ) as (client, contexts):
            engine = InvestigationEngine(
                adapters,
                client,
                database,
                network_contexts=contexts,
                budget=settings.budget,
                provider_configuration=configuration(settings, selected),
                search_options=asdict(settings.search),
                profile=settings.profile,
            )
            inv = await engine.run(query, resume=resume, previous_id=refresh_id)
            for path, export in (
                (output, export_json),
                (markdown, export_markdown),
                (csv, export_csv),
            ):
                if path:
                    export(inv, path)
            print(f"{inv.status}: {len(inv.unique_results)} unique results · {inv.stop_reason}")
            print(f"Investigation: {inv.id} · {len(inv.pending_tasks)} searches pending")
            for attempt in inv.attempts:
                if attempt.error or attempt.warnings:
                    print(
                        redact(
                            f"{attempt.provider}: "
                            + "; ".join(
                                ([attempt.error] if attempt.error else []) + attempt.warnings
                            )
                        )
                    )
            return 1 if inv.status == "failed" else 0


async def test_provider(settings, provider, data_dir):
    """One bounded search page; authenticated providers may charge for this request."""
    adapters = configured_adapters(settings, default_adapters(), [provider])
    async with network_session(settings, adapters, data_dir) as (direct, contexts):
        adapter = adapters[0]
        client = contexts.get(getattr(adapter, "network", "clearnet"), direct)
        context = SearchContext(client, limit=1)
        try:
            batch = await adapter.search(
                QueryVariant("example.org" if provider == "common_crawl" else "climate"), context
            )
        except SourceUnavailable as exc:
            print(redact(f"{provider}: {exc.category} · {exc}"))
            return 1
        except Exception as exc:
            print(f"{provider}: response contract failed ({type(exc).__name__})")
            return 1
        print(
            f"{provider}: {'partial' if batch.partial else 'reachable'} · "
            f"{len(batch.results)} records · "
            f"{context.stats.network} HTTP requests"
        )
        for warning in batch.warnings:
            print(redact(warning))
        return 1 if batch.partial else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="TRACTOR · Global Intelligence Search")
    parser.add_argument("--data-dir", type=Path, default=user_data_path("TRACTOR", appauthor=False))
    parser.add_argument("--debug", action="store_true", help="Enable structured debug logging")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--search", help="Run the investigation engine without the GUI")
    action.add_argument("--resume", help="Continue an investigation by its full ID")
    action.add_argument("--refresh", help="Run a fresh investigation from a saved ID")
    action.add_argument("--serve", action="store_true", help="Serve the local web search interface")
    parser.add_argument("--parent-pid", type=int, help=argparse.SUPPRESS)
    action.add_argument(
        "--history", nargs="?", const="", metavar="TEXT", help="Search local history"
    )
    action.add_argument(
        "--coverage", metavar="ID", help="Print saved coverage, configuration and health"
    )
    action.add_argument(
        "--providers", action="store_true", help="List configuration, capabilities and local health"
    )
    action.add_argument(
        "--test-provider",
        choices=PROVIDER_IDS,
        help="Make one bounded test search (may consume API credits)",
    )
    action.add_argument(
        "--benchmark", action="store_true", help="Run the versioned offline retrieval benchmark"
    )
    parser.add_argument(
        "--sources", nargs="+", choices=PROVIDER_IDS, help="Override providers for this run"
    )
    parser.add_argument(
        "--profile", choices=PROFILES, help="Use configured providers in a search profile"
    )
    parser.add_argument("--language", help="Language hint: auto, all, or a language code")
    parser.add_argument("--region", help="Two-letter region hint")
    parser.add_argument("--freshness", choices=["any", "day", "week", "month", "year", "custom"])
    parser.add_argument("--after", help="Custom freshness start, YYYY-MM-DD")
    parser.add_argument("--before", help="Custom freshness end, YYYY-MM-DD")
    parser.add_argument("--tor-proxy", help="Local socks5h proxy override")
    for name in asdict(Budget()):
        parser.add_argument(
            "--" + name.replace("_", "-"), type=float if name == "max_seconds" else int
        )
    parser.add_argument("--export-json", type=Path)
    parser.add_argument("--export-markdown", type=Path)
    parser.add_argument("--export-csv", type=Path)
    args = parser.parse_args()
    configure_logging(args.debug)
    try:
        settings = Settings.load(args.data_dir)
        if args.serve:
            from tractor.search_service import serve

            return serve(args.data_dir, args.parent_pid)
        if args.profile:
            settings.profile = args.profile
            settings.sources = select_profile(settings, args.profile)
            settings.search = replace(
                settings.search, category="news" if args.profile == "News" else "general"
            )
            if args.profile == "Maximum coverage":
                settings.budget = replace(
                    settings.budget,
                    max_jobs=240,
                    max_variants=24,
                    max_pages_per_query=6,
                    max_seconds=900,
                    max_results=6000,
                )
        changes = {
            name: getattr(args, name)
            for name in ("language", "region", "freshness", "after", "before")
            if getattr(args, name) is not None
        }
        settings.search = replace(settings.search, **changes)
        budget_changes = {
            name: getattr(args, name)
            for name in asdict(settings.budget)
            if getattr(args, name) is not None
        }
        settings.budget = replace(settings.budget, **budget_changes)
        if args.search or args.resume or args.refresh:
            return asyncio.run(
                headless(
                    args.search or "",
                    args.data_dir,
                    args.export_json,
                    resume_id=args.resume,
                    refresh_id=args.refresh,
                    sources=args.sources,
                    tor_proxy=args.tor_proxy,
                    settings=settings,
                    markdown=args.export_markdown,
                    csv=args.export_csv,
                )
            )
        if args.test_provider:
            return asyncio.run(test_provider(settings, args.test_provider, args.data_dir))
        if args.benchmark:
            from tractor.benchmark.runner import run_benchmark

            report = run_benchmark()
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0 if report["passed"] else 1
        if (
            args.export_json
            or args.export_markdown
            or args.export_csv
            or args.sources
            or args.tor_proxy
            or args.profile
            or changes
            or budget_changes
        ):
            parser.error("Search and export overrides require --search, --resume or --refresh")
        if args.providers or args.coverage or args.history is not None:
            with Database(args.data_dir / "investigations.sqlite3") as database:
                if args.providers:
                    print(
                        json.dumps(
                            {
                                "providers": configuration(settings),
                                "health": provider_health(database.connection),
                            },
                            indent=2,
                        )
                    )
                elif args.coverage:
                    inv = database.load(args.coverage)
                    print(
                        json.dumps(
                            redact(
                                {
                                    "coverage": inv.coverage,
                                    "configuration": inv.provider_configuration,
                                    "health": inv.provider_health,
                                    "search_options": inv.search_options,
                                    "limits": inv.limits,
                                    "budget": inv.budget,
                                }
                            ),
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                else:
                    for item in database.history(search=args.history):
                        print(
                            f"{item['id']}  {item['query']}  "
                            f"[{item['status']}; {item['results']} results]"
                        )
            return 0
    except KeyError:
        parser.exit(1, "No saved investigation has that ID. Use --history to list IDs.\n")
    except (ValueError, OSError, sqlite3.Error, RuntimeError) as exc:
        parser.exit(1, redact(f"Could not start: {exc}\n"))
    except KeyboardInterrupt:
        parser.exit(130, "Stopped. Collected evidence and remaining work are saved in History.\n")
    from PySide6.QtWidgets import QApplication

    from tractor.ui.main_window import MainWindow

    app = QApplication([])
    app.setApplicationName("TRACTOR")
    app.setOrganizationName("TRACTOR")
    window = MainWindow(args.data_dir)
    window.show()
    return app.exec()
