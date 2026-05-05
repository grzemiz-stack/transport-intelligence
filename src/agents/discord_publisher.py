"""Discord Publisher — publishes T1/T2 events to Cargo Watch Europe server.

Stateless connect-send-disconnect pattern (no 24/7 connection needed).
Tracks published event IDs in a local JSON file to avoid re-posting.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import discord
import yaml

logger = logging.getLogger(__name__)

CHANNELS_PATH = Path(__file__).parent / "discord_channels.yaml"

# Country code → flag emoji
COUNTRY_FLAGS = {
    "PL": "\U0001f1f5\U0001f1f1",
    "DE": "\U0001f1e9\U0001f1ea",
    "FR": "\U0001f1eb\U0001f1f7",
    "NL": "\U0001f1f3\U0001f1f1",
    "IT": "\U0001f1ee\U0001f1f9",
    "ES": "\U0001f1ea\U0001f1f8",
    "GB": "\U0001f1ec\U0001f1e7",
    "AT": "\U0001f1e6\U0001f1f9",
    "CZ": "\U0001f1e8\U0001f1ff",
    "RO": "\U0001f1f7\U0001f1f4",
    "HU": "\U0001f1ed\U0001f1fa",
    "BE": "\U0001f1e7\U0001f1ea",
    "SE": "\U0001f1f8\U0001f1ea",
    "TR": "\U0001f1f9\U0001f1f7",
    "UA": "\U0001f1fa\U0001f1e6",
    "SK": "\U0001f1f8\U0001f1f0",
    "BG": "\U0001f1e7\U0001f1ec",
    "HR": "\U0001f1ed\U0001f1f7",
    "DK": "\U0001f1e9\U0001f1f0",
    "FI": "\U0001f1eb\U0001f1ee",
    "GR": "\U0001f1ec\U0001f1f7",
    "IE": "\U0001f1ee\U0001f1ea",
    "LT": "\U0001f1f1\U0001f1f9",
    "LV": "\U0001f1f1\U0001f1fb",
    "NO": "\U0001f1f3\U0001f1f4",
    "PT": "\U0001f1f5\U0001f1f9",
    "SI": "\U0001f1f8\U0001f1ee",
    "CH": "\U0001f1e8\U0001f1ed",
}

COUNTRY_NAMES = {
    "PL": "Poland", "DE": "Germany", "FR": "France", "NL": "Netherlands",
    "IT": "Italy", "ES": "Spain", "GB": "United Kingdom", "AT": "Austria",
    "CZ": "Czech Republic", "RO": "Romania", "HU": "Hungary", "BE": "Belgium",
    "SE": "Sweden", "TR": "Turkey", "UA": "Ukraine", "SK": "Slovakia",
    "BG": "Bulgaria", "HR": "Croatia", "DK": "Denmark", "FI": "Finland",
    "GR": "Greece", "IE": "Ireland", "LT": "Lithuania", "LV": "Latvia",
    "NO": "Norway", "PT": "Portugal", "SI": "Slovenia", "CH": "Switzerland",
}

EVENT_TYPE_LABELS = {
    "theft_cargo": "CARGO THEFT",
    "theft_fuel": "FUEL THEFT",
    "theft_vehicle": "VEHICLE THEFT",
    "bankruptcy": "BANKRUPTCY",
    "restructuring": "RESTRUCTURING",
    "payment_issue": "PAYMENT ISSUE",
    "license_revoked": "LICENSE REVOKED",
    "route_closure": "ROUTE CLOSURE",
    "strike": "STRIKE",
    "damage": "DAMAGE",
    "fraud": "FRAUD",
    "smuggling": "SMUGGLING",
    "accident": "ACCIDENT",
    "customs_alert": "CUSTOMS ALERT",
    "sanctions_violation": "SANCTIONS VIOLATION",
}

# event_type → category channel name
_TYPE_TO_CHANNEL = {
    "theft_cargo": "theft-alerts",
    "theft_fuel": "theft-alerts",
    "theft_vehicle": "theft-alerts",
    "bankruptcy": "company-warnings",
    "restructuring": "company-warnings",
    "payment_issue": "company-warnings",
    "license_revoked": "company-warnings",
    "route_closure": "road-warnings",
    "strike": "road-warnings",
}


def load_own_server_config() -> dict:
    """Load the own_server section from discord_channels.yaml."""
    with open(CHANNELS_PATH) as f:
        data = yaml.safe_load(f)
    return data.get("own_server", {})


class DiscordPublisher:
    """Publishes T1/T2 intelligence events to our Discord server."""

    def __init__(self, bot_token: str, server_config: dict):
        self.bot_token = bot_token
        self.server_config = server_config
        self.guild_id = int(server_config["guild_id"])
        self.max_posts_per_day = server_config.get("max_posts_per_day", 5)
        self.publish_tiers = server_config.get("publish_tiers", [1, 2])
        self._published_file = Path(__file__).parent / ".discord_published.json"

    def _load_published(self) -> dict:
        """Load published event IDs and metadata from JSON file."""
        if self._published_file.exists():
            try:
                return json.loads(self._published_file.read_text())
            except (json.JSONDecodeError, OSError):
                logger.warning("Corrupt published file, resetting")
        return {"event_ids": [], "last_publish": None, "daily_count": 0, "daily_date": None}

    def _save_published(self, data: dict):
        """Save published event IDs and metadata."""
        # Keep only last 500 event IDs to prevent unbounded growth
        if len(data.get("event_ids", [])) > 500:
            data["event_ids"] = data["event_ids"][-500:]
        self._published_file.write_text(json.dumps(data, default=str))

    def _format_event_message(self, event: dict) -> str:
        """Format an event into a Discord message string."""
        tier = event.get("intelligence_tier", 3)
        event_type = event.get("event_type", "unknown")
        country_code = event.get("country_code", "XX")
        label = EVENT_TYPE_LABELS.get(event_type, event_type.upper().replace("_", " "))
        flag = COUNTRY_FLAGS.get(country_code, "")
        country_name = COUNTRY_NAMES.get(country_code, country_code)

        if tier == 1:
            header = f"\U0001f6a8 **{label}** | {flag} {country_name}"
        else:
            header = f"\u26a0\ufe0f **{label}** | {flag} {country_name}"

        lines = [header, ""]

        # Location
        location = event.get("location_detail") or event.get("city") or event.get("region")
        if location:
            lines.append(f"\U0001f4cd {location}")

        # Date
        date_val = event.get("date_occurred") or event.get("date_collected")
        if date_val:
            if isinstance(date_val, str):
                try:
                    date_val = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    date_val = None
            if isinstance(date_val, datetime):
                lines.append(f"\U0001f4c5 {date_val.strftime('%d.%m.%Y %H:%M')}")

        # Description
        desc = event.get("translated_description") or event.get("description") or ""
        if desc:
            lines.append(f"\U0001f4dd {desc[:200]}")

        # Financial impact
        impact = event.get("financial_impact_eur")
        if impact:
            lines.append(f"\U0001f4b0 \u20ac{impact:,.0f}")

        # Modus operandi
        mo = event.get("modus_operandi")
        if mo:
            lines.append(f"\U0001f50d MO: {mo}")

        # Cargo type
        cargo = event.get("cargo_type")
        if cargo:
            lines.append(f"\U0001f4e6 Cargo: {cargo}")

        # Source
        source_name = event.get("source_name", "")
        if source_name:
            lines.append(f"\u26a0\ufe0f Source: {source_name}")

        return "\n".join(lines)

    def _get_target_channels(self, event: dict) -> list[str]:
        """Determine which Discord channels an event should be posted to."""
        channels = []
        event_type = event.get("event_type", "")
        country_code = (event.get("country_code") or "").upper()
        intelligence_category = event.get("intelligence_category") or ""

        # Category channel
        cat_channel = _TYPE_TO_CHANNEL.get(event_type)
        if cat_channel:
            channels.append(cat_channel)
        elif event_type == "damage" and intelligence_category in (
            "curtain_slashing", "dangerous_parking",
        ):
            channels.append("unsafe-parkings")
        elif not cat_channel:
            # Default: road-warnings for unknown types
            channels.append("road-warnings")

        # Country channel
        configured_channels = self.server_config.get("channels", {})
        country_channel = f"country-{country_code.lower()}"
        if country_channel in configured_channels:
            channels.append(country_channel)
        else:
            channels.append("country-other")

        return list(dict.fromkeys(channels))  # deduplicate, preserve order

    async def publish_events(self, dry_run: bool = False) -> int:
        """Publish unpublished T1/T2 events to Discord.

        Returns number of events published.
        """
        published_data = self._load_published()
        published_ids = set(published_data.get("event_ids", []))

        # Reset daily counter if new day
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if published_data.get("daily_date") != today:
            published_data["daily_count"] = 0
            published_data["daily_date"] = today

        remaining = self.max_posts_per_day - published_data.get("daily_count", 0)
        if remaining <= 0:
            logger.info("[discord_publish] Daily limit reached (%d), skipping",
                        self.max_posts_per_day)
            return 0

        # Query DB for unpublished T1/T2 events
        try:
            from sqlalchemy import select

            from src.db.models import Event, Source
            from src.db.postgres import async_session
        except ImportError as e:
            logger.error("[discord_publish] Import error: %s", e)
            return 0

        cutoff = datetime.utcnow() - timedelta(hours=24)
        events_to_publish = []

        async with async_session() as session:
            query = (
                select(Event, Source.name.label("source_name"))
                .outerjoin(Source, Event.source_id == Source.id)
                .where(
                    Event.intelligence_tier.in_(self.publish_tiers),
                    Event.date_collected >= cutoff,
                )
                .order_by(Event.intelligence_tier, Event.date_collected.desc())
                .limit(remaining)
            )
            result = await session.execute(query)
            rows = result.all()

            for row in rows:
                event = row[0]
                source_name = row[1] if len(row) > 1 else None
                eid = str(event.id)
                if eid in published_ids:
                    continue
                event_dict = {
                    "id": eid,
                    "event_type": event.event_type,
                    "intelligence_tier": event.intelligence_tier,
                    "intelligence_category": event.intelligence_category,
                    "country_code": event.country_code,
                    "region": event.region,
                    "city": event.city,
                    "location_detail": event.location_detail,
                    "date_occurred": event.date_occurred,
                    "date_collected": event.date_collected,
                    "description": event.description,
                    "translated_description": event.translated_description,
                    "financial_impact_eur": event.financial_impact_eur,
                    "modus_operandi": event.modus_operandi,
                    "cargo_type": event.cargo_type,
                    "source_name": source_name or "",
                    "title": event.title,
                }
                events_to_publish.append(event_dict)

        if not events_to_publish:
            logger.info("[discord_publish] No new events to publish")
            return 0

        if dry_run:
            for ev in events_to_publish:
                msg = self._format_event_message(ev)
                channels = self._get_target_channels(ev)
                logger.info("[discord_publish][DRY RUN] Would send to %s:\n%s",
                            channels, msg)
            return len(events_to_publish)

        # Connect bot, send messages, disconnect
        count = await self._send_events(events_to_publish)

        # Update published tracking
        for ev in events_to_publish[:count]:
            published_data["event_ids"].append(ev["id"])
        published_data["daily_count"] = published_data.get("daily_count", 0) + count
        published_data["last_publish"] = datetime.utcnow().isoformat()
        self._save_published(published_data)

        logger.info("[discord_publish] Published %d events", count)
        return count

    async def _send_events(self, events: list[dict]) -> int:
        """Connect to Discord, send event messages, disconnect. Returns count sent."""
        intents = discord.Intents.default()
        bot = discord.Client(intents=intents)
        sent_count = 0

        @bot.event
        async def on_ready():
            nonlocal sent_count
            try:
                guild = bot.get_guild(self.guild_id)
                if guild is None:
                    logger.error("[discord_publish] Guild %d not found", self.guild_id)
                    await bot.close()
                    return

                # Build channel name → channel object lookup
                channel_map: dict[str, discord.TextChannel] = {}
                for ch in guild.text_channels:
                    channel_map[ch.name] = ch

                for event_dict in events:
                    msg = self._format_event_message(event_dict)
                    target_channels = self._get_target_channels(event_dict)

                    for ch_name in target_channels:
                        channel = channel_map.get(ch_name)
                        if channel is None:
                            logger.warning("[discord_publish] Channel #%s not found in guild",
                                           ch_name)
                            continue
                        try:
                            await channel.send(msg)
                        except discord.Forbidden:
                            logger.error("[discord_publish] No permission to send to #%s",
                                         ch_name)
                        except discord.HTTPException as e:
                            logger.error("[discord_publish] HTTP error sending to #%s: %s",
                                         ch_name, e)

                    sent_count += 1

            except Exception as e:
                logger.error("[discord_publish] Error in on_ready: %s", e, exc_info=True)
            finally:
                await bot.close()

        try:
            await bot.start(self.bot_token)
        except discord.LoginFailure:
            logger.error("[discord_publish] Invalid bot token")
        except Exception as e:
            logger.error("[discord_publish] Bot error: %s", e)

        return sent_count

    async def publish_daily_summary(self, dry_run: bool = False) -> bool:
        """Post 24h summary to #general-chat. Returns True on success."""
        try:
            from sqlalchemy import func, select

            from src.db.models import Event
            from src.db.postgres import async_session
        except ImportError as e:
            logger.error("[discord_summary] Import error: %s", e)
            return False

        cutoff = datetime.utcnow() - timedelta(hours=24)

        async with async_session() as session:
            # Total events
            total_result = await session.execute(
                select(func.count(Event.id)).where(Event.date_collected >= cutoff)
            )
            total = total_result.scalar() or 0

            # By event type
            type_result = await session.execute(
                select(Event.event_type, func.count(Event.id))
                .where(Event.date_collected >= cutoff)
                .group_by(Event.event_type)
            )
            type_counts = {row[0]: row[1] for row in type_result.all()}

            # By country (top 5)
            country_result = await session.execute(
                select(Event.country_code, func.count(Event.id))
                .where(Event.date_collected >= cutoff)
                .group_by(Event.country_code)
                .order_by(func.count(Event.id).desc())
                .limit(5)
            )
            top_countries = country_result.all()

            # By tier
            tier_result = await session.execute(
                select(Event.intelligence_tier, func.count(Event.id))
                .where(
                    Event.date_collected >= cutoff,
                    Event.intelligence_tier.isnot(None),
                )
                .group_by(Event.intelligence_tier)
            )
            tier_counts = {row[0]: row[1] for row in tier_result.all()}

        # Count thefts
        theft_count = sum(
            type_counts.get(t, 0)
            for t in ("theft_cargo", "theft_fuel", "theft_vehicle")
        )

        t1 = tier_counts.get(1, 0)
        t2 = tier_counts.get(2, 0)

        # Top countries line
        country_parts = []
        for code, cnt in top_countries:
            flag = COUNTRY_FLAGS.get(code, "")
            country_parts.append(f"{flag} {code} ({cnt})")
        top_line = ", ".join(country_parts) if country_parts else "none"

        summary = (
            f"\U0001f4ca **24h Summary** | New events: {total} "
            f"| Thefts: {theft_count} | Alerts: {t1 + t2}\n"
            f"\U0001f51d Top countries: {top_line}\n"
            f"\U0001f6a8 T1 events: {t1} | \u26a0\ufe0f T2 events: {t2}"
        )

        if dry_run:
            logger.info("[discord_summary][DRY RUN] Would send to #general-chat:\n%s", summary)
            return True

        # Send to #general-chat
        intents = discord.Intents.default()
        bot = discord.Client(intents=intents)
        success = False

        @bot.event
        async def on_ready():
            nonlocal success
            try:
                guild = bot.get_guild(self.guild_id)
                if guild is None:
                    logger.error("[discord_summary] Guild %d not found", self.guild_id)
                    await bot.close()
                    return

                summary_channel_name = self.server_config.get(
                    "summary_channel", "general-chat"
                )
                channel = discord.utils.get(
                    guild.text_channels, name=summary_channel_name
                )
                if channel is None:
                    logger.error(
                        "[discord_summary] #%s not found", summary_channel_name
                    )
                    await bot.close()
                    return

                await channel.send(summary)
                success = True
                logger.info("[discord_summary] Daily summary posted to #general-chat")
            except Exception as e:
                logger.error("[discord_summary] Error: %s", e, exc_info=True)
            finally:
                await bot.close()

        try:
            await bot.start(self.bot_token)
        except discord.LoginFailure:
            logger.error("[discord_summary] Invalid bot token")
        except Exception as e:
            logger.error("[discord_summary] Bot error: %s", e)

        return success
