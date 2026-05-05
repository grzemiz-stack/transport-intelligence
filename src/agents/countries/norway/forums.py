"""Agent forow transportowych dla Norway (NO).

Pobiera i parsuje dane z forums zrodel w Norway.
"""

from src.agents.base_agent import BaseAgent, RawRecord, SourceType


class NOForumsAgent(BaseAgent):
    """Agent forow transportowych dla Norway."""

    def __init__(self, source_config: dict):
        super().__init__(
            name="no_forums",
            country_code="NO",
            language="no",
            source_type=SourceType.FORUM,
            trust_score=source_config.get("trust_score", 0.5),
            is_official_source=source_config.get("is_official", False),
            scrape_interval_minutes=source_config.get("scrape_interval_minutes", 30),
        )
        self.source_config = source_config

    async def fetch(self) -> list[RawRecord]:
        """Pobiera dane z forums zrodel Norway."""
        raise NotImplementedError

    async def parse(self, records: list[RawRecord]) -> list[dict]:
        """Parsuje dane z forums zrodel Norway."""
        raise NotImplementedError
