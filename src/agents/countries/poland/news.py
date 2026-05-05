"""Agent mediow informacyjnych dla Poland (PL).

Pobiera i parsuje dane z news zrodel w Poland.
"""

from src.agents.base_agent import BaseAgent, RawRecord, SourceType


class PLNewsAgent(BaseAgent):
    """Agent mediow informacyjnych dla Poland."""

    def __init__(self, source_config: dict):
        super().__init__(
            name="pl_news",
            country_code="PL",
            language="pl",
            source_type=SourceType.NEWS,
            trust_score=source_config.get("trust_score", 0.5),
            is_official_source=source_config.get("is_official", False),
            scrape_interval_minutes=source_config.get("scrape_interval_minutes", 30),
        )
        self.source_config = source_config

    async def fetch(self) -> list[RawRecord]:
        """Pobiera dane z news zrodel Poland."""
        raise NotImplementedError

    async def parse(self, records: list[RawRecord]) -> list[dict]:
        """Parsuje dane z news zrodel Poland."""
        raise NotImplementedError
