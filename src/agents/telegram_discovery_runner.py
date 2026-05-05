"""Telegram Discovery Runner — CLI do wyszukiwania nowych grup Telegram.

Uzycie:
    python -m src.agents.telegram_discovery_runner --discover
    python -m src.agents.telegram_discovery_runner --similar truckers_of_europe3
    python -m src.agents.telegram_discovery_runner --full
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("telegram_discovery_runner")


def _load_env():
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass


async def run_discovery(discover: bool = False, similar: str | None = None, full: bool = False):
    """Run Telegram channel discovery."""
    _load_env()

    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    session_name = os.environ.get("TELEGRAM_DISCOVERY_SESSION", "ti_discovery_session")

    if not api_id or not api_hash:
        logger.error("TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env")
        sys.exit(1)

    from src.agents.telegram_discovery import TelegramDiscoveryAgent

    agent = TelegramDiscoveryAgent(api_id, api_hash, session_name)

    try:
        await agent.connect()
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)

    try:
        total_auto = 0
        total_manual = 0

        if discover or full:
            logger.info("=" * 70)
            logger.info("Starting channel discovery (multilingual search)")
            logger.info("=" * 70)
            result = await agent.discover_channels()
            total_auto += result["auto_added"]
            total_manual += result["manual_review"]

        if similar:
            logger.info("=" * 70)
            logger.info("Searching channels similar to: @%s", similar)
            logger.info("=" * 70)
            result = await agent.discover_similar(similar)
            total_auto += result["auto_added"]
            total_manual += result["manual_review"]

        if full:
            # Also run similar-channel search for each existing channel
            from src.agents.telegram_runner import load_channels, get_channels_flat
            all_ch = load_channels()
            flat = get_channels_flat(all_ch)
            for ch_cfg in flat[:10]:  # Limit to first 10 to avoid rate limits
                logger.info("--- Similar to: @%s ---", ch_cfg["channel"])
                result = await agent.discover_similar(ch_cfg["channel"])
                total_auto += result["auto_added"]
                total_manual += result["manual_review"]
                await asyncio.sleep(5)

        # Send email report
        await agent.send_discovery_report()

        logger.info("=" * 70)
        logger.info("DISCOVERY COMPLETE: %d auto-added, %d manual review", total_auto, total_manual)
        logger.info("=" * 70)

        # Update agent status
        try:
            from src.db.queries import update_agent_status
            await update_agent_status(
                country_code="EU",
                agent_type="telegram_discovery",
                events_count=total_auto + total_manual,
                errors_count=0,
            )
        except Exception as e:
            logger.debug("Could not update agent status: %s", e)

    finally:
        await agent.disconnect()


def main():
    parser = argparse.ArgumentParser(description="Transport Intelligence Telegram Discovery")
    parser.add_argument("--discover", action="store_true",
                        help="Search for new channels using multilingual queries")
    parser.add_argument("--similar", metavar="CHANNEL",
                        help="Find channels similar to CHANNEL username")
    parser.add_argument("--full", action="store_true",
                        help="Full discovery: search + similar for all existing channels")
    args = parser.parse_args()

    if not args.discover and not args.similar and not args.full:
        parser.print_help()
        sys.exit(1)

    asyncio.run(run_discovery(
        discover=args.discover,
        similar=args.similar,
        full=args.full,
    ))


if __name__ == "__main__":
    main()
