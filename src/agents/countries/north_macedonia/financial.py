"""Agent rejestrow finansowych i handlowych dla North Macedonia (MK).

Pobiera i parsuje dane z financial zrodel w North Macedonia.
"""

from src.agents.base_agent import BaseAgent, RawRecord, SourceType


class MKFinancialAgent(BaseAgent):
    """Agent rejestrow finansowych i handlowych dla North Macedonia."""

    def __init__(self, source_config: dict):
        super().__init__(
            name="mk_financial",
            country_code="MK",
            language="mk",
            source_type=SourceType.FINANCIAL,
            trust_score=source_config.get("trust_score", 0.5),
            is_official_source=source_config.get("is_official", False),
            scrape_interval_minutes=source_config.get("scrape_interval_minutes", 30),
        )
        self.source_config = source_config

    async def fetch(self) -> list[RawRecord]:
        """Pobiera dane z financial zrodel North Macedonia."""
        raise NotImplementedError

    async def parse(self, records: list[RawRecord]) -> list[dict]:
        """Parsuje dane z financial zrodel North Macedonia."""
        raise NotImplementedError
