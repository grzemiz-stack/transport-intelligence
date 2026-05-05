"""Agent kanalow Telegram dla Malta (MT).

Pobiera i parsuje dane z telegram zrodel w Malta.
"""

from src.agents.base_agent import BaseAgent, RawRecord, SourceType


class MTTelegramAgent(BaseAgent):
    """Agent kanalow Telegram dla Malta."""

    def __init__(self, source_config: dict):
        super().__init__(
            name="mt_telegram",
            country_code="MT",
            language="mt",
            source_type=SourceType.TELEGRAM,
            trust_score=source_config.get("trust_score", 0.5),
            is_official_source=source_config.get("is_official", False),
            scrape_interval_minutes=source_config.get("scrape_interval_minutes", 30),
        )
        self.source_config = source_config

    async def fetch(self) -> list[RawRecord]:
        """Pobiera dane z telegram zrodel Malta."""
        raise NotImplementedError

    async def parse(self, records: list[RawRecord]) -> list[dict]:
        """Parsuje dane z telegram zrodel Malta."""
        raise NotImplementedError
