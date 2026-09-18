"""EventTranslator — tlumaczenie eventow na polski za pomoca Claude API.

Uzywa httpx do komunikacji z Anthropic Messages API.
Cache in-memory (hash tekstu -> tlumaczenie).
Rate limiting: max 10 requestow/min.
"""

import hashlib
import logging

from src.config import settings
from src.utils.claude_client import ClaudeClient

logger = logging.getLogger(__name__)


class EventTranslator:
    """Tlumaczy eventy transportowe na jezyk polski."""

    SYSTEM_PROMPT = (
        "Jestes tlumaczem specjalizujacym sie w terminologii transportowej, "
        "logistycznej i spedycyjnej. Przetlumacz podany tekst na jezyk polski. "
        "Zachowaj nazwy wlasne (firmy, miejscowosci, drogi) bez zmian. "
        "Zachowaj terminologie branzy transportowej: "
        "cargo, fracht, spedycja, CMR, ADR, TIR, kabotaz, itp. "
        "Odpowiedz TYLKO przetlumaczonym tekstem, bez dodatkowych komentarzy."
    )

    def __init__(self):
        self._cache: dict[str, str] = {}
        self._claude = ClaudeClient(
            api_key=settings.anthropic_api_key,
            max_requests_per_minute=10,
            timeout=30.0,
        )

    def _text_hash(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    async def translate_to_polish(self, text: str, source_language: str = "") -> str:
        """Translate text to Polish using Claude API.

        Args:
            text: Text to translate.
            source_language: ISO language code of the source text.

        Returns:
            Translated text in Polish, or original with language prefix on failure.
        """
        if not text or not text.strip():
            return text

        # Already Polish
        if source_language == "pl":
            return text

        # Check cache
        h = self._text_hash(text)
        if h in self._cache:
            return self._cache[h]

        user_prompt = f"Przetlumacz na polski (zrodlo: {source_language}):\n\n{text}"
        translated = await self._claude.call(
            user_prompt, self.SYSTEM_PROMPT, max_tokens=1024,
        )

        if translated is None:
            return f"[{source_language}] {text}" if source_language else text

        self._cache[h] = translated
        return translated

    async def translate_event(self, event: dict) -> dict:
        """Translate event title and description to Polish.

        Saves originals in original_title/original_description.
        Sets translated=True flag.
        """
        lang = event.get("language", "")
        if lang == "pl":
            return event

        # Save originals
        event["original_title"] = event.get("title", "")
        event["original_description"] = event.get("description", "")

        # Translate title
        title = event.get("title", "")
        if title:
            event["translated_title"] = await self.translate_to_polish(title, lang)

        # Translate description
        desc = event.get("description", "")
        if desc:
            event["translated_description"] = await self.translate_to_polish(desc, lang)

        event["translated"] = True
        return event
