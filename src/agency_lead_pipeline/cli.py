from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Annotated

import httpx
import typer
from playwright.async_api import async_playwright
from rich.progress import Progress

from .clutch import DirectoryAccessError, discover_agencies
from .config import Settings, load_settings
from .contacts import extract_record
from .dedupe import dedupe_records
from .geography import is_european_location
from .generic_directory import discover_generic_websites
from .http_utils import homepage_url
from .logging_utils import console
from .models import FINALIZED_STATUSES, Status
from .storage import read_archived_domains, read_records, validate_csv, write_records_atomic


app = typer.Typer(
    help="Discover directory listings and extract publicly available contact emails.",
    no_args_is_help=True,
)


def _print_directory_error(exc: DirectoryAccessError) -> None:
    console.print(f"[red]Discovery stopped:[/red] {exc}")
    console.print(
        "[yellow]Previously saved CSV checkpoints were left unchanged. "
        "No extraction was started.[/yellow]"
    )


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
        # A project-local config.yaml is the conventional default. An explicit
        # --config path still takes precedence, and CLI values override both.
        config_path = config or (Path("config.yaml") if Path("config.yaml").is_file() else None)
        return load_settings(config_path, **values)
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


def _log_line(path: Path | None, message: str) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {message}\n")


def _valid_email_leads(records) -> list:
    return [
        record for record in dedupe_records(records)
        if record.status == Status.EMAIL_FOUND and record.email
    ]


def _write_valid_email_leads(
    path: Path,
    records,
    limit: int | None = None,
    homepage_websites: bool = True,
) -> int:
    leads = _valid_email_leads(records)
    if limit is not None:
        leads = leads[:limit]
    if homepage_websites:
        leads = [
            record.model_copy(update={"website": homepage_url(record.website)})
            for record in leads
        ]
    write_records_atomic(path, leads)
    return len(leads)


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
    europe_only: Annotated[bool | None, typer.Option("--europe-only/--all-regions")] = None,
) -> None:
    settings = _settings(config, raw_output=output, max_directory_pages=max_pages, max_agencies=max_agencies,
                         delay_seconds=delay, timeout_seconds=timeout, user_agent=user_agent,
                         europe_only=europe_only)
    expanded = _expand_urls(urls) or settings.clutch_urls
    if not expanded:
        raise typer.BadParameter("Provide at least one Clutch directory URL")
    try:
        records = asyncio.run(discover_agencies(expanded, settings, settings.raw_output))
    except DirectoryAccessError as exc:
        _print_directory_error(exc)
        raise typer.Exit(2) from None
    console.print(f"[green]Discovered {len(records)} rows → {settings.raw_output}[/green]")


@app.command("discover-websites")
def discover_websites(
    urls: Annotated[list[str], typer.Argument(help="Directory page URL(s), or newline-delimited URL file(s).")],
    config: Annotated[Path | None, typer.Option()] = None,
    output: Annotated[Path | None, typer.Option()] = None,
    log_file: Annotated[Path | None, typer.Option()] = None,
    max_pages: Annotated[int | None, typer.Option()] = None,
    max_sites: Annotated[int | None, typer.Option()] = None,
    delay: Annotated[float | None, typer.Option()] = None,
    timeout: Annotated[float | None, typer.Option()] = None,
    user_agent: Annotated[str | None, typer.Option()] = None,
    europe_only: Annotated[bool | None, typer.Option("--europe-only/--all-regions")] = None,
) -> None:
    settings = _settings(
        config,
        raw_output=output,
        log_file=log_file,
        max_directory_pages=max_pages,
        max_agencies=max_sites,
        delay_seconds=delay,
        timeout_seconds=timeout,
        user_agent=user_agent,
        europe_only=europe_only,
    )
    expanded = _expand_urls(urls)
    if not expanded:
        raise typer.BadParameter("Provide at least one directory page URL")
    _log_line(settings.log_file, f"DISCOVER_WEBSITES start urls={len(expanded)} output={settings.raw_output}")
    records = asyncio.run(
        discover_generic_websites(expanded, settings, settings.raw_output, max_sites, settings.max_directory_pages)
    )
    _log_line(settings.log_file, f"DISCOVER_WEBSITES done rows={len(records)} output={settings.raw_output}")
    console.print(f"[green]Discovered {len(records)} website row(s) -> {settings.raw_output}[/green]")


