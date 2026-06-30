# agency-lead-pipeline

An open-source Python pipeline for discovering organizations in public directories, resolving their public websites, and extracting publicly available contact emails into clean, resumable CSV files.

## What it does

- Discovers organization records through directory adapters.
- Resolves public websites and deduplicates registrable domains.
- Visits a limited number of same-domain website pages.
- Extracts and ranks publicly available emails from links, visible text, common obfuscations, and JSON-LD.
- Saves progress atomically and resumes from finalized domains.

The currently bundled directory adapter supports Clutch. Clutch is an input implementation, not the defining purpose of the extraction and storage pipeline.

## Architecture

The pipeline separates directory discovery from website contact extraction and CSV storage. A directory adapter produces normalized organization records; the shared extraction stage visits the organizations' public websites; the storage stage writes the common CSV schema. `clutch.py` contains the current Clutch adapter, including its listing selectors and outbound-link resolution.

## Installation

Python 3.11 or newer is required.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

Copy and edit the example configuration if desired:

```bash
cp config.example.yaml config.yaml
```

Commands automatically load `config.yaml` from the current directory when it exists. Use `--config PATH` to select another file; explicit CLI options override configuration values.

## Commands

The current `discover` and `run` commands use the bundled Clutch adapter:

```bash
agency-lead-pipeline discover https://clutch.co/web-developers
agency-lead-pipeline discover examples/clutch_urls.txt --max-pages 3 --max-agencies 100
agency-lead-pipeline discover examples/clutch_urls.txt --europe-only
agency-lead-pipeline extract
agency-lead-pipeline extract --europe-only
agency-lead-pipeline run examples/clutch_urls.txt --config config.example.yaml
agency-lead-pipeline dedupe data/leads.csv --output data/leads_clean.csv
agency-lead-pipeline validate data/leads.csv
```

`discover` defaults to `data/raw_agencies.csv`; `extract` defaults to reading that file and writing `data/leads.csv`. CLI values override YAML settings. The pipeline never follows an off-domain website link, except for the initial directory adapter's outbound redirect chain.

Historical CSV files placed directly in `archive/` are a read-only suppression list. The pipeline reads only their `Domain` or `Website` column, normalizes registrable domains, and excludes matches from new discovery and extraction output regardless of archived status. All other legacy columns are ignored, and archived rows are never copied into current output. Set `archive_directory` to select a different folder.

Set `europe_only: true` in YAML or pass `--europe-only` to keep only agencies whose directory location ends in a recognized European country. The filter runs during both discovery and extraction. Missing or unrecognized locations are excluded; `--all-regions` disables a YAML-configured filter.

`max_directory_pages` limits directory result pages per URL. `max_pages_per_website` separately limits contact pages visited on each organization website. `max_agencies` limits newly accepted discovery rows per run; existing raw rows do not consume that allowance.

### Privacy-conscious email selection

`allow_personal_emails` defaults to `false`. Email candidates are classified using heuristic categories:

- `ROLE`: functional inboxes such as `info@`, `hello@`, `sales@`, or `support@`. These are retained and preferred.
- `PERSONAL`: addresses showing signals commonly associated with a named individual, such as `jane.doe@`. These are excluded by default.
- `UNKNOWN`: ambiguous addresses such as `founder@`. These are retained but rank below preferred role inboxes.

These examples are illustrative, not exhaustive. Classification is fallible and does not determine identity, consent, lawful basis, or the legal status of an address. Set `allow_personal_emails: true` only if you choose to retain candidates classified as `PERSONAL`.

## CSV schema and data handling

Every CSV uses these columns, in order:

`Agency, Website, Domain, Country, Email, Email_Source_Page, Source_URL, Clutch_Profile, Status, Notes`

`Clutch_Profile` is populated by the current Clutch adapter and may be empty for records from other adapters.

Statuses are `New`, `Email_Found`, `No_Email`, `Website_Unreachable`, `Timeout`, `Duplicate`, and `Skipped`. A finalized domain is one whose lead has `Email_Found`, `No_Email`, `Website_Unreachable`, `Timeout`, or `Skipped`; extraction skips it on later runs. Raw discovery keeps duplicate rows marked `Duplicate`, while leads output contains one canonical row per domain.

Canonical selection prefers a valid website, then richer agency/location data, then earliest source order. The current export contains one best email per organization but retains eligible candidates during extraction for diagnostics and possible future multi-email output.

All exported fields are protected against spreadsheet formula injection when they begin with `=`, `+`, `-`, `@`, a tab, or a carriage return. The protective prefix is not removed when a CSV is read back because the file cannot reliably distinguish pipeline escaping from legitimate apostrophe-prefixed data.

Writes use a temporary file beside the destination and atomically replace the destination after flushing. Discovery saves after each directory page; extraction saves after each organization.

CSV exports may contain personal data depending on their source content and the applicable jurisdiction. Collect only the data needed for your purpose, secure exported files appropriately, and periodically delete data that is no longer needed.

## Compliance and Responsible Use

Use this project only to extract publicly available contact information. Public availability does not by itself establish permission, consent, or a lawful basis for collection or use.

Operators are responsible for complying with all applicable laws, regulations, privacy requirements, website terms of service, and outreach rules in their jurisdiction. Business contact information may still be subject to privacy or data-protection requirements depending on the content and jurisdiction. Operators must evaluate whether they have an appropriate lawful basis for collecting, storing, or using extracted data.

The project does not send emails, automate outreach, generate marketing content, determine lawful basis, verify consent requirements, or provide legal advice. It also has no CAPTCHA bypass, proxy rotation, login bypass, legal-analysis engine, privacy scanner, or jurisdiction-specific compliance logic.

Use respectful delays and concurrency, honor relevant access restrictions and policies, minimize retained data, and delete exports when they are no longer required.

## FAQ

### What does the project do?

It discovers public directory listings, resolves organization websites, extracts publicly available contact emails, and writes resumable CSV exports.

### What does the project not do?

It does not contact anyone, create marketing material, assess legal compliance, establish consent or lawful basis, or decide whether a particular use of the data is permitted.

### Why is compliance the operator's responsibility?

Requirements depend on the operator's purpose, location, sources, retained data, recipients, and jurisdiction. The pipeline does not have enough context to make those determinations, and its safeguards are not legal advice.

## Troubleshooting

- **Chromium missing:** run `playwright install chromium` in the active environment.
- **The Clutch adapter returns no rows:** page markup may have changed; inspect the listing selectors in `clutch.py` and open an issue with sanitized HTML details.
- **Directory access challenge:** set `headless: false`, rerun from an interactive terminal, and complete any check shown in the browser. The pipeline waits for listings but does not bypass CAPTCHAs or access controls.
- **Challenge clears too slowly:** increase `challenge_wait_seconds` so visible-browser runs have more time for manual checks before discovery stops.
- **Timeouts:** increase `timeout_seconds`, lower concurrency, or reduce per-run limits.
- **No email:** the site may publish no eligible address, require unsupported interaction, or place it beyond the page limit.
- **Resume behavior surprises:** remove or edit finalized rows in `data/leads.csv` to intentionally retry them.

## Roadmap

- Additional public-directory adapters with isolated source-specific parsing.
- Shared adapter interfaces and adapter-focused fixtures.
- Optional persisted email-candidate diagnostics and multi-email CSV output.
- Robots-policy checking and richer retry/backoff controls.
