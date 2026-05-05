"""Agent zrodel policyjnych dla Iceland (IS).

Pobiera i parsuje dane z police zrodel w Iceland.
"""

from src.agents.base_agent import BaseAgent, RawRecord, SourceType


class ISPoliceAgent(BaseAgent):
    """Agent zrodel policyjnych dla Iceland."""

    def __init__(self, source_config: dict):
        super().__init__(
            name="is_police",
            country_code="IS",
            language="is",
            source_type=SourceType.POLICE,
            trust_score=source_config.get("trust_score", 0.5),
            is_official_source=source_config.get("is_official", False),
            scrape_interval_minutes=source_config.get("scrape_interval_minutes", 30),
        )
        self.source_config = source_config

    async def fetch(self) -> list[RawRecord]:
        """Pobiera dane z police zrodel Iceland."""
        raise NotImplementedError

    async def parse(self, records: list[RawRecord]) -> list[dict]:
        """Parsuje dane z police zrodel Iceland."""
        raise NotImplementedError
