"""Telegram Discovery Agent — automatycznie wyszukuje nowe grupy/kanaly kierowcow.

Uzywa Telethon SearchRequest do wyszukiwania kanalow w 25+ jezykach.
Auto-dodaje publiczne kanaly do telegram_channels.yaml.
Prywatne kanaly zapisuje do reports/output/telegram_discovery.txt.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

import yaml
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import Channel, Chat

from src.agents.telegram_agent import SESSION_DIR

logger = logging.getLogger(__name__)

CHANNELS_PATH = Path(__file__).parent / "telegram_channels.yaml"
DISCOVERY_REPORT_PATH = Path(__file__).parent.parent.parent / "reports" / "output" / "telegram_discovery.txt"

# Minimum participants to consider a channel relevant
MIN_PARTICIPANTS = 50

# Search queries in 25+ languages targeting trucker/freight groups
SEARCH_QUERIES = {
    "en": ["truck drivers group", "cargo theft Europe", "trucker chat", "freight transport group"],
    "pl": ["kierowcy ciezarowek", "transport miedzynarodowy", "kradzież ładunku", "spedycja grupa"],
    "de": ["LKW Fahrer Gruppe", "Frachtdiebstahl", "Spedition Telegram", "Trucker Deutschland"],
    "fr": ["chauffeurs routiers", "vol de fret", "transport routier groupe"],
    "es": ["camioneros grupo", "robo de carga", "transporte carretera"],
    "it": ["camionisti gruppo", "furto carico", "trasporto merci"],
    "nl": ["vrachtwagenchauffeurs", "vrachtdiefstal", "transport groep"],
    "ro": ["soferi camion", "furt marfa", "transport romania"],
    "cs": ["ridici kamionu", "kradez nakladu", "doprava skupina"],
    "hu": ["kamionsofőrök", "rakománylopás", "fuvarozás csoport"],
    "sk": ["vodici kamiónov", "kradez nakladu", "doprava skupina"],
    "bg": ["шофьори камиони", "кражба товар", "транспорт група"],
    "hr": ["vozači kamiona", "krađa tereta", "transport grupa"],
    "sl": ["vozniki tovornjakov", "kraja tovora", "transport skupina"],
    "lt": ["vairuotojai sunkvežimių", "krovinių vagystė", "transportas grupė"],
    "lv": ["kravas automašīnu vadītāji", "kravu zādzība", "transports grupa"],
    "et": ["veoautojuhid", "kaubavargus", "transport grupp"],
    "ru": ["дальнобойщики", "кража груза Европа", "перевозки группа", "дальнобой Европа"],
    "uk": ["далекобійники", "крадіжка вантажу", "перевезення група"],
    "tr": ["kamyon şoförleri", "yük hırsızlığı", "nakliye grubu"],
    "sv": ["lastbilschaufförer", "laststöld", "transport grupp"],
    "da": ["lastbilchauffører", "fragttyveri", "transport gruppe"],
    "fi": ["rekkakuskit", "rahtivarkaus", "kuljetus ryhmä"],
    "pt": ["caminhoneiros", "roubo de carga", "transporte grupo"],
    "el": ["οδηγοί φορτηγών", "κλοπή φορτίου", "μεταφορές ομάδα"],
    "sr": ["возачи камиона", "крађа терета", "транспорт група"],
}


class TelegramDiscoveryAgent:
    """Wyszukuje nowe grupy/kanaly Telegram zwiazane z transportem."""

    def __init__(
        self,
        api_id: int | str,
        api_hash: str,
        session_name: str = "ti_session",
    ):
        self.api_id = int(api_id)
        self.api_hash = api_hash
        session_path = SESSION_DIR / session_name
        self.client = TelegramClient(str(session_path), self.api_id, self.api_hash)
        self._existing_channels: set[str] = set()
        self._discovered_public: list[dict] = []
        self._discovered_private: list[dict] = []

    async def connect(self):
        """Connect to Telegram."""
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise RuntimeError(
                "Telegram session not authorized. "
                "Run 'python -m src.agents.telegram_setup' first."
            )
        me = await self.client.get_me()
        logger.info("Discovery agent connected as: %s (id=%d)", me.first_name, me.id)

    async def disconnect(self):
        await self.client.disconnect()

    def _load_existing_channels(self) -> set[str]:
        """Load existing channel usernames from telegram_channels.yaml."""
        from src.agents.telegram_runner import load_channels, get_channels_flat

        try:
            all_ch = load_channels()
            flat = get_channels_flat(all_ch)
            return {ch["channel"].lower() for ch in flat}
        except Exception as e:
            logger.warning("Cannot load existing channels: %s", e)
            return set()

    async def discover_channels(self) -> dict:
        """Search for new trucker/freight Telegram groups using multilingual queries.

        Returns:
            dict with 'auto_added' and 'manual_review' counts.
        """
        self._existing_channels = self._load_existing_channels()
        logger.info("Existing channels: %d", len(self._existing_channels))

        total_queries = sum(len(v) for v in SEARCH_QUERIES.values())
        query_num = 0

        for lang, queries in SEARCH_QUERIES.items():
            for query in queries:
                query_num += 1
                logger.info("[%d/%d] Searching: '%s' (%s)", query_num, total_queries, query, lang)

                try:
                    result = await self.client(SearchRequest(q=query, limit=20))
                except FloodWaitError as e:
                    logger.warning("Flood wait %ds — sleeping...", e.seconds)
                    await asyncio.sleep(e.seconds + 1)
                    continue
                except Exception as e:
                    logger.error("Search error for '%s': %s", query, e)
                    continue

                for entity in (result.chats or []):
                    await self._process_entity(entity, lang)

                # Rate limit between searches
                await asyncio.sleep(3)

        # Save results
        auto_added = self._save_to_yaml()
        manual_saved = self._save_private_report()

        logger.info(
            "Discovery complete: %d auto-added, %d manual review",
            auto_added, manual_saved,
        )
        return {"auto_added": auto_added, "manual_review": manual_saved}

    async def discover_similar(self, channel_username: str) -> dict:
        """Find channels similar to a given channel using recommendations.

        Returns:
            dict with 'auto_added' and 'manual_review' counts.
        """
        self._existing_channels = self._load_existing_channels()

        try:
            entity = await self.client.get_entity(channel_username)
        except Exception as e:
            logger.error("Cannot resolve '%s': %s", channel_username, e)
            return {"auto_added": 0, "manual_review": 0}

        if not isinstance(entity, Channel):
            logger.warning("'%s' is not a channel — skipping similar search", channel_username)
            return {"auto_added": 0, "manual_review": 0}

        # Try GetChannelRecommendationsRequest if available
        try:
            from telethon.tl.functions.channels import GetChannelRecommendationsRequest
            result = await self.client(GetChannelRecommendationsRequest(channel=entity))
            for chat in (result.chats or []):
                await self._process_entity(chat, "en")
        except (ImportError, AttributeError):
            logger.info("GetChannelRecommendationsRequest not available in this Telethon version")
        except Exception as e:
            logger.warning("Similar channel lookup failed: %s", e)

        auto_added = self._save_to_yaml()
        manual_saved = self._save_private_report()

        return {"auto_added": auto_added, "manual_review": manual_saved}

    async def _process_entity(self, entity, language: str):
        """Check if entity is a relevant channel/group and categorize it."""
        if not isinstance(entity, (Channel, Chat)):
            return

        username = getattr(entity, "username", None)
        title = getattr(entity, "title", "")
        participants_count = getattr(entity, "participants_count", 0) or 0

        # Get participants count from full info if not available
        if participants_count == 0 and isinstance(entity, Channel) and username:
            try:
                full = await self.client(GetFullChannelRequest(channel=entity))
                participants_count = getattr(full.full_chat, "participants_count", 0) or 0
            except Exception:
                pass

        # Filter by minimum participants
        if participants_count < MIN_PARTICIPANTS:
            return

        # Check for duplicates
        if username and username.lower() in self._existing_channels:
            return
        # Also check against already-discovered in this session
        already_found = {d["username"].lower() for d in self._discovered_public if d.get("username")}
        already_found |= {d.get("title", "").lower() for d in self._discovered_private}
        if username and username.lower() in already_found:
            return
        if not username and title.lower() in already_found:
            return

        info = {
            "title": title,
            "username": username or "",
            "participants": participants_count,
            "language": language,
            "discovered_at": datetime.utcnow().isoformat(),
        }

        if username:
            self._discovered_public.append(info)
            logger.info("AUTO-ADDED: @%s (%s) — %d participants", username, title, participants_count)
        else:
            self._discovered_private.append(info)
            logger.info("MANUAL: '%s' (private) — %d participants", title, participants_count)

    def _save_to_yaml(self) -> int:
        """Append discovered public channels to telegram_channels.yaml under 'discovered:' section."""
        if not self._discovered_public:
            return 0

        try:
            with open(CHANNELS_PATH) as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            data = {}

        # Load existing discovered channels for dedup
        existing_discovered = set()
        if "discovered" in data:
            for ch in data["discovered"]:
                existing_discovered.add(ch.get("channel", "").lower())

        new_entries = []
        for ch in self._discovered_public:
            if ch["username"].lower() in existing_discovered:
                continue
            if ch["username"].lower() in self._existing_channels:
                continue
            new_entries.append({
                "name": ch["title"],
                "channel": ch["username"],
                "language": ch["language"],
                "priority": "medium",
                "discovered_at": ch["discovered_at"],
            })
            existing_discovered.add(ch["username"].lower())

        if not new_entries:
            return 0

        if "discovered" not in data:
            data["discovered"] = []
        data["discovered"].extend(new_entries)

        with open(CHANNELS_PATH, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        logger.info("Saved %d new channels to %s", len(new_entries), CHANNELS_PATH)
        return len(new_entries)

    def _save_private_report(self) -> int:
        """Append discovered private channels to discovery report file."""
        if not self._discovered_private:
            return 0

        DISCOVERY_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(DISCOVERY_REPORT_PATH, "a") as f:
            f.write(f"\n# Discovery run: {datetime.utcnow().isoformat()}\n")
            for ch in self._discovered_private:
                f.write(
                    f"- {ch['title']} | {ch['participants']} members | "
                    f"lang={ch['language']} | private (no username)\n"
                )

        logger.info("Saved %d private channels to %s", len(self._discovered_private), DISCOVERY_REPORT_PATH)
        return len(self._discovered_private)

    async def send_discovery_report(self):
        """Send email notification about discovered channels."""
        if not self._discovered_public and not self._discovered_private:
            return

        try:
            from src.notifications.email_sender import EmailSender

            sender = EmailSender()
            subject = "[TI] Nowe grupy Telegram znalezione"

            lines = [f"Raport odkrywania grup Telegram — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"]

            if self._discovered_public:
                lines.append(f"\nAuto-dodane ({len(self._discovered_public)}):")
                for ch in self._discovered_public:
                    lines.append(
                        f"  @{ch['username']} — {ch['title']} "
                        f"({ch['participants']} members, {ch['language']})"
                    )

            if self._discovered_private:
                lines.append(f"\nDo recznej weryfikacji ({len(self._discovered_private)}):")
                for ch in self._discovered_private:
                    lines.append(
                        f"  {ch['title']} ({ch['participants']} members, "
                        f"{ch['language']}) — prywatna"
                    )

            body = "\n".join(lines)
            await sender.send_raw_email(subject=subject, body_text=body)
            logger.info("Discovery report email sent")
        except Exception as e:
            logger.warning("Failed to send discovery report email: %s", e)
