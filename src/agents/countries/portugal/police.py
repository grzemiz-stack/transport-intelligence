"""Agent zrodel policyjnych dla Portugal (PT).

Pobiera i parsuje dane z police zrodel w Portugal.
"""

from src.agents.base_agent import BaseAgent, RawRecord, SourceType


class PTPoliceAgent(BaseAgent):
    """Agent zrodel policyjnych dla Portugal."""

    def __init__(self, source_config: dict):
        super().__init__(
            name="pt_police",
            country_code="PT",
            language="pt",
            source_type=SourceType.POLICE,
            trust_score=source_config.get("trust_score", 0.5),
            is_official_source=source_config.get("is_official", False),
            scrape_interval_minutes=source_config.get("scrape_interval_minutes", 30),
        )
        self.source_config = source_config

    async def fetch(self) -> list[RawRecord]:
        """Pobiera dane z police zrodel Portugal."""
        raise NotImplementedError

    async def parse(self, records: list[RawRecord]) -> list[dict]:
        """Parsuje dane z police zrodel Portugal."""
        raise NotImplementedError
