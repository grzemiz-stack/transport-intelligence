"""Agent rejestrow finansowych i handlowych dla Turkey (TR).

Pobiera i parsuje dane z financial zrodel w Turkey.
"""

from src.agents.base_agent import BaseAgent, RawRecord, SourceType


class TRFinancialAgent(BaseAgent):
    """Agent rejestrow finansowych i handlowych dla Turkey."""

    def __init__(self, source_config: dict):
        super().__init__(
            name="tr_financial",
            country_code="TR",
            language="tr",
            source_type=SourceType.FINANCIAL,
            trust_score=source_config.get("trust_score", 0.5),
            is_official_source=source_config.get("is_official", False),
            scrape_interval_minutes=source_config.get("scrape_interval_minutes", 30),
        )
        self.source_config = source_config

    async def fetch(self) -> list[RawRecord]:
        """Pobiera dane z financial zrodel Turkey."""
        raise NotImplementedError

    async def parse(self, records: list[RawRecord]) -> list[dict]:
        """Parsuje dane z financial zrodel Turkey."""
        raise NotImplementedError
