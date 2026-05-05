"""Agent alertow drogowych i transportowych dla Spain (ES).

Pobiera i parsuje dane z alerts zrodel w Spain.
"""

from src.agents.base_agent import BaseAgent, RawRecord, SourceType


class ESAlertsAgent(BaseAgent):
    """Agent alertow drogowych i transportowych dla Spain."""

    def __init__(self, source_config: dict):
        super().__init__(
            name="es_alerts",
            country_code="ES",
            language="es",
            source_type=SourceType.ALERTS,
            trust_score=source_config.get("trust_score", 0.5),
            is_official_source=source_config.get("is_official", False),
            scrape_interval_minutes=source_config.get("scrape_interval_minutes", 30),
        )
        self.source_config = source_config

    async def fetch(self) -> list[RawRecord]:
        """Pobiera dane z alerts zrodel Spain."""
        raise NotImplementedError

    async def parse(self, records: list[RawRecord]) -> list[dict]:
        """Parsuje dane z alerts zrodel Spain."""
        raise NotImplementedError
