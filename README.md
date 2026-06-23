# agency-lead-pipeline

An open-source Python pipeline for discovering web development and digital agencies on Clutch, resolving their public websites, and extracting public contact emails into clean, resumable CSV files.

## What it does

- Loads one or more Clutch directory pages with Playwright and Chromium.
- Extracts agency, location, website, source, and Clutch profile data.
- Resolves Clutch outbound redirects and deduplicates registrable domains.
- Visits up to five same-domain website pages by default.
- Extracts and ranks public emails from links, text, obfuscations, and JSON-LD.
- Saves progress atomically and resumes from finalized domains in `leads.csv`.

It does **not** scan for ConsentLens concerns, classify GDPR violations, generate email, send outreach, evade access controls, or contain private qualification logic, customer data, templates, or credentials.

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

## Commands

```bash
agency-lead-pipeline discover https://clutch.co/web-developers
agency-lead-pipeline discover examples/clutch_urls.txt --max-pages 3 --max-agencies 100
agency-lead-pipeline extract
agency-lead-pipeline run examples/clutch_urls.txt --config config.example.yaml
agency-lead-pipeline dedupe data/leads.csv --output data/leads_clean.csv
agency-lead-pipeline validate data/leads.csv
```

`discover` defaults to `data/raw_agencies.csv`; `extract` defaults to reading that file and writing `data/leads.csv`. CLI values override YAML settings. The pipeline never follows an off-domain website link, except for the initial Clutch outbound redirect chain.

## CSV schema

Every CSV uses these columns, in order:

`Agency, Website, Domain, Country, Email, Email_Source_Page, Source_URL, Clutch_Profile, Status, Notes`

Statuses are `New`, `Email_Found`, `No_Email`, `Website_Unreachable`, `Timeout`, `Duplicate`, and `Skipped`. A finalized domain is one whose lead has `Email_Found`, `No_Email`, `Website_Unreachable`, `Timeout`, or `Skipped`; extraction skips it on later runs. Raw discovery keeps duplicate rows marked `Duplicate`, while leads output contains one canonical row per domain.

Canonical selection prefers a valid website, then richer agency/location data, then earliest source order. The MVP exports one best email per agency, but retains all candidates during extraction for diagnostics and future multi-email output.

Writes use a temporary file beside the destination and atomically replace the destination after flushing. Discovery saves after each directory page; extraction saves after each agency.

## Ethical use

Use this project only for lawful collection of public business contact details. Review applicable terms, robots policies, privacy rules, and local law. Keep delays and concurrency respectful. The project intentionally has no CAPTCHA bypass, proxy rotation, login bypass, outreach, or messaging features.

## Troubleshooting

- **Chromium missing:** run `playwright install chromium` in the active environment.
- **Clutch returns no rows:** page markup may have changed; inspect the listing selectors in `clutch.py` and open an issue with sanitized HTML details.
- **Timeouts:** increase `timeout_seconds`, lower concurrency, or reduce per-run limits.
- **No email:** the site may publish no address, require unsupported interaction, or place it beyond the page limit.
- **Resume behavior surprises:** remove or edit finalized rows in `data/leads.csv` to intentionally retry them.

## Roadmap

- More resilient, fixture-backed Clutch selector variants.
- Optional persisted email-candidate diagnostics and multi-email CSV output.
- Robots-policy checking and richer retry/backoff controls.
- Additional public agency directories through separate adapters.

