"""Test BundespolizeiAgent — dry run bez zapisu do bazy.

Uzycie:
    cd /Users/osx/transport-intelligence
    python -m src.agents.countries.germany.test_police
"""

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("test_police")


async def test_fetch():
    """Test 1: Sprawdz czy fetch zwraca HTML (HTTP 200)."""
    from src.agents.countries.germany.police_live import BundespolizeiAgent

    agent = BundespolizeiAgent()
    logger.info("TEST 1: fetch()")

    try:
        html = await agent.fetch()
    except Exception as e:
        logger.error("FAIL: fetch() rzucil wyjatek: %s", e)
        await agent.stop()
        return False

    if not html:
        logger.error("FAIL: fetch() zwrocil pusty string")
        await agent.stop()
        return False

    if not isinstance(html, str):
        logger.error("FAIL: fetch() zwrocil %s zamiast str", type(html))
        await agent.stop()
        return False

    if len(html) < 1000:
        logger.warning("WARN: HTML bardzo krotki (%d bytes) — moze byc redirect/blokada", len(html))

    logger.info("OK: fetch() zwrocil %d bytes HTML", len(html))
    await agent.stop()
    return html


async def test_parse(html: str):
    """Test 2: Sprawdz czy parse zwraca liste eventow."""
    from src.agents.countries.germany.police_live import BundespolizeiAgent

    agent = BundespolizeiAgent()
    logger.info("TEST 2: parse()")

    try:
        events = await agent.parse(html)
    except Exception as e:
        logger.error("FAIL: parse() rzucil wyjatek: %s", e)
        await agent.stop()
        return False

    if not isinstance(events, list):
        logger.error("FAIL: parse() zwrocil %s zamiast list", type(events))
        await agent.stop()
        return False

    logger.info("OK: parse() zwrocil %d eventow", len(events))

    # Podsumowanie
    if events:
        for i, ev in enumerate(events[:5], 1):
            logger.info("  Event %d: [%s] %s", i, ev.get("date", "?"), ev.get("title", "?")[:80])
        if len(events) > 5:
            logger.info("  ... i %d wiecej", len(events) - 5)
    else:
        logger.info("  (brak eventow transportowych — to normalne jesli aktualne komunikaty nie dotycza transportu)")

    await agent.stop()
    return events


async def test_pipeline(events: list[dict]):
    """Test 3: Sprawdz czy pipeline przetwarza eventy (dry run)."""
    from src.agents.runner import _create_pipeline, _run_pipeline

    logger.info("TEST 3: pipeline (dry run)")

    pipeline = _create_pipeline()
    processed = []

    for ev in events:
        result = _run_pipeline(ev, pipeline)
        if result is not None:
            processed.append(result)

    logger.info("OK: pipeline %d input -> %d output", len(events), len(processed))

    for i, ev in enumerate(processed[:5], 1):
        logger.info(
            "  Event %d: type=%s severity=%s tags=%s | %s",
            i,
            ev.get("event_type", "?"),
            ev.get("severity", "?"),
            ev.get("tags", []),
            ev.get("title", "?")[:60],
        )

    return processed


async def test_validate(events: list[dict]):
    """Test 4: Sprawdz walidacje eventow."""
    from src.agents.countries.germany.police_live import BundespolizeiAgent

    agent = BundespolizeiAgent()
    logger.info("TEST 4: validate()")

    validated = await agent.validate(events)
    logger.info("OK: validate() %d input -> %d output", len(events), len(validated))

    # Check that metadata was added
    if validated:
        ev = validated[0]
        checks = {
            "country_code": ev.get("country_code") == "DE",
            "language": ev.get("language") == "de",
            "source_name": ev.get("source_name") == "Bundespolizei",
            "trust_score": ev.get("trust_score") == 1.0,
            "is_official": ev.get("is_official") is True,
        }
        for field, ok in checks.items():
            status = "OK" if ok else "FAIL"
            logger.info("  %s: %s = %s", status, field, ev.get(field))

    await agent.stop()
    return validated


async def main():
    """Uruchamia wszystkie testy."""
    logger.info("=" * 70)
    logger.info("BundespolizeiAgent — Test Suite (dry run)")
    logger.info("=" * 70)

    # Test 1: Fetch
    html = await test_fetch()
    if not html:
        logger.error("Test 1 FAIL — przerywam")
        sys.exit(1)

    logger.info("")

    # Test 2: Parse
    events = await test_parse(html)
    if events is False:
        logger.error("Test 2 FAIL — przerywam")
        sys.exit(1)

    logger.info("")

    # Test 3: Validate
    if events:
        await test_validate(events)
        logger.info("")

        # Test 4: Pipeline dry run
        await test_pipeline(events)
    else:
        logger.info("Pomijam testy 3-4 — brak eventow (nie jest to blad)")

    logger.info("")
    logger.info("=" * 70)
    logger.info("WSZYSTKIE TESTY ZAKONCZONE POMYSLNIE")
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
