"""Agent serwisu Reddit dla Lithuania (LT).

Pobiera i parsuje dane z reddit zrodel w Lithuania.
"""

from src.agents.base_agent import BaseAgent, RawRecord, SourceType


class LTRedditAgent(BaseAgent):
    """Agent serwisu Reddit dla Lithuania."""

    def __init__(self, source_config: dict):
        super().__init__(
            name="lt_reddit",
            country_code="LT",
            language="lt",
            source_type=SourceType.REDDIT,
            trust_score=source_config.get("trust_score", 0.5),
            is_official_source=source_config.get("is_official", False),
            scrape_interval_minutes=source_config.get("scrape_interval_minutes", 30),
        )
        self.source_config = source_config

    async def fetch(self) -> list[RawRecord]:
        """Pobiera dane z reddit zrodel Lithuania."""
        raise NotImplementedError

    async def parse(self, records: list[RawRecord]) -> list[dict]:
        """Parsuje dane z reddit zrodel Lithuania."""
        raise NotImplementedError
