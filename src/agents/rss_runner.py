"""RSS Runner — uruchamia RSSAgent dla feedow z rss_feeds.yaml.

Uzycie:
    python -m src.agents.rss_runner --country DE --once
    python -m src.agents.rss_runner --country PL --once
    python -m src.agents.rss_runner --all --once
    python -m src.agents.rss_runner --country DE --once --dry-run
    python -m src.agents.rss_runner --reddit --once
    python -m src.agents.rss_runner --country DE --source-type reddit --once
    python -m src.agents.rss_runner --all --source-type police --once
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
logger = logging.getLogger("rss_runner")

FEEDS_PATH = Path(__file__).parent / "rss_feeds.yaml"

# Reddit rate limit: min seconds between requests
REDDIT_RATE_LIMIT_SECONDS = 2.0

# Country name -> ISO code mapping
COUNTRY_CODE_MAP = {
    "germany": "DE", "poland": "PL", "france": "FR", "austria": "AT",
    "italy": "IT", "spain": "ES", "netherlands": "NL", "belgium": "BE",
    "sweden": "SE", "romania": "RO", "czech_republic": "CZ", "hungary": "HU",
    "united_kingdom": "GB", "denmark": "DK", "bulgaria": "BG", "croatia": "HR",
    "portugal": "PT", "ireland": "IE", "finland": "FI", "norway": "NO",
    "switzerland": "CH", "slovakia": "SK", "slovenia": "SI", "lithuania": "LT",
    "latvia": "LV", "estonia": "EE", "greece": "GR", "serbia": "RS",
    "luxembourg": "LU", "iceland": "IS", "turkey": "TR", "ukraine": "UA",
    "ireland": "IE",
}

# Reverse: code -> country name
CODE_TO_COUNTRY = {v: k for k, v in COUNTRY_CODE_MAP.items()}


def load_feeds() -> dict:
    """Load RSS feeds configuration from YAML."""
    if not FEEDS_PATH.exists():
        logger.error("Feeds file not found: %s", FEEDS_PATH)
        sys.exit(1)
    with open(FEEDS_PATH) as f:
        return yaml.safe_load(f)


def get_feeds_for_country(
    all_feeds: dict,
    country_code: str,
    source_type_filter: str | None = None,
) -> list[dict]:
    """Get flat list of feed configs for a country code.

    Args:
        source_type_filter: If set, only return feeds of this type (police/news/reddit/etc.)
    """
    country_code = country_code.upper()
    country_name = CODE_TO_COUNTRY.get(country_code)
    if not country_name or country_name not in all_feeds:
        return []

    country_cfg = all_feeds[country_name]
    language = country_cfg.get("language", "en")
    feeds = []

    for source_type, feed_list in country_cfg.items():
        if source_type == "language":
            continue
        if not isinstance(feed_list, list):
            continue
        if source_type_filter and source_type != source_type_filter:
            continue
        for feed in feed_list:
            if feed.get("url", "").startswith("placeholder"):
                continue
            feeds.append({
                "name": feed["name"],
                "url": feed["url"],
                "trust_score": feed.get("trust_score", 0.5),
                "is_official": feed.get("is_official", False),
                "source_type": source_type,
                "language": feed.get("language", language),
                "country_code": country_code,
            })

    return feeds


def get_global_reddit_feeds(all_feeds: dict) -> list[dict]:
    """Get global Reddit feeds that apply to all countries.

    Uses 'XX' as country_code (varchar(2) constraint in DB).
    """
    feeds = []
    for feed in all_feeds.get("global_reddit", []):
        if feed.get("url", "").startswith("placeholder"):
            continue
        feeds.append({
            "name": feed["name"],
            "url": feed["url"],
            "trust_score": feed.get("trust_score", 0.3),
            "is_official": feed.get("is_official", False),
            "source_type": "reddit",
            "language": feed.get("language", "en"),
            "country_code": "XX",
        })
    return feeds


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


# -- Pipeline (reuse from runner.py) -----------------------------------------

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

    if source_url and not sv.is_legal_to_scrape(source_url):
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


# -- DB save (generic, not hardcoded to one source) --------------------------

async def _save_events_to_db(events: list[dict], feed_cfg: dict) -> int:
    """Save processed events to PostgreSQL."""
    from sqlalchemy import select
    from src.db.models import Event, Source
    from src.db.postgres import async_session

    saved = 0

    async with async_session() as session:
        # Find or create source record
        result = await session.execute(
            select(Source).where(Source.name == feed_cfg["name"])
        )
        source = result.scalar_one_or_none()

        if source is None:
            source = Source(
                id=uuid.uuid4(),
                name=feed_cfg["name"],
                source_type=feed_cfg["source_type"],
                url=feed_cfg["url"],
                country_code=feed_cfg["country_code"],
                trust_score=feed_cfg["trust_score"],
                is_official=feed_cfg["is_official"],
                is_active=True,
                scrape_interval_minutes=60,
            )
            session.add(source)
            await session.flush()
            logger.info("Created source: %s (id=%s)", feed_cfg["name"], source.id)

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

            # Make datetime naive for PostgreSQL columns
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
                country_code=ev.get("country_code", feed_cfg["country_code"]),
                region=location.get("region") if isinstance(location, dict) else None,
                city=location.get("city") if isinstance(location, dict) else None,
                source_id=source.id,
                trust_score=ev.get("trust_score", feed_cfg["trust_score"]),
                is_verified=False,
                is_anonymized=ev.get("is_anonymized", True),
                raw_text=(ev.get("raw_text") or "")[:5000],
                processed_text=ev.get("description"),
                source_url=src_url or None,
                language=ev.get("language", feed_cfg["language"]),
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


# -- Main ------------------------------------------------------------------

# Track last Reddit request time for rate limiting
_last_reddit_request: float = 0.0


async def run_feed(feed_cfg: dict, pipeline: dict, dry_run: bool = False, translator=None) -> dict:
    """Run a single RSS feed through the full pipeline."""
    global _last_reddit_request
    from src.agents.rss_agent import RSSAgent

    # Reddit rate limiting: wait at least 2s between requests
    is_reddit = "reddit.com" in feed_cfg.get("url", "")
    if is_reddit:
        elapsed = time.time() - _last_reddit_request
        if elapsed < REDDIT_RATE_LIMIT_SECONDS:
            wait = REDDIT_RATE_LIMIT_SECONDS - elapsed
            logger.debug("Reddit rate limit: waiting %.1fs", wait)
            await asyncio.sleep(wait)

    agent = RSSAgent(
        country_code=feed_cfg["country_code"],
        language=feed_cfg["language"],
        source_name=feed_cfg["name"],
        feed_url=feed_cfg["url"],
        trust_score=feed_cfg["trust_score"],
        is_official=feed_cfg["is_official"],
        source_type_str=feed_cfg["source_type"],
    )

    result = {"name": feed_cfg["name"], "country": feed_cfg["country_code"],
              "fetched": 0, "transport": 0, "saved": 0, "error": None,
              "_source_type": feed_cfg.get("source_type", "news")}

    try:
        events = await agent.run_once()
        result["fetched"] = len(events)
        if is_reddit:
            _last_reddit_request = time.time()
    except Exception as e:
        result["error"] = str(e)
        logger.error("[%s] Fetch failed: %s", feed_cfg["name"], e)
        if is_reddit:
            _last_reddit_request = time.time()
        await agent.stop()
        return result

    if not events:
        await agent.stop()
        return result

    # The events from RSSAgent are already keyword-filtered (transport-related)
    result["transport"] = len(events)

    # Run through pipeline
    processed = []
    for ev in events:
        out = await asyncio.get_running_loop().run_in_executor(
            None, _run_pipeline, ev, pipeline
        )
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
            result["saved"] = await _save_events_to_db(processed, feed_cfg)
        except Exception as e:
            result["error"] = str(e)
            logger.error("[%s] DB save failed: %s", feed_cfg["name"], e)

    await agent.stop()
    return result


async def run_country(
    country_code: str,
    dry_run: bool = False,
    source_type_filter: str | None = None,
):
    """Run all feeds for a single country."""
    all_feeds = load_feeds()
    feeds = get_feeds_for_country(all_feeds, country_code, source_type_filter)

    if not feeds:
        logger.error("No feeds found for country: %s (filter=%s)", country_code, source_type_filter)
        return

    filter_label = f" [{source_type_filter}]" if source_type_filter else ""
    logger.info("=" * 70)
    logger.info("RSS Runner: %s%s — %d feeds", country_code, filter_label, len(feeds))
    logger.info("=" * 70)

    pipeline = _create_pipeline()
    total_start = time.time()
    results = []

    for feed_cfg in feeds:
        logger.info("--- %s [%s] ---", feed_cfg["name"], feed_cfg["source_type"])
        r = await run_feed(feed_cfg, pipeline, dry_run)
        results.append(r)
        logger.info("  Articles: %d fetched, %d transport-related, %d saved%s",
                     r["fetched"], r["transport"], r["saved"],
                     f" ERROR: {r['error']}" if r["error"] else "")

    # Summary
    elapsed = time.time() - total_start
    total_fetched = sum(r["fetched"] for r in results)
    total_transport = sum(r["transport"] for r in results)
    total_saved = sum(r["saved"] for r in results)
    errors = sum(1 for r in results if r["error"])

    logger.info("=" * 70)
    logger.info("PODSUMOWANIE %s%s:", country_code, filter_label)
    logger.info("  Czas:              %.1fs", elapsed)
    logger.info("  Feeds:             %d (%d errors)", len(results), errors)
    logger.info("  Articles fetched:  %d", total_fetched)
    logger.info("  Transport-related: %d", total_transport)
    logger.info("  Saved to DB:       %d", total_saved)
    logger.info("=" * 70)

    # Update agent_statuses per source_type for this country
    if not dry_run:
        from src.db.queries import update_agent_status
        by_type: dict[str, dict] = {}
        for r in results:
            st = r.get("_source_type", source_type_filter or "news")
            if st not in by_type:
                by_type[st] = {"saved": 0, "errors": 0}
            by_type[st]["saved"] += r["saved"]
            by_type[st]["errors"] += 1 if r["error"] else 0

        for st, stats in by_type.items():
            agent_type = f"rss_{st}" if not st.startswith("rss_") else st
            await update_agent_status(
                country_code=country_code,
                agent_type=agent_type,
                events_count=stats["saved"],
                errors_count=stats["errors"],
            )


async def run_all(dry_run: bool = False, source_type_filter: str | None = None):
    """Run all countries from rss_feeds.yaml."""
    all_feeds = load_feeds()
    countries = []
    for country_name in all_feeds:
        code = COUNTRY_CODE_MAP.get(country_name)
        if code:
            countries.append(code)

    logger.info("Running RSS feeds for %d countries: %s", len(countries), ", ".join(countries))

    for code in sorted(countries):
        await run_country(code, dry_run, source_type_filter)


async def run_reddit(dry_run: bool = False):
    """Run all Reddit feeds — global + per-country reddit sections."""
    all_feeds = load_feeds()
    pipeline = _create_pipeline()
    total_start = time.time()
    results = []

    # 1. Global Reddit feeds
    global_feeds = get_global_reddit_feeds(all_feeds)
    if global_feeds:
        logger.info("=" * 70)
        logger.info("Reddit Runner: GLOBAL — %d feeds", len(global_feeds))
        logger.info("=" * 70)

        for feed_cfg in global_feeds:
            logger.info("--- %s ---", feed_cfg["name"])
            r = await run_feed(feed_cfg, pipeline, dry_run)
            results.append(r)
            logger.info("  Posts: %d fetched, %d transport-related, %d saved%s",
                         r["fetched"], r["transport"], r["saved"],
                         f" ERROR: {r['error']}" if r["error"] else "")

    # 2. Per-country Reddit feeds
    for country_name in all_feeds:
        code = COUNTRY_CODE_MAP.get(country_name)
        if not code:
            continue
        country_feeds = get_feeds_for_country(all_feeds, code, source_type_filter="reddit")
        if not country_feeds:
            continue

        logger.info("=" * 70)
        logger.info("Reddit Runner: %s — %d feeds", code, len(country_feeds))
        logger.info("=" * 70)

        for feed_cfg in country_feeds:
            logger.info("--- %s ---", feed_cfg["name"])
            r = await run_feed(feed_cfg, pipeline, dry_run)
            results.append(r)
            logger.info("  Posts: %d fetched, %d transport-related, %d saved%s",
                         r["fetched"], r["transport"], r["saved"],
                         f" ERROR: {r['error']}" if r["error"] else "")

    # Summary
    elapsed = time.time() - total_start
    total_fetched = sum(r["fetched"] for r in results)
    total_transport = sum(r["transport"] for r in results)
    total_saved = sum(r["saved"] for r in results)
    errors = sum(1 for r in results if r["error"])

    logger.info("=" * 70)
    logger.info("PODSUMOWANIE REDDIT:")
    logger.info("  Czas:              %.1fs", elapsed)
    logger.info("  Feeds:             %d (%d errors)", len(results), errors)
    logger.info("  Posts fetched:     %d", total_fetched)
    logger.info("  Transport-related: %d", total_transport)
    logger.info("  Saved to DB:       %d", total_saved)
    logger.info("=" * 70)

    # Update agent_statuses per country for reddit
    if not dry_run:
        from src.db.queries import update_agent_status
        by_country: dict[str, dict] = {}
        for r in results:
            cc = r.get("country", "XX")
            if cc not in by_country:
                by_country[cc] = {"saved": 0, "errors": 0}
            by_country[cc]["saved"] += r["saved"]
            by_country[cc]["errors"] += 1 if r["error"] else 0

        for cc, stats in by_country.items():
            await update_agent_status(
                country_code=cc,
                agent_type="reddit",
                events_count=stats["saved"],
                errors_count=stats["errors"],
            )


def main():
    parser = argparse.ArgumentParser(description="Transport Intelligence RSS Runner")
    parser.add_argument("--country", help="Country ISO code (e.g. DE, PL)")
    parser.add_argument("--all", action="store_true", help="Run all countries")
    parser.add_argument("--reddit", action="store_true", help="Run all Reddit feeds (global + per-country)")
    parser.add_argument("--source-type", choices=["police", "news", "reddit", "all"],
                        default=None, help="Filter by source type")
    parser.add_argument("--once", action="store_true", help="Single execution (vs. loop)")
    parser.add_argument("--dry-run", action="store_true", help="Don't save to DB")
    args = parser.parse_args()

    if not args.country and not args.all and not args.reddit:
        parser.print_help()
        sys.exit(1)

    source_filter = args.source_type if args.source_type != "all" else None

    if args.reddit:
        asyncio.run(run_reddit(dry_run=args.dry_run))
    elif args.all:
        asyncio.run(run_all(dry_run=args.dry_run, source_type_filter=source_filter))
    else:
        asyncio.run(run_country(args.country, dry_run=args.dry_run, source_type_filter=source_filter))


if __name__ == "__main__":
    main()
