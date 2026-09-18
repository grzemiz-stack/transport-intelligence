"""Shared Claude API client with per-instance rate limiting and JSON extraction."""

import logging
import time

import httpx

logger = logging.getLogger(__name__)

COUNTRY_NAMES: dict[str, str] = {
    "PL": "Polska", "DE": "Niemcy", "CZ": "Czechy", "SK": "Slowacja",
    "AT": "Austria", "HU": "Wegry", "RO": "Rumunia", "NL": "Holandia",
    "FR": "Francja", "IT": "Wlochy", "ES": "Hiszpania", "GB": "Wielka Brytania",
    "BE": "Belgia", "DK": "Dania", "SE": "Szwecja", "NO": "Norwegia",
    "FI": "Finlandia", "HR": "Chorwacja", "SI": "Slowenia", "BG": "Bulgaria",
    "GR": "Grecja", "LT": "Litwa", "LV": "Lotwa", "EE": "Estonia",
}


class ClaudeClient:
    """Thin wrapper around the Anthropic Messages API.

    Each instance carries its own rate-limit bucket and httpx client,
    so analytics modules can use different limits and timeouts.

    Note: the rate limit is **per instance**.  Before this refactor the
    three analytics modules shared a single module-level timestamp list,
    so they collectively consumed 5 req/min.  Now each instance gets its
    own budget — if all three run concurrently, the aggregate can reach
    15 req/min.  Adjust ``max_requests_per_minute`` if a global cap is
    needed.
    """

    API_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_requests_per_minute: int = 5,
        timeout: float = 60.0,
    ):
        self._api_key = api_key
        self._model = model
        self._max_rpm = max_requests_per_minute
        self._timestamps: list[float] = []
        self._http = httpx.AsyncClient(timeout=timeout)

    # ------------------------------------------------------------------
    # Rate limiting (instance-level — no shared mutable state)
    # ------------------------------------------------------------------

    def rate_limit_ok(self) -> bool:
        now = time.time()
        while self._timestamps and self._timestamps[0] < now - 60:
            self._timestamps.pop(0)
        if len(self._timestamps) >= self._max_rpm:
            return False
        self._timestamps.append(now)
        return True

    # ------------------------------------------------------------------
    # API call
    # ------------------------------------------------------------------

    async def call(
        self,
        user_prompt: str,
        system_prompt: str,
        max_tokens: int = 4096,
    ) -> str | None:
        """Send a message to Claude and return the response text, or *None* on error."""
        if not self._api_key:
            logger.warning("ANTHROPIC_API_KEY not set — skipping Claude call")
            return None

        if not self.rate_limit_ok():
            logger.warning("Claude rate limit reached (%d/min)", self._max_rpm)
            return None

        try:
            response = await self._http.post(
                self.API_URL,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": self.API_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": max_tokens,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
            )

            if response.status_code != 200:
                logger.error(
                    "Claude API error %d: %s",
                    response.status_code,
                    response.text[:200],
                )
                return None

            return response.json()["content"][0]["text"].strip()

        except Exception as e:
            logger.error("Claude API call failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # JSON extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_json(text: str) -> str:
        """Extract JSON object or array from text that may contain markdown fences."""
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            return stripped
        if "```" in stripped:
            parts = stripped.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{") or part.startswith("["):
                    return part
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            return stripped[start : end + 1]
        return stripped
