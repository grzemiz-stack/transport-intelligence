"""Agent rejestrow finansowych i handlowych dla Finland (FI).

Pobiera i parsuje dane z financial zrodel w Finland.
"""

from src.agents.base_agent import BaseAgent, RawRecord, SourceType


class FIFinancialAgent(BaseAgent):
    """Agent rejestrow finansowych i handlowych dla Finland."""

    def __init__(self, source_config: dict):
        super().__init__(
            name="fi_financial",
            country_code="FI",
            language="fi",
            source_type=SourceType.FINANCIAL,
            trust_score=source_config.get("trust_score", 0.5),
            is_official_source=source_config.get("is_official", False),
            scrape_interval_minutes=source_config.get("scrape_interval_minutes", 30),
        )
        self.source_config = source_config

    async def fetch(self) -> list[RawRecord]:
        """Pobiera dane z financial zrodel Finland."""
        raise NotImplementedError

    async def parse(self, records: list[RawRecord]) -> list[dict]:
        """Parsuje dane z financial zrodel Finland."""
        raise NotImplementedError
