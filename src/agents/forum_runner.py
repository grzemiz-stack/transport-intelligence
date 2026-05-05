"""Forum Runner — uruchamia ForumAgent dla forow z forum_feeds.yaml.

Uzycie:
    python3 -m src.agents.forum_runner --country DE --once
    python3 -m src.agents.forum_runner --country PL --once
    python3 -m src.agents.forum_runner --all --once
    python3 -m src.agents.forum_runner --all --once --dry-run
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
logger = logging.getLogger("forum_runner")

FEEDS_PATH = Path(__file__).parent / "forum_feeds.yaml"

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
    "international": "XX",
}

CODE_TO_COUNTRY = {v: k for k, v in COUNTRY_CODE_MAP.items()}


def load_forum_feeds() -> dict:
    """Load forum feeds configuration from YAML."""
    if not FEEDS_PATH.exists():
        logger.error("Forum feeds file not found: %s", FEEDS_PATH)
        sys.exit(1)
    with open(FEEDS_PATH) as f:
        return yaml.safe_load(f)


def get_forums_for_country(all_feeds: dict, country_code: str) -> list[dict]:
    """Get flat list of forum configs for a country code."""
    country_code = country_code.upper()
    country_name = CODE_TO_COUNTRY.get(country_code)
    if not country_name or country_name not in all_feeds:
        return []

    country_cfg = all_feeds[country_name]
    language = country_cfg.get("language", "en")
    forums = []

    for forum in country_cfg.get("forums", []):
        forums.append({
            "name": forum["name"],
            "url": forum["url"],
            "rss_url": forum.get("rss_url"),
            "trust_score": forum.get("trust_score", 0.3),
            "is_official": forum.get("is_official", False),
            "language": forum.get("language", language),
            "country_code": country_code,
            "forum_type": forum.get("forum_type", "generic"),
            "keywords_extra": forum.get("keywords_extra"),
        })

    return forums


# ── Translator ───────────────────────────────────────────────────────────

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


# ── Pipeline (reuse from runner.py) ──────────────────────────────────────

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

    # Anonymize — extra important for forums (GDPR: no nicknames)
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


# ── DB save ──────────────────────────────────────────────────────────────

async def _save_events_to_db(events: list[dict], forum_cfg: dict) -> int:
    """Save processed events to PostgreSQL."""
    from sqlalchemy import select

    from src.db.models import Event, Source
    from src.db.postgres import async_session

    saved = 0

    async with async_session() as session:
        # Find or create source record
        result = await session.execute(
            select(Source).where(Source.name == forum_cfg["name"])
        )
        source = result.scalar_one_or_none()

        if source is None:
            source = Source(
                id=uuid.uuid4(),
                name=forum_cfg["name"],
                source_type="forum",
                url=forum_cfg["url"],
                country_code=forum_cfg["country_code"],
                trust_score=forum_cfg["trust_score"],
                is_official=forum_cfg["is_official"],
                is_active=True,
                scrape_interval_minutes=120,
            )
            session.add(source)
            await session.flush()
            logger.info("Created source: %s (id=%s)", forum_cfg["name"], source.id)

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
                    date_occurred = datetime.fromisoformat(
                        date_val.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    pass

            # Make datetime naive for PostgreSQL
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
                country_code=ev.get("country_code", forum_cfg["country_code"]),
                region=location.get("region") if isinstance(location, dict) else None,
                city=location.get("city") if isinstance(location, dict) else None,
                source_id=source.id,
                trust_score=ev.get("trust_score", forum_cfg["trust_score"]),
                is_verified=False,
                is_anonymized=ev.get("is_anonymized", True),
                raw_text=(ev.get("raw_text") or "")[:5000],
                processed_text=ev.get("description"),
                source_url=src_url or None,
                language=ev.get("language", forum_cfg["language"]),
                tags=ev.get("tags"),
            )
            session.add(db_event)
            saved += 1

        source.last_scraped = datetime.utcnow()
        source.total_events_collected = (source.total_events_collected or 0) + saved

        await session.commit()

    return saved


# ── Main ─────────────────────────────────────────────────────────────────

async def run_forum(forum_cfg: dict, pipeline: dict, dry_run: bool = False, translator=None) -> dict:
    """Run a single forum through the full pipeline."""
    from src.agents.forum_agent import ForumAgent

    agent = ForumAgent(
        country_code=forum_cfg["country_code"],
        language=forum_cfg["language"],
        source_name=forum_cfg["name"],
        forum_url=forum_cfg["url"],
        trust_score=forum_cfg["trust_score"],
        is_official=forum_cfg["is_official"],
        forum_type=forum_cfg["forum_type"],
        rss_url=forum_cfg.get("rss_url"),
        keywords_extra=forum_cfg.get("keywords_extra"),
    )

    result = {
        "name": forum_cfg["name"],
        "country": forum_cfg["country_code"],
        "fetched": 0,
        "matched": 0,
        "saved": 0,
        "error": None,
        "method": "unknown",
    }

    try:
        events = await agent.run_once()
        result["fetched"] = agent.events_collected
        result["matched"] = len(events)

        # Detect method used
        if hasattr(agent, '_logger'):
            result["method"] = "rss+html"
    except Exception as e:
        result["error"] = str(e)
        logger.error("[%s] Fetch failed: %s", forum_cfg["name"], e)
        await agent.stop()
        return result

    if not events:
        await agent.stop()
        return result

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

    if dry_run:
        result["saved"] = 0
        for ev in processed:
            logger.info("  [DRY] [%s] %s", ev.get("event_type", "?"),
                        ev.get("title", "?")[:80])
    else:
        try:
            result["saved"] = await _save_events_to_db(processed, forum_cfg)
        except Exception as e:
            result["error"] = str(e)
            logger.error("[%s] DB save failed: %s", forum_cfg["name"], e)

    await agent.stop()
    return result


async def run_country(country_code: str, dry_run: bool = False):
    """Run all forums for a single country."""
    all_feeds = load_forum_feeds()
    forums = get_forums_for_country(all_feeds, country_code)

    if not forums:
        logger.error("No forums found for country: %s", country_code)
        return

    logger.info("=" * 70)
    logger.info("Forum Runner: %s — %d forums", country_code, len(forums))
    logger.info("=" * 70)

    pipeline = _create_pipeline()
    total_start = time.time()
    results = []

    for forum_cfg in forums:
        logger.info("--- %s [%s] ---", forum_cfg["name"], forum_cfg["forum_type"])
        r = await run_forum(forum_cfg, pipeline, dry_run)
        results.append(r)
        logger.info(
            "  Threads: %d matched, %d saved%s",
            r["matched"], r["saved"],
            f" ERROR: {r['error']}" if r["error"] else "",
        )

    # Summary
    elapsed = time.time() - total_start
    total_matched = sum(r["matched"] for r in results)
    total_saved = sum(r["saved"] for r in results)
    errors = sum(1 for r in results if r["error"])

    logger.info("=" * 70)
    logger.info("PODSUMOWANIE %s:", country_code)
    logger.info("  Czas:              %.1fs", elapsed)
    logger.info("  Forums:            %d (%d errors)", len(results), errors)
    logger.info("  Threads matched:   %d", total_matched)
    logger.info("  Saved to DB:       %d", total_saved)
    logger.info("=" * 70)

    # Update agent_statuses for this country
    if not dry_run:
        from src.db.queries import update_agent_status
        await update_agent_status(
            country_code=country_code,
            agent_type="forum",
            events_count=total_saved,
            errors_count=errors,
        )


async def run_all(dry_run: bool = False):
    """Run all countries from forum_feeds.yaml."""
    all_feeds = load_forum_feeds()
    countries = []
    for country_name in all_feeds:
        code = COUNTRY_CODE_MAP.get(country_name)
        if code:
            countries.append(code)

    logger.info("Running forums for %d countries: %s",
                len(countries), ", ".join(sorted(countries)))

    for code in sorted(countries):
        await run_country(code, dry_run)


def main():
    parser = argparse.ArgumentParser(
        description="Transport Intelligence Forum Runner"
    )
    parser.add_argument("--country", help="Country ISO code (e.g. DE, PL, GB)")
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
