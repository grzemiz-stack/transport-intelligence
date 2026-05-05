"""Agent serwisu Reddit dla Ukraine (UA).

Pobiera i parsuje dane z reddit zrodel w Ukraine.
"""

from src.agents.base_agent import BaseAgent, RawRecord, SourceType


class UARedditAgent(BaseAgent):
    """Agent serwisu Reddit dla Ukraine."""

    def __init__(self, source_config: dict):
        super().__init__(
            name="ua_reddit",
            country_code="UA",
            language="uk",
            source_type=SourceType.REDDIT,
            trust_score=source_config.get("trust_score", 0.5),
            is_official_source=source_config.get("is_official", False),
            scrape_interval_minutes=source_config.get("scrape_interval_minutes", 30),
        )
        self.source_config = source_config

    async def fetch(self) -> list[RawRecord]:
        """Pobiera dane z reddit zrodel Ukraine."""
        raise NotImplementedError

    async def parse(self, records: list[RawRecord]) -> list[dict]:
        """Parsuje dane z reddit zrodel Ukraine."""
        raise NotImplementedError
