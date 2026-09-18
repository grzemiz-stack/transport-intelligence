"""Runner agentow — uruchamia agenta end-to-end z pelnym pipeline'em.

Uzycie:
    python -m src.agents.runner --country DE --agent police --once
    python -m src.agents.runner --country DE --agent police --once --dry-run

Pipeline flow:
    1. Agent fetch + parse -> raw events
    2. Dla kazdego raw event:
       a. source_validator.is_legal_to_scrape(url)
       b. parser.parse_raw_event(event)
       c. anonymizer.anonymize_personal_data(text)
       d. gdpr_filter.check_compliance(event)
       e. normalizer.normalize(event)
       f. classifier.classify(event)
       g. legal_filter.filter_event(event)
    3. Zapis do PostgreSQL (tabela events)
    4. Log podsumowanie
"""

import argparse
import asyncio
import logging
import sys
import time
import uuid
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("runner")

# Registry of available agents per country
AGENT_REGISTRY: dict[str, dict[str, type]] = {}


def _register_agents():
    """Rejestruje dostepne agenty."""
    from functools import partial

    from src.agents.police.base import BasePoliceAgent
    from src.agents.police.custom import (
        AustrianPoliceAgent,
        BundespolizeiAgent,
        SwissPoliceAgent,
        TurkishPoliceAgent,
    )
    from src.agents.police.sources import SOURCES

    from src.agents.countries.poland.financial_live import PolishFinancialAgent
    from src.agents.financial.companies_house_uk import UKCompaniesHouseAgent
    from src.agents.financial.insolvency_at import AustrianInsolvencyAgent
    from src.agents.financial.insolvency_de import GermanInsolvencyAgent
    from src.agents.financial.insolvency_fr import FrenchInsolvencyAgent
    from src.agents.financial.insolvency_pl import PolishInsolvencyAgent
    from src.agents.financial.licenses_pl import PolishLicenseAgent

    # 25 standard police agents from config
    for code, cfg in SOURCES.items():
        AGENT_REGISTRY.setdefault(code, {})["police"] = partial(BasePoliceAgent, cfg)

    # 4 custom police agents (override standard entries)
    AGENT_REGISTRY.setdefault("DE", {})["police"] = BundespolizeiAgent
    AGENT_REGISTRY.setdefault("AT", {})["police"] = AustrianPoliceAgent
    AGENT_REGISTRY.setdefault("TR", {})["police"] = TurkishPoliceAgent
    AGENT_REGISTRY.setdefault("CH", {})["police"] = SwissPoliceAgent

    # Non-police agents
    AGENT_REGISTRY["PL"]["financial"] = PolishFinancialAgent
    AGENT_REGISTRY["PL"]["insolvency"] = PolishInsolvencyAgent
    AGENT_REGISTRY["PL"]["licenses"] = PolishLicenseAgent
    AGENT_REGISTRY["DE"]["insolvency"] = GermanInsolvencyAgent
    AGENT_REGISTRY["FR"]["insolvency"] = FrenchInsolvencyAgent
    AGENT_REGISTRY["AT"]["insolvency"] = AustrianInsolvencyAgent
    AGENT_REGISTRY["GB"]["companies_house"] = UKCompaniesHouseAgent


# -- Pipeline components ---------------------------------------------------


def _create_pipeline():
    """Tworzy instancje komponentow pipeline'u."""
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
    """Przepuszcza event przez caly pipeline.

    Returns:
        Przetworzony event lub None jesli odrzucony.
    """
    sv = pipeline["source_validator"]
    parser = pipeline["parser"]
    anonymizer = pipeline["anonymizer"]
    gdpr = pipeline["gdpr_filter"]
    normalizer = pipeline["normalizer"]
    classifier = pipeline["classifier"]
    legal = pipeline["legal_filter"]

    source_url = event.get("source_url", "")

    # 1. Source validator
    if source_url and not sv.is_legal_to_scrape(source_url):
        logger.warning("Source rejected by validator: %s", source_url)
        return None

    # 2. Parser — extract structured fields
    parsed = parser.parse_raw_event(event)
    # Merge back fields not handled by parser
    for key in ("trust_score", "is_official", "source_type", "language",
                 "collected_at", "timestamp", "source_name", "country_code"):
        if key in event and key not in parsed:
            parsed[key] = event[key]

    # 3. Anonymizer — remove PII from text fields
    for field in ("title", "description", "raw_text"):
        text = parsed.get(field)
        if text:
            parsed[field] = anonymizer.anonymize_personal_data(text)
    parsed["is_anonymized"] = True

    # 4. GDPR filter
    gdpr_result = gdpr.check_compliance(parsed)
    gdpr_status = gdpr_result.get("status", "non_compliant")
    if gdpr_status == "non_compliant":
        logger.info("GDPR rejected: %s — %s", parsed.get("title", "?")[:60], gdpr_result.get("reason"))
        return None
    if gdpr_status == "needs_review":
        logger.info("GDPR needs review: %s", parsed.get("title", "?")[:60])
        parsed["_needs_legal_review"] = True

    # 5. Normalizer
    parsed = normalizer.normalize(parsed)

    # 6. Classifier — assign event_type, severity, tags
    parsed = classifier.classify(parsed)

    # 7. Legal filter
    filtered = legal.filter_event(parsed)
    if filtered is None:
        logger.info("Legal filter rejected: %s", parsed.get("title", "?")[:60])
        return None

    return filtered


