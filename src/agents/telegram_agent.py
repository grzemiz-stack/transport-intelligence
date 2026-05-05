"""Telegram Monitor — monitoruje publiczne grupy i kanaly kierowcow/spedytorow.

Uzywa Telethon (Python Telegram client) do:
- Pobierania ostatnich wiadomosci z grup/kanalow (scan mode)
- Nasluchiwania na nowe wiadomosci w real-time (listen mode)

Filtruje przez dual-list is_transport_related() z transport_keywords.py.
Anonimizuje usernames i phone numbers (GDPR).

Wymaga jednorazowego setup (telegram_setup.py) z kodem weryfikacyjnym.
"""

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from telethon import TelegramClient, events
from telethon.errors import (
    ChannelInvalidError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    FloodWaitError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl.types import Channel, Chat, User

from src.agents.road_alerts_keywords import is_road_alert
from src.agents.transport_keywords import has_event_keyword, is_transport_related

logger = logging.getLogger(__name__)

# Where session files are stored
SESSION_DIR = Path(__file__).parent.parent.parent  # project root

# PII patterns for anonymization
_PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{8,15}")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_USERNAME_RE = re.compile(r"@[a-zA-Z0-9_]{3,32}")


def anonymize_telegram_text(text: str) -> str:
    """Remove PII from Telegram message text (GDPR compliance)."""
    if not text:
        return ""
    text = _PHONE_RE.sub("[PHONE]", text)
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _USERNAME_RE.sub("[USER]", text)
    return text


def anonymize_sender(sender) -> str:
    """Return anonymized sender identifier."""
    if sender is None:
        return "anonymous"
    if isinstance(sender, Channel):
        # Channel posts — channel name is public, OK to keep
        return f"channel:{sender.title or sender.username or 'unknown'}"
    if isinstance(sender, User):
        # User — anonymize to ID hash
        return f"user:{hash(sender.id) % 100000:05d}"
    if isinstance(sender, Chat):
        return f"group:{sender.title or 'unknown'}"
    return "unknown"


class TelegramMonitor:
    """Monitoruje publiczne grupy/kanaly Telegram pod katem transportu."""

    def __init__(
        self,
        api_id: int | str,
        api_hash: str,
        session_name: str = "ti_session",
    ):
        self.api_id = int(api_id)
        self.api_hash = api_hash
        self.session_name = session_name
        session_path = SESSION_DIR / session_name
        self.client = TelegramClient(str(session_path), self.api_id, self.api_hash)
        self._seen_ids: set[int] = set()

    async def connect(self):
        """Connect to Telegram. Session file must exist (run telegram_setup.py first)."""
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise RuntimeError(
                "Telegram session not authorized. "
                "Run 'python -m src.agents.telegram_setup' first to create session."
            )
        me = await self.client.get_me()
        logger.info("Telegram connected as: %s (id=%d)", me.first_name, me.id)

    async def disconnect(self):
        """Disconnect from Telegram."""
        await self.client.disconnect()

    async def resolve_channel(self, channel_id: str) -> object | None:
        """Try to resolve a channel/group by username or ID. Returns entity or None."""
        try:
            entity = await self.client.get_entity(channel_id)
            logger.info("Resolved channel: %s -> %s", channel_id, getattr(entity, 'title', channel_id))
            return entity
        except (
            UsernameInvalidError,
            UsernameNotOccupiedError,
            ChannelInvalidError,
            ChannelPrivateError,
            ChatAdminRequiredError,
            ValueError,
        ) as e:
            logger.warning("Cannot resolve channel '%s': %s", channel_id, e)
            return None

    async def fetch_recent_messages(
        self,
        channel_id: str,
        language: str,
        limit: int = 100,
        trusted_transport: bool = False,
    ) -> list[dict]:
        """Fetch recent messages from a channel/group, filtered by transport keywords.

        Args:
            channel_id: Telegram username or ID of the channel/group.
            language: Language code for keyword matching.
            limit: Max messages to fetch.
            trusted_transport: If True, relax dual-list filter to single-list match
                (vehicle OR event keyword) for channels known to be transport-related.

        Returns:
            List of transport-related event dicts.
        """
        entity = await self.resolve_channel(channel_id)
        if entity is None:
            return []

        channel_title = getattr(entity, 'title', channel_id)
        events_list = []

        try:
            async for message in self.client.iter_messages(entity, limit=limit):
                if not message.text:
                    continue

                # Dedup by message ID
                if message.id in self._seen_ids:
                    continue
                self._seen_ids.add(message.id)

                # Dual-stream keyword filtering
                is_ti = is_transport_related(message.text, language)
                # For trusted transport channels, also accept single-list event keyword match
                if not is_ti and trusted_transport:
                    is_ti = has_event_keyword(message.text, language)
                is_cc = is_road_alert(message.text, language)
                if not is_ti and not is_cc:
                    continue

                # Build event with stream routing flags
                event = self._message_to_event(message, channel_id, channel_title, language)
                event["_stream_ti"] = is_ti
                event["_stream_cc"] = is_cc
                events_list.append(event)

        except FloodWaitError as e:
            logger.warning("Flood wait %ds for channel '%s'", e.seconds, channel_id)
        except (ChannelPrivateError, ChatAdminRequiredError) as e:
            logger.warning("Access denied for '%s': %s", channel_id, e)
        except Exception as e:
            logger.error("Error fetching from '%s': %s", channel_id, e)

        logger.info(
            "Channel '%s': fetched %d messages, %d transport-related",
            channel_title, limit, len(events_list),
        )
        return events_list

    def _message_to_event(
        self,
        message,
        channel_id: str,
        channel_title: str,
        language: str,
    ) -> dict:
        """Convert a Telegram message to a transport event dict."""
        # Anonymize text and sender (GDPR)
        raw_text = message.text or ""
        anon_text = anonymize_telegram_text(raw_text)
        sender_label = anonymize_sender(message.sender)

        # Message date
        msg_date = message.date
        if msg_date and msg_date.tzinfo is not None:
            msg_date = msg_date.replace(tzinfo=None)
        date_iso = msg_date.isoformat() if msg_date else datetime.utcnow().isoformat()

        # Build source URL (link to the message if public channel)
        source_url = f"https://t.me/{channel_id}/{message.id}"

        return {
            "title": anon_text[:200] if anon_text else "Telegram message",
            "description": anon_text[:3000],
            "source_url": source_url,
            "raw_text": anon_text[:5000],
            "date": date_iso,
            "timestamp": date_iso,
            "date_parsed": msg_date,
            "collected_at": datetime.utcnow().isoformat(),
            "source_name": f"Telegram/{channel_title}",
            "source_type": "telegram",
            "country_code": "XX",  # will be overridden by channel config
            "language": language,
            "trust_score": 0.3,
            "is_official": False,
            "is_anonymized": True,
            "telegram_channel": channel_id,
            "telegram_msg_id": message.id,
            "sender": sender_label,
        }

    def create_realtime_handler(self, channels_config: list[dict], callback):
        """Create a real-time message handler for specified channels.

        Args:
            channels_config: List of channel config dicts with 'channel' and 'language' keys.
            callback: Async function(event_dict) called for each transport-related message.
        """
        # Build language lookup
        channel_lang = {}
        channel_titles = {}
        for cfg in channels_config:
            channel_lang[cfg["channel"]] = cfg.get("language", "en")
            channel_titles[cfg["channel"]] = cfg.get("name", cfg["channel"])

        @self.client.on(events.NewMessage)
        async def handler(event):
            if not event.message or not event.message.text:
                return

            # Determine channel
            chat = await event.get_chat()
            chat_username = getattr(chat, 'username', None) or str(chat.id)

            # Check if this channel is in our monitored list
            language = channel_lang.get(chat_username)
            if language is None:
                # Try matching by title
                chat_title = getattr(chat, 'title', '')
                for cfg in channels_config:
                    if cfg["channel"] == chat_username or cfg.get("name") == chat_title:
                        language = cfg.get("language", "en")
                        break
            if language is None:
                return  # Not a monitored channel

            # Dual-stream keyword filtering
            is_ti = is_transport_related(event.message.text, language)
            is_cc = is_road_alert(event.message.text, language)
            if not is_ti and not is_cc:
                return

            # Build event with stream routing flags
            channel_title = channel_titles.get(chat_username, chat_username)
            ev = self._message_to_event(
                event.message, chat_username, channel_title, language,
            )
            ev["_stream_ti"] = is_ti
            ev["_stream_cc"] = is_cc

            # Override country from config
            for cfg in channels_config:
                if cfg["channel"] == chat_username:
                    ev["country_code"] = cfg.get("country_code", "XX")
                    break

            logger.info(
                "Real-time: [%s] %s",
                channel_title, ev["title"][:80],
            )

            try:
                await callback(ev)
            except Exception as e:
                logger.error("Callback error: %s", e)

        return handler
