"""EventTranslator — tlumaczenie eventow na polski za pomoca Claude API.

Uzywa httpx do komunikacji z Anthropic Messages API.
Cache in-memory (hash tekstu -> tlumaczenie).
Rate limiting: max 10 requestow/min.
"""

import hashlib
import logging
import time

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Rate limiting
_MAX_REQUESTS_PER_MINUTE = 10
_request_timestamps: list[float] = []


def _rate_limit_ok() -> bool:
    """Check if we can make another request (token bucket, 10/min)."""
    now = time.time()
    # Remove timestamps older than 60s
    while _request_timestamps and _request_timestamps[0] < now - 60:
        _request_timestamps.pop(0)
    if len(_request_timestamps) >= _MAX_REQUESTS_PER_MINUTE:
        return False
    _request_timestamps.append(now)
    return True


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
        self._api_key = settings.anthropic_api_key
        self._model = "claude-sonnet-4-20250514"

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

        # Check API key
        if not self._api_key:
            logger.warning("ANTHROPIC_API_KEY not set — returning original text")
            return f"[{source_language}] {text}" if source_language else text

        # Rate limit
        if not _rate_limit_ok():
            logger.warning("Translation rate limit reached (10/min) — returning original")
            return f"[{source_language}] {text}" if source_language else text

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "max_tokens": 1024,
                        "system": self.SYSTEM_PROMPT,
                        "messages": [
                            {
                                "role": "user",
                                "content": f"Przetlumacz na polski (zrodlo: {source_language}):\n\n{text}",
                            }
                        ],
                    },
                )

            if response.status_code != 200:
                logger.error("Translation API error %d: %s", response.status_code, response.text[:200])
                return f"[{source_language}] {text}" if source_language else text

            data = response.json()
            translated = data["content"][0]["text"].strip()

            # Cache result
            self._cache[h] = translated
            return translated

        except Exception as e:
            logger.error("Translation failed: %s", e)
            return f"[{source_language}] {text}" if source_language else text

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
