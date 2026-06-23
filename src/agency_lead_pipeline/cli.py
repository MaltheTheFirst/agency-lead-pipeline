from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import httpx
import typer
from playwright.async_api import async_playwright
from rich.progress import Progress

from .clutch import discover_agencies
from .config import Settings, load_settings
from .contacts import extract_record
from .dedupe import dedupe_records
from .logging_utils import console
from .models import FINALIZED_STATUSES, Status
from .storage import read_records, validate_csv, write_records_atomic


app = typer.Typer(help="Discover Clutch agencies and extract public contact emails.", no_args_is_help=True)


def _expand_urls(values: list[str]) -> list[str]:
    urls: list[str] = []
    for value in values:
        path = Path(value)
        if path.is_file():
            urls.extend(line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#"))
        else:
            urls.append(value)
    return list(dict.fromkeys(urls))


def _settings(config: Path | None, **values) -> Settings:
    try:
        return load_settings(config, **values)
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command()
def discover(
    urls: Annotated[list[str], typer.Argument(help="Clutch URL(s), or newline-delimited URL file(s).")],
    config: Annotated[Path | None, typer.Option()] = None,
    output: Annotated[Path | None, typer.Option()] = None,
    max_pages: Annotated[int | None, typer.Option()] = None,
    max_agencies: Annotated[int | None, typer.Option()] = None,
    delay: Annotated[float | None, typer.Option()] = None,
    timeout: Annotated[float | None, typer.Option()] = None,
    user_agent: Annotated[str | None, typer.Option()] = None,
) -> None:
    settings = _settings(config, raw_output=output, max_directory_pages=max_pages, max_agencies=max_agencies,
                         delay_seconds=delay, timeout_seconds=timeout, user_agent=user_agent)
    expanded = _expand_urls(urls) or settings.clutch_urls
    if not expanded:
        raise typer.BadParameter("Provide at least one Clutch directory URL")
    records = asyncio.run(discover_agencies(expanded, settings, settings.raw_output))
    console.print(f"[green]Discovered {len(records)} rows → {settings.raw_output}[/green]")


async def _extract_all(settings: Settings, input_path: Path, output_path: Path) -> tuple[int, int]:
    source = dedupe_records([record for record in read_records(input_path) if record.status != Status.DUPLICATE])
    existing = read_records(output_path)
    finalized = {record.domain for record in existing if record.domain and record.status in FINALIZED_STATUSES}
    results = list(existing)
    pending = [record for record in source if record.domain not in finalized]
    headers = {"User-Agent": settings.user_agent}
    timeout = httpx.Timeout(settings.timeout_seconds)
    semaphore = asyncio.Semaphore(settings.concurrency)
    async with async_playwright() as playwright, httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=False) as client:
        browser = await playwright.chromium.launch(headless=settings.headless)
        async def process(record):
            async with semaphore:
                return await extract_record(record, client, browser, settings)
        try:
            with Progress(console=console) as progress:
                task = progress.add_task("Extracting", total=len(pending))
                jobs = [asyncio.create_task(process(record)) for record in pending]
                for job in asyncio.as_completed(jobs):
                    extraction = await job
                    completed = extraction.record
                    results = [row for row in results if not completed.domain or row.domain != completed.domain]
                    results.append(completed)
                    write_records_atomic(output_path, dedupe_records(results))
                    progress.advance(task)
        finally:
            await browser.close()
    return len(pending), len(finalized)


@app.command("extract")
def extract_command(
    input: Annotated[Path | None, typer.Option()] = None,
    output: Annotated[Path | None, typer.Option()] = None,
    config: Annotated[Path | None, typer.Option()] = None,
    max_site_pages: Annotated[int | None, typer.Option()] = None,
    concurrency: Annotated[int | None, typer.Option()] = None,
    delay: Annotated[float | None, typer.Option()] = None,
    timeout: Annotated[float | None, typer.Option()] = None,
) -> None:
    settings = _settings(config, leads_output=output, max_pages_per_website=max_site_pages,
                         concurrency=concurrency, delay_seconds=delay, timeout_seconds=timeout)
    input_path = input or settings.raw_output
    processed, skipped = asyncio.run(_extract_all(settings, input_path, settings.leads_output))
    console.print(f"[green]Processed {processed}; skipped {skipped} finalized domain(s) → {settings.leads_output}[/green]")


@app.command()
def run(
    urls: Annotated[list[str], typer.Argument()],
    config: Annotated[Path | None, typer.Option()] = None,
) -> None:
    settings = _settings(config)
    expanded = _expand_urls(urls) or settings.clutch_urls
    asyncio.run(discover_agencies(expanded, settings, settings.raw_output))
    processed, skipped = asyncio.run(_extract_all(settings, settings.raw_output, settings.leads_output))
    console.print(f"[green]Run complete: {processed} processed, {skipped} resumed → {settings.leads_output}[/green]")


@app.command()
def dedupe(
    input: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    output: Annotated[Path | None, typer.Option()] = None,
) -> None:
    target = output or input.with_name(f"{input.stem}_deduped{input.suffix}")
    records = dedupe_records(read_records(input))
    write_records_atomic(target, records)
    console.print(f"[green]Wrote {len(records)} canonical rows → {target}[/green]")


@app.command("validate")
def validate_command(input: Annotated[Path, typer.Argument(exists=True, dir_okay=False)]) -> None:
    errors = validate_csv(input)
    if errors:
        for error in errors:
            console.print(f"[red]{error}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Valid CSV: {input}[/green]")


if __name__ == "__main__":
    app()
