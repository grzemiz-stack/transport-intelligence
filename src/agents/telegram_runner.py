"""Telegram Runner — uruchamia TelegramMonitor w trybie scan lub listen.

Uzycie:
    python -m src.agents.telegram_runner --scan-once
    python -m src.agents.telegram_runner --scan-once --country PL
    python -m src.agents.telegram_runner --scan-once --dry-run
    python -m src.agents.telegram_runner --listen
"""

import argparse
import asyncio
import logging
import os
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
logger = logging.getLogger("telegram_runner")

CHANNELS_PATH = Path(__file__).parent / "telegram_channels.yaml"

# Rate limits
RATE_LIMIT_BETWEEN_CHANNELS = 5.0  # seconds between channel fetches (increased to reduce flood rate)


def _load_env():
    """Load .env file if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass


def load_channels() -> dict:
    """Load Telegram channel configuration from YAML."""
    if not CHANNELS_PATH.exists():
        logger.error("Channels file not found: %s", CHANNELS_PATH)
        sys.exit(1)
    with open(CHANNELS_PATH) as f:
        return yaml.safe_load(f)


def get_channels_flat(all_channels: dict, country_filter: str | None = None) -> list[dict]:
    """Get flat list of channel configs from YAML.

    Supports two YAML formats:
    1. Flat list:  region_name: [{name, channel, language, ...}, ...]
    2. Nested:     country_name: {country_code, language, channels: [...]}
    """
    result = []
    for region_name, region_cfg in all_channels.items():
        # Format 1: flat list of channels directly under region key
        if isinstance(region_cfg, list):
            for ch in region_cfg:
                cc = ch.get("country_code", "EU")
                if country_filter and cc != country_filter.upper():
                    continue
                result.append({
                    "name": ch["name"],
                    "channel": ch["channel"],
                    "language": ch.get("language", "en"),
                    "country_code": cc,
                    "country_name": region_name,
                })
        # Format 2: nested dict with country_code + channels list
        elif isinstance(region_cfg, dict):
            country_code = region_cfg.get("country_code", "XX")
            default_lang = region_cfg.get("language", "en")
            if country_filter and country_code != country_filter.upper():
                continue
            for ch in region_cfg.get("channels", []):
                result.append({
                    "name": ch["name"],
                    "channel": ch["channel"],
                    "language": ch.get("language", default_lang),
                    "country_code": country_code,
                    "country_name": region_name,
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


# -- Pipeline ---------------------------------------------------------------

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
    parser = pipeline["parser"]
    anonymizer = pipeline["anonymizer"]
    gdpr = pipeline["gdpr_filter"]
    normalizer = pipeline["normalizer"]
    classifier = pipeline["classifier"]
    legal = pipeline["legal_filter"]

    # Skip source_validator for t.me URLs (Telegram links aren't scrape targets)
    parsed = parser.parse_raw_event(event)
    for key in ("trust_score", "is_official", "source_type", "language",
                "collected_at", "timestamp", "source_name", "country_code"):
        if key in event and key not in parsed:
            parsed[key] = event[key]

    # Extra anonymization pass on already-anonymized text (belt and suspenders for GDPR)
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

async def _save_events_to_db(events: list[dict], channel_cfg: dict) -> int:
    """Save processed Telegram events to PostgreSQL."""
    from sqlalchemy import select
    from src.db.models import Event, Source
    from src.db.postgres import async_session

    saved = 0
    source_name = f"Telegram/{channel_cfg['name']}"

    async with async_session() as session:
        result = await session.execute(
            select(Source).where(Source.name == source_name)
        )
        source = result.scalar_one_or_none()

        if source is None:
            source = Source(
                id=uuid.uuid4(),
                name=source_name,
                source_type="telegram",
                url=f"https://t.me/{channel_cfg['channel']}",
                country_code=channel_cfg.get("country_code", "XX"),
                trust_score=0.3,
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
                title=(ev.get("title") or "Telegram message")[:500],
                description=ev.get("description"),
                date_occurred=date_occurred,
                date_collected=datetime.utcnow(),
                country_code=ev.get("country_code", channel_cfg.get("country_code", "XX")),
                region=location.get("region") if isinstance(location, dict) else None,
                city=location.get("city") if isinstance(location, dict) else None,
                source_id=source.id,
                trust_score=ev.get("trust_score", 0.3),
                is_verified=False,
                is_anonymized=True,
                raw_text=(ev.get("raw_text") or "")[:5000],
                processed_text=ev.get("description"),
                source_url=src_url or None,
                language=ev.get("language", channel_cfg.get("language", "en")),
                tags=ev.get("tags"),
            )
            session.add(db_event)
            saved += 1

        source.last_scraped = datetime.utcnow()
        source.total_events_collected = (source.total_events_collected or 0) + saved

        await session.commit()

    return saved


async def _save_single_event(event: dict) -> int:
    """Save a single event to DB (used in real-time listen mode)."""
    channel_cfg = {
        "name": event.get("telegram_channel", "unknown"),
        "channel": event.get("telegram_channel", "unknown"),
        "country_code": event.get("country_code", "XX"),
        "language": event.get("language", "en"),
    }
    return await _save_events_to_db([event], channel_cfg)


# -- Scan mode --------------------------------------------------------------

async def scan_once(country_filter: str | None = None, dry_run: bool = False):
    """Fetch recent messages from all configured channels."""
    _load_env()

    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    session_name = os.environ.get("TELEGRAM_SESSION_NAME", "ti_session")

    if not api_id or not api_hash:
        logger.error("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env")
        sys.exit(1)

    from src.agents.telegram_agent import TelegramMonitor

    monitor = TelegramMonitor(api_id, api_hash, session_name)

    try:
        await monitor.connect()
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)

    all_channels = load_channels()
    channels = get_channels_flat(all_channels, country_filter)

    if not channels:
        logger.error("No channels found%s", f" for country {country_filter}" if country_filter else "")
        await monitor.disconnect()
        return

    logger.info("=" * 70)
    logger.info("Telegram Scan: %d channels%s",
                len(channels),
                f" (country={country_filter})" if country_filter else "")
    logger.info("=" * 70)

    pipeline = _create_pipeline()
    translator = _create_translator()
    total_start = time.time()
    total_fetched = 0
    total_transport = 0
    total_saved = 0
    total_errors = 0

    for i, ch_cfg in enumerate(channels):
        logger.info("--- [%d/%d] %s (%s) ---", i + 1, len(channels), ch_cfg["name"], ch_cfg["channel"])

        try:
            events = await monitor.fetch_recent_messages(
                channel_id=ch_cfg["channel"],
                language=ch_cfg["language"],
                limit=100,
                trusted_transport=True,
            )
        except Exception as e:
            logger.error("Fetch failed for '%s': %s", ch_cfg["channel"], e)
            total_errors += 1
            continue

        total_fetched += 100  # attempted
        total_transport += len(events)

        if not events:
            logger.info("  No transport-related messages")
        else:
            # Run through pipeline with dual-stream routing
            processed_ti = []
            total_road_alerts_ch = 0
            for ev in events:
                ev["country_code"] = ch_cfg["country_code"]
                out = _run_pipeline(ev, pipeline)
                if out is None:
                    continue

                # Translate non-Polish events if enabled
                if translator and out.get("language") != "pl":
                    try:
                        out = await translator.translate_event(out)
                    except Exception as tr_err:
                        logger.debug("Translation skipped: %s", tr_err)

                # Dual-stream routing
                is_ti = ev.get("_stream_ti", True)
                is_cc = ev.get("_stream_cc", False)

                if is_cc:
                    from src.agents.road_alerts_writer import save_road_alert
                    save_road_alert(out, ch_cfg)
                    total_road_alerts_ch += 1
                if is_ti:
                    processed_ti.append(out)

            if total_road_alerts_ch:
                logger.info("  Wrote %d road alerts to JSONL", total_road_alerts_ch)

            if dry_run:
                for ev in processed_ti:
                    logger.info("  [DRY] [%s] %s", ev.get("event_type", "?"), ev.get("title", "?")[:80])
            else:
                try:
                    saved = await _save_events_to_db(processed_ti, ch_cfg)
                    total_saved += saved
                    logger.info("  Saved %d events to DB", saved)
                except Exception as e:
                    logger.error("  DB save failed: %s", e)
                    total_errors += 1

        # Rate limit
        if i < len(channels) - 1:
            await asyncio.sleep(RATE_LIMIT_BETWEEN_CHANNELS)

    await monitor.disconnect()

    elapsed = time.time() - total_start
    logger.info("=" * 70)
    logger.info("PODSUMOWANIE:")
    logger.info("  Czas:              %.1fs", elapsed)
    logger.info("  Channels:          %d (%d errors)", len(channels), total_errors)
    logger.info("  Transport-related: %d", total_transport)
    logger.info("  Saved to DB:       %d", total_saved)
    logger.info("=" * 70)

    # Update agent_statuses per country_code
    if not dry_run:
        from src.db.queries import update_agent_status
        by_country: dict[str, dict] = {}
        for ch_cfg in channels:
            cc = ch_cfg.get("country_code", "EU")
            if cc not in by_country:
                by_country[cc] = {"saved": 0, "errors": 0}
        # We don't track per-channel saved counts in the loop, so use totals
        # with a single "EU" entry for all European channels
        await update_agent_status(
            country_code="EU",
            agent_type="telegram",
            events_count=total_saved,
            errors_count=total_errors,
        )


# -- Listen mode (24/7 real-time) -------------------------------------------

async def listen(country_filter: str | None = None):
    """Listen for new messages in real-time (24/7 mode)."""
    _load_env()

    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    session_name = os.environ.get("TELEGRAM_SESSION_NAME", "ti_session")

    if not api_id or not api_hash:
        logger.error("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env")
        sys.exit(1)

    from src.agents.telegram_agent import TelegramMonitor

    monitor = TelegramMonitor(api_id, api_hash, session_name)

    try:
        await monitor.connect()
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)

    all_channels = load_channels()
    channels = get_channels_flat(all_channels, country_filter)

    if not channels:
        logger.error("No channels configured")
        await monitor.disconnect()
        return

    # Join/resolve all channels first
    resolved = []
    for ch_cfg in channels:
        entity = await monitor.resolve_channel(ch_cfg["channel"])
        if entity is not None:
            resolved.append(ch_cfg)
        await asyncio.sleep(0.5)  # gentle rate limit on resolve

    logger.info("=" * 70)
    logger.info("Telegram Listen: %d/%d channels resolved", len(resolved), len(channels))
    logger.info("=" * 70)

    if not resolved:
        logger.error("No channels could be resolved — nothing to listen to")
        await monitor.disconnect()
        return

    # Pipeline for real-time processing
    pipeline = _create_pipeline()

    async def on_new_message(event_dict: dict):
        """Callback for each new transport/road-alert message (dual-stream)."""
        out = _run_pipeline(event_dict, pipeline)
        if out is None:
            return

        is_ti = event_dict.get("_stream_ti", True)
        is_cc = event_dict.get("_stream_cc", False)

        if is_cc:
            from src.agents.road_alerts_writer import save_road_alert
            ch_cfg = {
                "name": event_dict.get("telegram_channel", "unknown"),
                "country_code": event_dict.get("country_code", "XX"),
            }
            save_road_alert(out, ch_cfg)
            logger.info("Road alert saved: %s", out.get("title", "?")[:80])

        if is_ti:
            saved = await _save_single_event(out)
            if saved > 0:
                logger.info("Saved real-time event: %s", out.get("title", "?")[:80])

    # Register real-time handler
    monitor.create_realtime_handler(resolved, on_new_message)

    logger.info("Listening for new messages... (Ctrl+C to stop)")

    try:
        await monitor.client.run_until_disconnected()
    except KeyboardInterrupt:
        logger.info("Stopping listener...")
    finally:
        await monitor.disconnect()


# -- CLI --------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Transport Intelligence Telegram Runner")
    parser.add_argument("--scan-once", action="store_true",
                        help="Fetch recent messages from all channels (one-time)")
    parser.add_argument("--listen", action="store_true",
                        help="Listen for new messages in real-time (24/7)")
    parser.add_argument("--country", help="Filter by country code (e.g. PL, DE)")
    parser.add_argument("--dry-run", action="store_true", help="Don't save to DB")
    args = parser.parse_args()

    if not args.scan_once and not args.listen:
        parser.print_help()
        sys.exit(1)

    if args.scan_once:
        asyncio.run(scan_once(country_filter=args.country, dry_run=args.dry_run))
    elif args.listen:
        asyncio.run(listen(country_filter=args.country))


if __name__ == "__main__":
    main()
