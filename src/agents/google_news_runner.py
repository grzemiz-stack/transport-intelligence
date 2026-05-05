"""Google News Runner — uruchamia GoogleNewsAgent dla feedow z google_news_feeds.yaml.

Uzycie:
    python -m src.agents.google_news_runner --country DE --once
    python -m src.agents.google_news_runner --country PL --once
    python -m src.agents.google_news_runner --all --once
    python -m src.agents.google_news_runner --all --once --dry-run
"""

import argparse
import asyncio
import logging
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("google_news_runner")

FEEDS_PATH = Path(__file__).parent / "google_news_feeds.yaml"

# Rate limits
RATE_LIMIT_BETWEEN_REGIONS = 3.0  # sekundy miedzy regionami
RATE_LIMIT_BETWEEN_COUNTRIES = 10.0  # sekundy miedzy krajami

# Country name -> ISO code mapping
COUNTRY_CODE_MAP = {
    "germany": "DE", "poland": "PL", "france": "FR", "austria": "AT",
    "italy": "IT", "spain": "ES", "netherlands": "NL", "belgium": "BE",
    "sweden": "SE", "romania": "RO", "czech_republic": "CZ", "hungary": "HU",
    "united_kingdom": "GB", "denmark": "DK", "bulgaria": "BG", "croatia": "HR",
    "finland": "FI", "norway": "NO", "switzerland": "CH", "slovakia": "SK",
    "slovenia": "SI", "lithuania": "LT", "latvia": "LV", "estonia": "EE",
    "greece": "GR", "serbia": "RS", "turkey": "TR", "ukraine": "UA",
    "moldova": "MD",
}
CODE_TO_COUNTRY = {v: k for k, v in COUNTRY_CODE_MAP.items()}


def load_feeds() -> dict:
    """Load Google News feeds configuration from YAML."""
    if not FEEDS_PATH.exists():
        logger.error("Feeds file not found: %s", FEEDS_PATH)
        sys.exit(1)
    with open(FEEDS_PATH) as f:
        return yaml.safe_load(f)


def get_regions_for_country(all_feeds: dict, country_code: str) -> list[dict]:
    """Get list of region configs for a country code."""
    country_code = country_code.upper()
    country_name = CODE_TO_COUNTRY.get(country_code)
    if not country_name or country_name not in all_feeds:
        return []

    country_cfg = all_feeds[country_name]
    language = country_cfg.get("language", "en")
    regions = country_cfg.get("regions", [])

    result = []
    for region in regions:
        result.append({
            "name": region["name"],
            "query": region["query"],
            "lang": region.get("lang", language),
            "country": region.get("country", country_code),
            "country_code": country_code,
            "language": region.get("lang", language),
        })
    return result


# -- Translator -------------------------------------------------------------

def _create_translator():
    """Create EventTranslator if translation is enabled."""
    try:
        from src.config import settings
        if settings.translation_enabled and settings.anthropic_api_key:
            from src.pipeline.translator import EventTranslator
            return EventTranslator()
    except Exception:
        pass
    return None


# -- Pipeline (reuse pattern from rss_runner.py) ----------------------------

def _create_pipeline():
    from src.pipeline.anonymizer import Anonymizer
    from src.pipeline.classifier import EventClassifier
    from src.pipeline.gdpr_filter import GDPRFilter
    from src.pipeline.legal_filter import LegalFilter
    from src.pipeline.normalizer import EventNormalizer
    from src.pipeline.parser import EventParser
    from src.pipeline.source_validator import SourceValidator

    return {
        "source_validator": SourceValidator(),
        "parser": EventParser(),
        "anonymizer": Anonymizer(),
        "gdpr_filter": GDPRFilter(),
        "normalizer": EventNormalizer(),
        "classifier": EventClassifier(),
        "legal_filter": LegalFilter(),
    }


def _run_pipeline(event: dict, pipeline: dict) -> dict | None:
    sv = pipeline["source_validator"]
    parser = pipeline["parser"]
    anonymizer = pipeline["anonymizer"]
    gdpr = pipeline["gdpr_filter"]
    normalizer = pipeline["normalizer"]
    classifier = pipeline["classifier"]
    legal = pipeline["legal_filter"]

    source_url = event.get("source_url", "")

    # Skip source validation for Google News redirect URLs — we read the RSS feed,
    # not the article pages. The redirect URLs trigger robots.txt blocks on news.google.com.
    if source_url and "news.google.com" not in source_url:
        if not sv.is_legal_to_scrape(source_url):
            return None

    parsed = parser.parse_raw_event(event)
    for key in ("trust_score", "is_official", "source_type", "language",
                "collected_at", "timestamp", "source_name", "country_code"):
        if key in event and key not in parsed:
            parsed[key] = event[key]

    for field in ("title", "description", "raw_text"):
        text = parsed.get(field)
        if text:
            parsed[field] = anonymizer.anonymize_personal_data(text)
    parsed["is_anonymized"] = True

    gdpr_result = gdpr.check_compliance(parsed)
    gdpr_status = gdpr_result.get("status", "non_compliant")
    if gdpr_status == "non_compliant":
        return None
    if gdpr_status == "needs_review":
        parsed["_needs_legal_review"] = True

    parsed = normalizer.normalize(parsed)
    parsed = classifier.classify(parsed)

    filtered = legal.filter_event(parsed)
    if filtered is None:
        return None

    return filtered


