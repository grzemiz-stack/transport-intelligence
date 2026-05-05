"""Agent forow transportowych dla Netherlands (NL).

Pobiera i parsuje dane z forums zrodel w Netherlands.
"""

from src.agents.base_agent import BaseAgent, RawRecord, SourceType


class NLForumsAgent(BaseAgent):
    """Agent forow transportowych dla Netherlands."""

    def __init__(self, source_config: dict):
        super().__init__(
            name="nl_forums",
            country_code="NL",
            language="nl",
            source_type=SourceType.FORUM,
            trust_score=source_config.get("trust_score", 0.5),
            is_official_source=source_config.get("is_official", False),
            scrape_interval_minutes=source_config.get("scrape_interval_minutes", 30),
        )
        self.source_config = source_config

    async def fetch(self) -> list[RawRecord]:
        """Pobiera dane z forums zrodel Netherlands."""
        raise NotImplementedError

    async def parse(self, records: list[RawRecord]) -> list[dict]:
        """Parsuje dane z forums zrodel Netherlands."""
        raise NotImplementedError