async def _extract_all(
    settings: Settings,
    input_path: Path,
    output_path: Path,
    target_email_leads: int | None = None,
) -> tuple[int, int, int]:
    archived_domains = read_archived_domains(settings.archive_directory)
    source = dedupe_records([record for record in read_records(input_path) if record.status != Status.DUPLICATE])
    existing = read_records(output_path)
    archived_skipped = sum(bool(record.domain and record.domain in archived_domains) for record in source)
    source = [record for record in source if record.domain not in archived_domains]
    existing = [record for record in existing if record.domain not in archived_domains]
    if settings.europe_only:
        source = [record for record in source if is_european_location(record.country)]
        existing = [record for record in existing if is_european_location(record.country)]
    write_records_atomic(output_path, existing)
    finalized = archived_domains | {
        record.domain for record in existing if record.domain and record.status in FINALIZED_STATUSES
    }
    results = list(existing)
    pending = [record for record in source if record.domain not in finalized]
    skipped = archived_skipped + sum(bool(record.domain and record.domain in finalized) for record in source)
    processed = 0
    headers = {"User-Agent": settings.user_agent}
    timeout = httpx.Timeout(settings.timeout_seconds)
    semaphore = asyncio.Semaphore(settings.concurrency)
    async with async_playwright() as playwright, httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=False) as client:
        browser = await playwright.chromium.launch(headless=settings.headless)
        async def process(record):
            async with semaphore:
                _log_line(settings.log_file, f"EXTRACT start domain={record.domain} website={record.website}")
                extraction = await extract_record(record, client, browser, settings)
                completed = extraction.record
                _log_line(
                    settings.log_file,
                    f"EXTRACT done status={completed.status.value} domain={completed.domain} email={completed.email or '-'} notes={completed.notes!r}",
                )
                return extraction
        try:
            with Progress(console=console) as progress:
                task = progress.add_task("Extracting", total=len(pending))
                for index in range(0, len(pending), settings.concurrency):
                    if target_email_leads and len(_valid_email_leads(results)) >= target_email_leads:
                        break
                    batch = pending[index:index + settings.concurrency]
                    jobs = [asyncio.create_task(process(record)) for record in batch]
                    for job in asyncio.as_completed(jobs):
                        extraction = await job
                        completed = extraction.record
                        results = [row for row in results if not completed.domain or row.domain != completed.domain]
                        results.append(completed)
                        processed += 1
                        write_records_atomic(output_path, dedupe_records(results))
                        progress.advance(task)
        finally:
            await browser.close()
    return processed, skipped, len(_valid_email_leads(results))


@app.command("extract")
def extract_command(
    input: Annotated[Path | None, typer.Option()] = None,
    output: Annotated[Path | None, typer.Option()] = None,
    valid_output: Annotated[Path | None, typer.Option()] = None,
    target_leads: Annotated[int | None, typer.Option()] = None,
    homepage_websites: Annotated[bool | None, typer.Option("--homepage-websites/--full-websites")] = None,
    log_file: Annotated[Path | None, typer.Option()] = None,
    config: Annotated[Path | None, typer.Option()] = None,
    max_site_pages: Annotated[int | None, typer.Option()] = None,
    concurrency: Annotated[int | None, typer.Option()] = None,
    delay: Annotated[float | None, typer.Option()] = None,
    timeout: Annotated[float | None, typer.Option()] = None,
    europe_only: Annotated[bool | None, typer.Option("--europe-only/--all-regions")] = None,
) -> None:
    settings = _settings(config, leads_output=output, valid_leads_output=valid_output,
                         target_email_leads=target_leads, homepage_websites=homepage_websites,
                         log_file=log_file,
                         max_pages_per_website=max_site_pages,
                         concurrency=concurrency, delay_seconds=delay, timeout_seconds=timeout,
                         europe_only=europe_only)
    input_path = input or settings.raw_output
    _log_line(
        settings.log_file,
        f"EXTRACT_RUN start input={input_path} output={settings.leads_output} "
        f"target={settings.target_email_leads or '-'}",
    )
    processed, skipped, valid_count = asyncio.run(
        _extract_all(settings, input_path, settings.leads_output, settings.target_email_leads)
    )
    _log_line(
        settings.log_file,
        f"EXTRACT_RUN done processed={processed} skipped={skipped} valid={valid_count} output={settings.leads_output}",
    )
    console.print(
        f"[green]Processed {processed}; skipped {skipped} finalized domain(s); "
        f"{valid_count} valid email lead(s) -> {settings.leads_output}[/green]"
    )
    if valid_output or settings.target_email_leads:
        written = _write_valid_email_leads(
            settings.valid_leads_output,
            read_records(settings.leads_output),
            settings.target_email_leads,
            settings.homepage_websites,
        )
        _log_line(settings.log_file, f"VALID_EXPORT done rows={written} output={settings.valid_leads_output}")
        console.print(f"[green]Wrote {written} valid email lead(s) -> {settings.valid_leads_output}[/green]")


@app.command()
def run(
    urls: Annotated[list[str], typer.Argument()],
    config: Annotated[Path | None, typer.Option()] = None,
    europe_only: Annotated[bool | None, typer.Option("--europe-only/--all-regions")] = None,
) -> None:
    settings = _settings(config, europe_only=europe_only)
    expanded = _expand_urls(urls) or settings.clutch_urls
    try:
        asyncio.run(discover_agencies(expanded, settings, settings.raw_output))
    except DirectoryAccessError as exc:
        _print_directory_error(exc)
        raise typer.Exit(2) from None
    processed, skipped, _valid_count = asyncio.run(_extract_all(settings, settings.raw_output, settings.leads_output))
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
