"""Agent rejestrow finansowych i handlowych dla Belgium (BE).

Pobiera i parsuje dane z financial zrodel w Belgium.
"""

from src.agents.base_agent import BaseAgent, RawRecord, SourceType


class BEFinancialAgent(BaseAgent):
    """Agent rejestrow finansowych i handlowych dla Belgium."""

    def __init__(self, source_config: dict):
        super().__init__(
            name="be_financial",
            country_code="BE",
            language="nl",
            source_type=SourceType.FINANCIAL,
            trust_score=source_config.get("trust_score", 0.5),
            is_official_source=source_config.get("is_official", False),
            scrape_interval_minutes=source_config.get("scrape_interval_minutes", 30),
        )
        self.source_config = source_config

    async def fetch(self) -> list[RawRecord]:
        """Pobiera dane z financial zrodel Belgium."""
        raise NotImplementedError

    async def parse(self, records: list[RawRecord]) -> list[dict]:
        """Parsuje dane z financial zrodel Belgium."""
        raise NotImplementedError
