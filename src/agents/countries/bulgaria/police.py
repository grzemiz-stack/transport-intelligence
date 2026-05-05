"""Agent zrodel policyjnych dla Bulgaria (BG).

Pobiera i parsuje dane z police zrodel w Bulgaria.
"""

from src.agents.base_agent import BaseAgent, RawRecord, SourceType


class BGPoliceAgent(BaseAgent):
    """Agent zrodel policyjnych dla Bulgaria."""

    def __init__(self, source_config: dict):
        super().__init__(
            name="bg_police",
            country_code="BG",
            language="bg",
            source_type=SourceType.POLICE,
            trust_score=source_config.get("trust_score", 0.5),
            is_official_source=source_config.get("is_official", False),
            scrape_interval_minutes=source_config.get("scrape_interval_minutes", 30),
        )
        self.source_config = source_config

    async def fetch(self) -> list[RawRecord]:
        """Pobiera dane z police zrodel Bulgaria."""
        raise NotImplementedError

    async def parse(self, records: list[RawRecord]) -> list[dict]:
        """Parsuje dane z police zrodel Bulgaria."""
        raise NotImplementedError
