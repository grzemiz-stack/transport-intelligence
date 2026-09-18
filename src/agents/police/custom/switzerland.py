"""SwissPoliceAgent — card-based layout with "DD. MONTH YYYY" dates.

Single source (fedpol.admin.ch) but uses card-specific CSS selectors
(div.card__title, div.card__description) and a date format like
"15. März 2025" that the standard base class doesn't handle.
"""

import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.agents.base_agent import SourceType
from src.agents.police.base import BasePoliceAgent, PoliceSourceConfig
from src.agents.transport_keywords import is_transport_related

FEDPOL_URL = "https://www.fedpol.admin.ch/de/medieninformationen"

_CONFIG = PoliceSourceConfig(
    country_code="CH",
    language="de",
    source_name="Fedpol Schweiz",
    source_url=FEDPOL_URL,
    url_domain="https://www.fedpol.admin.ch",
    selectors=("div.card", "article", "div.news-item", "div.list-item"),
    fallback_href_markers=("/medien", "/news", "/aktuell"),
    date_class_names=(),
    date_patterns=(),  # custom _extract_date handles this
)

# DD. MONTH YYYY (German), e.g. "15. März 2025", "3. Januar 2024"
_DATE_WORD = r"(\d{1,2}\.\s*\w+\s+\d{4})"
_DATE_DOT = r"(\d{1,2}\.\d{1,2}\.\d{4})"
_DATE_ISO = r"(\d{4}-\d{2}-\d{2})"


class SwissPoliceAgent(BasePoliceAgent):
    """Swiss police scraper with card-based layout support."""

    def __init__(self, event_queue=None):
        super().__init__(_CONFIG, event_queue)

    async def parse(self, raw_data: str) -> list[dict]:
        soup = BeautifulSoup(raw_data, "html.parser")
        events: list[dict] = []
        seen: set[str] = set()

        items = self._find_items(soup)
        self._logger.info("Fedpol: znaleziono %d elementow", len(items))

        for item in items:
            # Card-specific title selector, then standard fallback
            title_el = (
                item.select_one("div.card__title")
                or item.find(["h2", "h3", "h4"])
                or item.find("a")
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # Card-specific description selector
            desc_el = item.select_one("div.card__description") or item.find("p")
            desc = desc_el.get_text(strip=True) if desc_el else ""

            link_el = item.find("a", href=True)
            href = FEDPOL_URL
            if link_el:
                h = link_el["href"]
                if h.startswith("/"):
                    href = "https://www.fedpol.admin.ch" + h
                elif h.startswith("http"):
                    href = h
                else:
                    href = "https://www.fedpol.admin.ch/" + h

            full = f"{title} {desc}".lower()
            if is_transport_related(full, "de"):
                key = title.strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    date = self._extract_ch_date(item)
                    events.append({
                        "title": title,
                        "description": desc,
                        "date": date,
                        "source_url": href,
                        "raw_text": f"{title}\n{desc}",
                        "country_code": "CH",
                        "language": "de",
                        "source_name": "Fedpol Schweiz",
                        "trust_score": 1.0,
                        "is_official": True,
                        "source_type": SourceType.POLICE.value,
                        "timestamp": date or datetime.utcnow().isoformat(),
                        "collected_at": datetime.utcnow().isoformat(),
                    })

        self._logger.info("CH total: %d transport-related events", len(events))
        return events

    @staticmethod
    def _extract_ch_date(item) -> str:
        """Extract date — tries DD. MONTH YYYY first, then numeric formats."""
        text = item.get_text()
        for pat in (_DATE_WORD, _DATE_DOT, _DATE_ISO):
            m = re.search(pat, text)
            if m:
                return m.group(1)
        return ""
