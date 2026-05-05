"""Agent kanalow Telegram dla Austria (AT).

Pobiera i parsuje dane z telegram zrodel w Austria.
"""

from src.agents.base_agent import BaseAgent, RawRecord, SourceType


class ATTelegramAgent(BaseAgent):
    """Agent kanalow Telegram dla Austria."""

    def __init__(self, source_config: dict):
        super().__init__(
            name="at_telegram",
            country_code="AT",
            language="de",
            source_type=SourceType.TELEGRAM,
            trust_score=source_config.get("trust_score", 0.5),
            is_official_source=source_config.get("is_official", False),
            scrape_interval_minutes=source_config.get("scrape_interval_minutes", 30),
        )
        self.source_config = source_config

    async def fetch(self) -> list[RawRecord]:
        """Pobiera dane z telegram zrodel Austria."""
        raise NotImplementedError

    async def parse(self, records: list[RawRecord]) -> list[dict]:
        """Parsuje dane z telegram zrodel Austria."""
        raise NotImplementedError