# -- DB save ---------------------------------------------------------------


async def _save_events_to_db(events: list[dict]) -> int:
    """Zapisuje przetworzone eventy do PostgreSQL.

    Returns:
        Liczba zapisanych eventow.
    """
    from sqlalchemy import select

    from src.db.models import Event, Source
    from src.db.postgres import async_session

    saved = 0

    async with async_session() as session:
        # Find or create source record dynamically based on event data
        source_name = events[0].get("source_name", "Unknown") if events else "Unknown"
        source_type = events[0].get("source_type", "police") if events else "police"
        country_code = events[0].get("country_code", "XX") if events else "XX"
        source_url = events[0].get("source_url", "") if events else ""

        result = await session.execute(
            select(Source).where(Source.name == source_name)
        )
        source = result.scalar_one_or_none()

        if source is None:
            source = Source(
                id=uuid.uuid4(),
                name=source_name,
                source_type=source_type,
                url=source_url,
                country_code=country_code,
                trust_score=events[0].get("trust_score", 1.0) if events else 1.0,
                is_official=events[0].get("is_official", True) if events else True,
                is_active=True,
                scrape_interval_minutes=60,
            )
            session.add(source)
            await session.flush()
            logger.info("Created source record: %s (id=%s)", source_name, source.id)

        for ev in events:
            # Check for duplicate by source_url
            src_url = ev.get("source_url", "")
            if src_url:
                dup = await session.execute(
                    select(Event.id).where(Event.source_url == src_url).limit(1)
                )
                if dup.scalar_one_or_none():
                    logger.debug("Duplicate skipped: %s", src_url)
                    continue

            # Parse date_occurred
            date_occurred = None
            date_val = ev.get("date_parsed") or ev.get("date")
            if isinstance(date_val, datetime):
                date_occurred = date_val
            elif isinstance(date_val, str) and date_val:
                try:
                    date_occurred = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            # Map location fields
            location = ev.get("location", {})

            db_event = Event(
                id=uuid.uuid4(),
                event_type=ev.get("event_type", "other"),
                severity=ev.get("severity", "medium"),
                title=(ev.get("title") or "Bez tytulu")[:500],
                description=ev.get("description"),
                date_occurred=date_occurred,
                date_collected=datetime.utcnow(),
                country_code=ev.get("country_code", "DE"),
                region=location.get("region") if isinstance(location, dict) else None,
                city=location.get("city") if isinstance(location, dict) else None,
                source_id=source.id,
                trust_score=ev.get("trust_score", 1.0),
                is_verified=False,
                is_anonymized=ev.get("is_anonymized", True),
                raw_text=(ev.get("raw_text") or "")[:5000],
                processed_text=ev.get("description"),
                source_url=src_url or None,
                language=ev.get("language", "de"),
                tags=ev.get("tags"),
                financial_impact_eur=ev.get("financial_impact_eur"),
            )
            session.add(db_event)
            saved += 1

        # Update source stats
        source.last_scraped = datetime.utcnow()
        source.total_events_collected = (source.total_events_collected or 0) + saved

        await session.commit()

    return saved


# -- Main ------------------------------------------------------------------