# -- DB save ----------------------------------------------------------------

async def _save_events_to_db(events: list[dict], region_cfg: dict) -> int:
    """Save processed events to PostgreSQL."""
    from sqlalchemy import select
    from src.db.models import Event, Source
    from src.db.postgres import async_session

    saved = 0
    source_name = f"Google News/{region_cfg['name']}"

    async with async_session() as session:
        result = await session.execute(
            select(Source).where(Source.name == source_name)
        )
        source = result.scalar_one_or_none()

        if source is None:
            source = Source(
                id=uuid.uuid4(),
                name=source_name,
                source_type="news",
                url=f"https://news.google.com/rss/search?q={region_cfg['query']}",
                country_code=region_cfg["country_code"],
                trust_score=0.4,
                is_official=False,
                is_active=True,
                scrape_interval_minutes=60,
            )
            session.add(source)
            await session.flush()
            logger.info("Created source: %s (id=%s)", source_name, source.id)

        for ev in events:
            src_url = ev.get("source_url", "")
            if src_url:
                dup = await session.execute(
                    select(Event.id).where(Event.source_url == src_url).limit(1)
                )
                if dup.scalar_one_or_none():
                    continue

            date_occurred = None
            date_val = ev.get("date_parsed") or ev.get("date")
            if isinstance(date_val, datetime):
                date_occurred = date_val
            elif isinstance(date_val, str) and date_val:
                try:
                    date_occurred = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            if date_occurred and date_occurred.tzinfo is not None:
                date_occurred = date_occurred.replace(tzinfo=None)

            location = ev.get("location", {})

            db_event = Event(
                id=uuid.uuid4(),
                event_type=ev.get("event_type", "other"),
                severity=ev.get("severity", "medium"),
                title=(ev.get("title") or "Bez tytulu")[:500],
                description=ev.get("description"),
                date_occurred=date_occurred,
                date_collected=datetime.utcnow(),
                country_code=ev.get("country_code", region_cfg["country_code"]),
                region=ev.get("region") or (location.get("region") if isinstance(location, dict) else None),
                city=location.get("city") if isinstance(location, dict) else None,
                source_id=source.id,
                trust_score=ev.get("trust_score", 0.4),
                is_verified=False,
                is_anonymized=ev.get("is_anonymized", True),
                raw_text=(ev.get("raw_text") or "")[:5000],
                processed_text=ev.get("description"),
                source_url=src_url or None,
                language=ev.get("language", region_cfg["language"]),
                tags=ev.get("tags"),
                financial_impact_eur=ev.get("financial_impact_eur"),
                cargo_type=ev.get("cargo_type"),
                modus_operandi=ev.get("modus_operandi"),
                location_detail=ev.get("location_detail"),
                vehicle_country=ev.get("vehicle_country"),
            )
            session.add(db_event)
            saved += 1

        source.last_scraped = datetime.utcnow()
        source.total_events_collected = (source.total_events_collected or 0) + saved

        await session.commit()

    return saved


# -- Run single region ------------------------------------------------------

async def run_region(region_cfg: dict, pipeline: dict, dry_run: bool = False, translator=None) -> dict:
    """Run a single Google News region through the full pipeline."""
    from src.agents.google_news_agent import GoogleNewsAgent

    agent = GoogleNewsAgent(
        country_code=region_cfg["country_code"],
        language=region_cfg["language"],
        region_name=region_cfg["name"],
        query=region_cfg["query"],
    )

    result = {
        "name": region_cfg["name"],
        "country": region_cfg["country_code"],
        "fetched": 0,
        "transport": 0,
        "saved": 0,
        "error": None,
    }

    try:
        events = await agent.run_once()
        result["fetched"] = len(events)
    except Exception as e:
        result["error"] = str(e)
        logger.error("[%s] Fetch failed: %s", region_cfg["name"], e)
        await agent.stop()
        return result

    if not events:
        await agent.stop()
        return result

    # Events are already keyword-filtered by GoogleNewsAgent
    result["transport"] = len(events)

    # Run through pipeline
    processed = []
    for ev in events:
        out = _run_pipeline(ev, pipeline)
        if out is not None:
            if translator and out.get("language") != "pl":
                try:
                    out = await translator.translate_event(out)
                except Exception:
                    pass
            processed.append(out)

    # Article enrichment — fetch full text and extract structured details
    if processed:
        from src.pipeline.article_extractor import fetch_article_text, ArticleExtractor
        extractor = ArticleExtractor()

        for ev in processed:
            url = ev.get("source_url", "")
            if not url:
                continue
            try:
                full_text = await fetch_article_text(url, ev.get("language", "en"))
                if full_text:
                    details = extractor.extract_details(full_text, ev.get("language", "en"))
                    if details.get("cargo_type"):
                        ev["cargo_type"] = details["cargo_type"]
                    if details.get("modus_operandi"):
                        ev["modus_operandi"] = details["modus_operandi"]
                    if details.get("location_detail"):
                        ev["location_detail"] = details["location_detail"]
                    if details.get("vehicle_country"):
                        ev["vehicle_country"] = details["vehicle_country"]
                    if details.get("financial_value_eur") and not ev.get("financial_impact_eur"):
                        ev["financial_impact_eur"] = details["financial_value_eur"]
                    # Enrich description with full text (max 2000 chars)
                    if len(full_text) > len(ev.get("description") or ""):
                        ev["description"] = full_text[:2000]
                        ev["raw_text"] = full_text[:5000]
            except Exception as e:
                logger.debug("Article enrichment failed for %s: %s", url[:80], e)
            await asyncio.sleep(3.0)  # rate limit between article fetches

    if dry_run:
        result["saved"] = 0
        for ev in processed:
            logger.info("  [DRY] [%s] %s", ev.get("event_type", "?"), ev.get("title", "?")[:80])
    else:
        try:
            result["saved"] = await _save_events_to_db(processed, region_cfg)
        except Exception as e:
            result["error"] = str(e)
            logger.error("[%s] DB save failed: %s", region_cfg["name"], e)

    await agent.stop()
    return result


