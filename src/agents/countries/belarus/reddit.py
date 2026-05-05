"""Agent serwisu Reddit dla Belarus (BY).

Pobiera i parsuje dane z reddit zrodel w Belarus.
"""

from src.agents.base_agent import BaseAgent, RawRecord, SourceType


class BYRedditAgent(BaseAgent):
    """Agent serwisu Reddit dla Belarus."""

    def __init__(self, source_config: dict):
        super().__init__(
            name="by_reddit",
            country_code="BY",
            language="be",
            source_type=SourceType.REDDIT,
            trust_score=source_config.get("trust_score", 0.5),
            is_official_source=source_config.get("is_official", False),
            scrape_interval_minutes=source_config.get("scrape_interval_minutes", 30),
        )
        self.source_config = source_config

    async def fetch(self) -> list[RawRecord]:
        """Pobiera dane z reddit zrodel Belarus."""
        raise NotImplementedError

    async def parse(self, records: list[RawRecord]) -> list[dict]:
        """Parsuje dane z reddit zrodel Belarus."""
        raise NotImplementedError