async def run_agent(country: str, agent_name: str, once: bool = True, dry_run: bool = False):
    """Uruchamia agenta z pelnym pipeline'em."""
    _register_agents()

    country = country.upper()
    if country not in AGENT_REGISTRY:
        logger.error("Nieznany kraj: %s. Dostepne: %s", country, list(AGENT_REGISTRY.keys()))
        sys.exit(1)

    agents = AGENT_REGISTRY[country]
    if agent_name not in agents:
        logger.error("Nieznany agent: %s. Dostepne dla %s: %s", agent_name, country, list(agents.keys()))
        sys.exit(1)

    agent_cls = agents[agent_name]
    agent = agent_cls()

    logger.info("=" * 70)
    logger.info("START: %s / %s (country=%s, once=%s, dry_run=%s)",
                agent.source_name, agent_name, country, once, dry_run)
    logger.info("=" * 70)

    pipeline = _create_pipeline()

    total_start = time.time()

    # Phase 1: Fetch + Parse
    logger.info("--- Phase 1: Fetch + Parse ---")
    try:
        events = await agent.run_once()
    except Exception as e:
        logger.error("Agent fetch/parse failed: %s", e)
        await agent.stop()
        return

    logger.info("Agent returned %d raw events", len(events))

    if not events:
        logger.info("Brak eventow do przetworzenia — koniec")
        await agent.stop()
        return

    # Phase 2: Pipeline
    logger.info("--- Phase 2: Pipeline ---")
    processed = []
    rejected_source = 0
    rejected_gdpr = 0
    rejected_legal = 0

    for i, ev in enumerate(events, 1):
        logger.debug("Pipeline event %d/%d: %s", i, len(events), ev.get("title", "?")[:60])
        result = await asyncio.get_running_loop().run_in_executor(
            None, _run_pipeline, ev, pipeline
        )
        if result is None:
            # Count rejection reason (approximation from logs)
            continue
        processed.append(result)

    logger.info("Pipeline: %d input -> %d output (%d rejected)",
                len(events), len(processed), len(events) - len(processed))

    # Phase 3: DB Save
    if dry_run:
        logger.info("--- Phase 3: DRY RUN — pomijam zapis do DB ---")
        for ev in processed:
            logger.info(
                "  [%s] [%s] %s",
                ev.get("event_type", "?"),
                ev.get("severity", "?"),
                ev.get("title", "?")[:80],
            )
        saved = 0
    else:
        logger.info("--- Phase 3: Zapis do PostgreSQL ---")
        try:
            saved = await _save_events_to_db(processed)
        except Exception as e:
            logger.error("DB save failed: %s", e, exc_info=True)
            saved = 0

    # Phase 4: Summary
    total_elapsed = time.time() - total_start
    logger.info("=" * 70)
    logger.info("PODSUMOWANIE:")
    logger.info("  Czas calkowity:    %.1fs", total_elapsed)
    logger.info("  Raw events:        %d", len(events))
    logger.info("  Po pipeline:       %d", len(processed))
    logger.info("  Odrzucone:         %d", len(events) - len(processed))
    logger.info("  Zapisane do DB:    %d", saved)
    logger.info("  Agent status:      collected=%d errors=%d", agent.events_collected, agent.errors_count)
    logger.info("=" * 70)

    # Update agent_statuses per country
    if not dry_run:
        from src.db.queries import update_agent_status
        await update_agent_status(
            country_code=country,
            agent_type=agent_name,
            events_count=saved,
            errors_count=agent.errors_count,
        )

    await agent.stop()


ALL_POLICE_COUNTRIES = [
    "DE", "PL", "FR", "NL", "IT", "ES", "CZ", "RO", "GB", "AT",
    "BE", "DK", "SE", "NO", "FI", "HU", "HR", "SI", "RS", "BG",
    "GR", "TR", "UA", "LT", "LV", "EE", "SK", "MD", "CH",
]
RATE_LIMIT_BETWEEN_COUNTRIES = 10.0  # sekund przerwy miedzy krajami


async def run_all_police(once: bool = True, dry_run: bool = False):
    """Uruchamia police scraper dla wszystkich krajow z rate limiting."""
    _register_agents()
    logger.info("=" * 70)
    logger.info("START: all_police_scrapers (%d krajow)", len(ALL_POLICE_COUNTRIES))
    logger.info("=" * 70)

    total_start = time.time()
    total_events = 0
    total_errors = 0

    for i, country in enumerate(ALL_POLICE_COUNTRIES):
        if country not in AGENT_REGISTRY or "police" not in AGENT_REGISTRY[country]:
            logger.warning("Brak police agenta dla %s — skip", country)
            continue

        logger.info("--- [%d/%d] %s police ---", i + 1, len(ALL_POLICE_COUNTRIES), country)
        try:
            await run_agent(country=country, agent_name="police", once=once, dry_run=dry_run)
        except Exception as e:
            logger.error("Police agent %s failed: %s", country, e)
            total_errors += 1

        # Rate limit between countries
        if i < len(ALL_POLICE_COUNTRIES) - 1:
            logger.info("Rate limit: czekam %.0fs przed nastepnym krajem...",
                        RATE_LIMIT_BETWEEN_COUNTRIES)
            await asyncio.sleep(RATE_LIMIT_BETWEEN_COUNTRIES)

    total_elapsed = time.time() - total_start
    logger.info("=" * 70)
    logger.info("ALL POLICE DONE: %.1fs, %d errors", total_elapsed, total_errors)
    logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Transport Intelligence Agent Runner")
    parser.add_argument("--country", help="Kod kraju ISO 2-literowy (np. DE)")
    parser.add_argument("--agent", help="Nazwa agenta (np. police)")
    parser.add_argument("--all-police", action="store_true",
                        help="Uruchom police scraper dla wszystkich krajow")
    parser.add_argument("--once", action="store_true", help="Jednorazowe uruchomienie")
    parser.add_argument("--dry-run", action="store_true", help="Nie zapisuj do DB")
    args = parser.parse_args()

    if args.all_police:
        asyncio.run(run_all_police(once=args.once, dry_run=args.dry_run))
    elif args.country and args.agent:
        asyncio.run(run_agent(
            country=args.country,
            agent_name=args.agent,
            once=args.once,
            dry_run=args.dry_run,
        ))
    else:
        parser.error("Podaj --country + --agent lub --all-police")


if __name__ == "__main__":
    main()