# -- Run country ------------------------------------------------------------

async def run_country(country_code: str, dry_run: bool = False):
    """Run all Google News regions for a single country."""
    all_feeds = load_feeds()
    regions = get_regions_for_country(all_feeds, country_code)

    if not regions:
        logger.error("No Google News feeds for country: %s", country_code)
        return

    logger.info("=" * 70)
    logger.info("Google News Runner: %s — %d regions", country_code, len(regions))
    logger.info("=" * 70)

    pipeline = _create_pipeline()
    total_start = time.time()
    results = []

    for i, region_cfg in enumerate(regions):
        logger.info("--- [%d/%d] %s ---", i + 1, len(regions), region_cfg["name"])
        r = await run_region(region_cfg, pipeline, dry_run)
        results.append(r)
        logger.info(
            "  Articles: %d fetched, %d transport-related, %d saved%s",
            r["fetched"], r["transport"], r["saved"],
            f" ERROR: {r['error']}" if r["error"] else "",
        )

        # Rate limit between regions
        if i < len(regions) - 1:
            logger.debug("Rate limit: %.0fs before next region...", RATE_LIMIT_BETWEEN_REGIONS)
            await asyncio.sleep(RATE_LIMIT_BETWEEN_REGIONS)

    # Summary
    elapsed = time.time() - total_start
    total_fetched = sum(r["fetched"] for r in results)
    total_transport = sum(r["transport"] for r in results)
    total_saved = sum(r["saved"] for r in results)
    errors = sum(1 for r in results if r["error"])

    logger.info("=" * 70)
    logger.info("PODSUMOWANIE %s:", country_code)
    logger.info("  Czas:              %.1fs", elapsed)
    logger.info("  Regions:           %d (%d errors)", len(results), errors)
    logger.info("  Articles fetched:  %d", total_fetched)
    logger.info("  Transport-related: %d", total_transport)
    logger.info("  Saved to DB:       %d", total_saved)
    logger.info("=" * 70)

    # Update agent_statuses for this country
    if not dry_run:
        from src.db.queries import update_agent_status
        await update_agent_status(
            country_code=country_code,
            agent_type="google_news",
            events_count=total_saved,
            errors_count=errors,
        )


# -- Run all countries ------------------------------------------------------

async def run_all(dry_run: bool = False):
    """Run Google News feeds for all countries."""
    all_feeds = load_feeds()
    countries = []
    for country_name in all_feeds:
        code = COUNTRY_CODE_MAP.get(country_name)
        if code:
            countries.append(code)

    logger.info("Google News: running %d countries: %s", len(countries), ", ".join(sorted(countries)))

    for i, code in enumerate(sorted(countries)):
        await run_country(code, dry_run)

        # Rate limit between countries
        if i < len(countries) - 1:
            logger.info("Rate limit: %.0fs before next country...", RATE_LIMIT_BETWEEN_COUNTRIES)
            await asyncio.sleep(RATE_LIMIT_BETWEEN_COUNTRIES)


# -- CLI --------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Transport Intelligence Google News Runner")
    parser.add_argument("--country", help="Country ISO code (e.g. DE, PL)")
    parser.add_argument("--all", action="store_true", help="Run all countries")
    parser.add_argument("--once", action="store_true", help="Single execution")
    parser.add_argument("--dry-run", action="store_true", help="Don't save to DB")
    args = parser.parse_args()

    if not args.country and not args.all:
        parser.print_help()
        sys.exit(1)

    if args.all:
        asyncio.run(run_all(dry_run=args.dry_run))
    else:
        asyncio.run(run_country(args.country, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
