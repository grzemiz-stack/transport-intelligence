# Transport Intelligence

![CI](https://github.com/grzemiz-stack/transport-intelligence/actions/workflows/ci.yml/badge.svg)

Open-source intelligence (OSINT) system that monitors cargo theft, fuel theft,
vehicle theft, and other transport disruptions across Europe. It scrapes police
press releases, RSS feeds, Google News, forums, Telegram channels, and Reddit,
then classifies, filters, and stores structured events in PostgreSQL. A REST API
serves the data to dashboards and downstream integrations.

This is a working prototype, not a production system. The known limitations
section at the bottom is required reading.

## How it works

```
Sources                  Pipeline                    Storage & Output
---------                --------                    ----------------
Police (29 countries) -> Source Validator             PostgreSQL
RSS feeds             -> Parser                      (events, companies,
Google News           -> Anonymizer (PII removal)     sources, alerts,
Forums                -> GDPR Filter                  hotspots, reports)
Telegram              -> Normalizer (text, dates,        |
Discord               ->   currency, language)           v
Reddit                -> Classifier (keywords)       REST API (FastAPI)
                      -> Legal Filter                    |
                           |                             v
                           v                         Dashboard /
                      Database write                  PDF reports
```

**Deterministic (no LLM):** classification (keyword matching per language),
severity scoring, event type assignment, GDPR filtering, PII anonymization
(regex + optional spaCy NER), text normalization, currency conversion,
language detection, legal language sanitization, source trust tiering.

**LLM-dependent (Claude API, optional):** translation of non-English events,
executive report summaries, company due diligence synthesis, insolvency risk
analysis, pattern detection across events. The system runs without an API key;
these features degrade to statistical fallbacks.

## Scope

**29 countries with police scrapers:**
25 use a shared config-driven base class (`BasePoliceAgent` + `PoliceSourceConfig`),
4 have custom parsers (Germany, Austria, Turkey, Switzerland).

Countries: AT, BE, BG, CH, CZ, DE, DK, EE, ES, FI, FR, GB, GR, HR, HU,
IT, LT, LV, MD, NL, NO, PL, RO, RS, SE, SI, SK, TR, UA.

**Other source types:** RSS feeds (per-country YAML config), Google News
(search-based), forums, Telegram, Discord, Reddit.

**Event types:** cargo theft, fuel theft, vehicle theft, damage, delay, strike,
payment issue, bankruptcy, restructuring, license revocation, route closure.

**Classification languages:** keyword dictionaries for DE, PL, EN, FR, NL, IT,
ES, RO, CZ, HU, TR, UK (Ukrainian), with fallback to English.

## Stack

Python 3.13, FastAPI, SQLAlchemy 2.0 (async), asyncpg, PostgreSQL, Alembic,
bcrypt, PyJWT, httpx, BeautifulSoup4, lxml, feedparser, spaCy (lazy-loaded),
APScheduler, Jinja2, ReportLab, WeasyPrint, Telethon, discord.py, pydantic-settings.

Linting: ruff. Testing: pytest.

## Local setup

```bash
pip install -r requirements.txt

# Set required environment variables (or use a .env file)
export JWT_SECRET_KEY="your-secret-key-at-least-32-characters-long"
export POSTGRES_PASSWORD="your-password"
export DATABASE_URL="postgresql+asyncpg://admin:your-password@localhost:5432/transport_intel"

# Start PostgreSQL, run migrations, start the API
docker compose up -d
alembic upgrade head
uvicorn src.api.main:app --reload
```

To run scrapers:

```bash
# Single country police scraper
python -m src.agents.runner --country DE --agent police --once

# All police scrapers (29 countries, rate-limited)
python -m src.agents.runner --all-police --once

# All RSS feeds
python -m src.agents.rss_runner --all --once

# Dry run (no database writes)
python -m src.agents.runner --country PL --agent police --once --dry-run
```

## Tests and CI

```bash
ruff check src/ tests/
pytest tests/ -v
```

441 tests pass, 4 are skipped (require spaCy model download). Coverage spans
the pipeline components (anonymizer, classifier, normalizer, transport keywords),
authentication (JWT, bcrypt), police agent parsing, and geo-extraction.

GitHub Actions runs ruff and pytest on every push and pull request to `main`.

## Known limitations

**No event verification.** Each source gets a static trust score (0.0-1.0)
assigned at configuration time. Events are classified by substring keyword
matching against dictionaries per language. There is no human-in-the-loop
verification, no cross-source corroboration, and precision/recall have never
been measured against a labeled dataset.

**Classifier does not detect negation.** The text "no theft occurred" will be
classified as `theft_cargo` because the keyword "theft" is present. There is
no negation handling in the keyword matcher.

**Polish inflection breaks substring matching.** The classifier checks whether
a keyword appears as a substring in the text. Polish declined forms like
"autostradzie" (locative) do not contain the nominative "autostrada", so some
matches are missed. This applies to other inflected languages to varying degrees.

**No data retention policy.** There is no automatic deletion of old events, no
GDPR Article 17 right-to-erasure endpoint, and no configurable TTL. The
`audit_log` table exists but retention is unbounded.

**Scrapers do not check robots.txt.** Police press pages and news sites are
scraped without consulting robots.txt. The scraping is rate-limited (delays
between requests) but does not respect crawler directives.

**Reports lack period-over-period comparison.** Period-over-period comparison
was never implemented; the unused fetch was removed during cleanup.

**In-memory caches.** The company investigator, insolvency analyzer, and
pattern analyzer use in-memory dict caches keyed by MD5. These are lost on
process restart and have no size limit or eviction policy.

**Translation is LLM-only.** Event translation depends on Claude API
availability. There is no offline translation fallback; events stay in their
original language if the API is unavailable.

## Project history

Built as a rapid prototype, then audited and incrementally refactored: dead
code removal (10k+ LOC of unused stubs), security hardening (CORS, SSRF,
secrets management, dependency pinning, CVE fixes), architectural cleanup
(config-driven police agents, shared Claude client), test coverage, and CI.
The commit history documents the full process.
