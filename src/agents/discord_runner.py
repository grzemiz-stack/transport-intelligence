"""Discord Runner — runs DiscordMonitor in listen mode.

Usage:
    python -m src.agents.discord_runner --listen
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("discord_runner")

CHANNELS_PATH = Path(__file__).parent / "discord_channels.yaml"


def _load_env():
    """Load .env file if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass


def load_discord_channels() -> list[dict]:
    """Load Discord channel configs from YAML."""
    if not CHANNELS_PATH.exists():
        logger.error("Discord channels file not found: %s", CHANNELS_PATH)
        sys.exit(1)
    with open(CHANNELS_PATH) as f:
        data = yaml.safe_load(f)
    servers = data.get("trucking_servers", [])
    # Filter out servers without guild_id
    active = [s for s in servers if s.get("guild_id")]
    if not active:
        logger.warning("No Discord servers with guild_id configured in %s", CHANNELS_PATH)
    return active


async def listen():
    """Listen for new messages in real-time (24/7 mode)."""
    _load_env()

    bot_token = os.environ.get("DISCORD_BOT_TOKEN")
    if not bot_token:
        logger.error("DISCORD_BOT_TOKEN must be set in .env")
        sys.exit(1)

    from src.agents.discord_agent import DiscordMonitor
    from src.agents.road_alerts_writer import save_road_alert
    from src.agents.telegram_runner import _create_pipeline, _run_pipeline, _save_events_to_db

    channels = load_discord_channels()
    if not channels:
        logger.error("No active Discord servers configured")
        return

    monitor = DiscordMonitor(bot_token)
    pipeline = _create_pipeline()

    async def on_discord_message(event_dict: dict):
        """Process a Discord message through the pipeline with dual-stream routing."""
        out = _run_pipeline(event_dict, pipeline)
        if out is None:
            return

        is_ti = event_dict.get("_stream_ti", False)
        is_cc = event_dict.get("_stream_cc", False)

        if is_cc:
            ch_cfg = {
                "name": event_dict.get("source_name", "unknown"),
                "country_code": event_dict.get("country_code", "XX"),
            }
            save_road_alert(out, ch_cfg)
            logger.info("Road alert saved: %s", out.get("title", "?")[:80])

        if is_ti:
            ch_cfg = {
                "name": event_dict.get("discord_channel", "unknown"),
                "channel": f"discord/{event_dict.get('discord_guild', '')}",
                "country_code": event_dict.get("country_code", "XX"),
                "language": event_dict.get("language", "en"),
            }
            saved = await _save_events_to_db([out], ch_cfg)
            if saved > 0:
                logger.info("Saved Discord event to DB: %s", out.get("title", "?")[:80])

    monitor.setup_handler(channels, on_discord_message)

    logger.info("=" * 70)
    logger.info("Discord Listen: %d server configs loaded", len(channels))
    logger.info("=" * 70)
    logger.info("Listening for Discord messages... (Ctrl+C to stop)")

    try:
        await monitor.connect()
    except KeyboardInterrupt:
        logger.info("Stopping Discord listener...")
    finally:
        await monitor.close()


def main():
    parser = argparse.ArgumentParser(description="Transport Intelligence Discord Runner")
    parser.add_argument("--listen", action="store_true",
                        help="Listen for new messages in real-time (24/7)")
    args = parser.parse_args()

    if not args.listen:
        parser.print_help()
        sys.exit(1)

    asyncio.run(listen())


if __name__ == "__main__":
    main()
