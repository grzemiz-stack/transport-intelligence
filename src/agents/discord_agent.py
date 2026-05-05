"""Discord Monitor — monitors trucking Discord servers for transport intelligence.

Uses discord.py to:
- Listen for new messages in configured servers/channels (real-time)
- Dual-stream routing: TI (transport intelligence → DB) and CC (cargo control → JSONL)
- GDPR: anonymize usernames via hash
"""

import hashlib
import logging
import re
import time
from datetime import datetime

import discord

from src.agents.road_alerts_keywords import is_road_alert
from src.agents.transport_keywords import is_transport_related

logger = logging.getLogger(__name__)

# PII patterns for anonymization (same as Telegram agent)
_PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{8,15}")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_USERNAME_RE = re.compile(r"@[a-zA-Z0-9_]{3,32}")


def anonymize_discord_text(text: str) -> str:
    """Remove PII from Discord message text (GDPR compliance)."""
    if not text:
        return ""
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _EMAIL_RE.sub("[EMAIL]", text)
    # Discord mentions like <@123456789>
    text = re.sub(r"<@!?\d+>", "[USER]", text)
    text = _USERNAME_RE.sub("[USER]", text)
    return text


def anonymize_discord_user(user: discord.User | discord.Member) -> str:
    """Return anonymized user identifier (GDPR)."""
    if user is None:
        return "anonymous"
    user_hash = hashlib.sha256(str(user.id).encode()).hexdigest()[:10]
    return f"discord_user:{user_hash}"


class DiscordMonitor:
    """Monitors Discord trucking servers for transport & road alert messages."""

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = discord.Client(intents=intents)
        self._rate_limits: dict[int, float] = {}  # guild_id → last_save_ts

    async def connect(self):
        """Start the bot (blocking)."""
        await self.bot.start(self.bot_token)

    async def close(self):
        """Close the bot connection."""
        await self.bot.close()

    def setup_handler(self, channels_config: list[dict], callback):
        """Register on_message handler with dual-stream routing.

        Args:
            channels_config: List of dicts with guild_id, channels, language, etc.
            callback: Async function(event_dict) called for matching messages.
        """
        # Build lookup: guild_id → config
        guild_lookup: dict[str, dict] = {}
        for cfg in channels_config:
            gid = cfg.get("guild_id", "")
            if gid:
                guild_lookup[gid] = cfg

        # Build set of monitored channel names per guild
        guild_channels: dict[str, set[str]] = {}
        for cfg in channels_config:
            gid = cfg.get("guild_id", "")
            if gid:
                guild_channels[gid] = set(
                    ch.lower() for ch in cfg.get("channels", [])
                )

        @self.bot.event
        async def on_ready():
            logger.info("Discord bot connected as %s", self.bot.user)
            logger.info("Monitoring %d guild configs", len(guild_lookup))

        @self.bot.event
        async def on_message(message: discord.Message):
            # Skip bot messages
            if message.author.bot:
                return

            if not message.content:
                return

            guild = message.guild
            if guild is None:
                return  # DMs not monitored

            guild_id_str = str(guild.id)

            # Check if guild is monitored
            cfg = guild_lookup.get(guild_id_str)
            if cfg is None:
                return

            # Check if channel is monitored
            monitored = guild_channels.get(guild_id_str, set())
            channel_name = message.channel.name.lower() if message.channel else ""
            if monitored and channel_name not in monitored:
                return

            # Rate limit: 1 msg/s per guild
            now = time.time()
            last_ts = self._rate_limits.get(guild.id, 0)
            if now - last_ts < 1.0:
                return
            self._rate_limits[guild.id] = now

            language = cfg.get("language", "en")
            text = message.content

            # Dual-stream classification
            is_ti = is_transport_related(text, language)
            is_cc = is_road_alert(text, language)
            if not is_ti and not is_cc:
                return

            # Anonymize (GDPR)
            anon_text = anonymize_discord_text(text)
            sender = anonymize_discord_user(message.author)

            # Build event dict (compatible with Telegram event format)
            msg_date = message.created_at.replace(tzinfo=None)
            date_iso = msg_date.isoformat()

            event = {
                "title": anon_text[:200] if anon_text else "Discord message",
                "description": anon_text[:3000],
                "source_url": message.jump_url,
                "raw_text": anon_text[:5000],
                "date": date_iso,
                "timestamp": date_iso,
                "date_parsed": msg_date,
                "collected_at": datetime.utcnow().isoformat(),
                "source_name": f"Discord/{guild.name}/{channel_name}",
                "source_type": "discord",
                "country_code": cfg.get("country_code", "XX"),
                "language": language,
                "trust_score": 0.2,
                "is_official": False,
                "is_anonymized": True,
                "discord_guild": guild_id_str,
                "discord_channel": channel_name,
                "discord_msg_id": message.id,
                "sender": sender,
                "_stream_ti": is_ti,
                "_stream_cc": is_cc,
            }

            logger.info(
                "Discord: [%s/#%s] %s (ti=%s, cc=%s)",
                guild.name, channel_name, event["title"][:60], is_ti, is_cc,
            )

            try:
                await callback(event)
            except Exception as e:
                logger.error("Callback error: %s", e)
