"""BasePoliceAgent — config-driven base class for all police news scrapers.

Replaces 29 near-identical police_live.py files with a single parameterized
implementation.  Country-specific differences (selectors, date formats, URLs)
are captured in PoliceSourceConfig; the scraping logic lives here.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

from bs4 import BeautifulSoup

from src.agents.base_agent import BaseAgent, SourceType
from src.agents.transport_keywords import is_transport_related

logger = logging.getLogger(__name__)

USER_AGENT = "TransportIntelligence/1.0 (Research Bot; kontakt@example.com)"
RATE_LIMIT_SECONDS = 5.0


@dataclass(frozen=True)
class PoliceSourceConfig:
    """All country-specific parameters for a police news scraper."""

    country_code: str
    language: str
    source_name: str
    source_url: str
    url_domain: str
    selectors: tuple[str, ...]
    fallback_href_markers: tuple[str, ...]
    date_class_names: tuple[str, ...] = ()
    date_patterns: tuple[str, ...] = (
        r"(\d{1,2}\.\d{1,2}\.\d{4})",
        r"(\d{4}-\d{2}-\d{2})",
    )


class BasePoliceAgent(BaseAgent):
    """Config-driven police news scraper.

    All country-specific behaviour is determined by PoliceSourceConfig.
    Subclass only when a country needs truly custom parsing logic
    (e.g. Germany with dual RSS+HTML sources).
    """

    def __init__(self, config: PoliceSourceConfig, event_queue=None):
        self._config = config
        super().__init__(
            country_code=config.country_code,
            language=config.language,
            source_type=SourceType.POLICE,
            source_name=config.source_name,
            source_url=config.source_url,
            trust_score=1.0,
            is_official=True,
            scrape_interval_minutes=60,
            event_queue=event_queue,
            max_retries=3,
            base_retry_delay=10.0,
        )
        self._last_request_time: float = 0.0

    # -- rate limiting ---------------------------------------------------

    async def _rate_limit(self):
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < RATE_LIMIT_SECONDS:
            wait = RATE_LIMIT_SECONDS - elapsed
            self._logger.debug("Rate limit: czekam %.1fs", wait)
            await asyncio.sleep(wait)
        self._last_request_time = asyncio.get_event_loop().time()

    # -- fetch -----------------------------------------------------------

    async def _fetch_url(self, url: str) -> str:
        await self._rate_limit()
        session = await self.get_session()
        headers = {"User-Agent": USER_AGENT}
        self._logger.info("Fetching: %s", url)
        start = asyncio.get_event_loop().time()
        response = await session.get(url, headers=headers)
        response.raise_for_status()
        elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
        self._logger.info(
            "Fetch OK: HTTP %d, %d bytes, %.0fms",
            response.status_code, len(response.text), elapsed_ms,
        )
        return response.text

    async def fetch(self) -> str:
        return await self._fetch_url(self._config.source_url)

    # -- parse -----------------------------------------------------------

    async def parse(self, raw_data: str) -> list[dict]:
        soup = BeautifulSoup(raw_data, "html.parser")
        events: list[dict] = []
        seen_titles: set[str] = set()

        items = self._find_items(soup)
        self._logger.info(
            "%s: znaleziono %d elementow",
            self._config.source_name, len(items),
        )

        transport_count = 0
        for item in items:
            parsed = self._parse_item(item)
            if not parsed:
                continue
            full_text = f"{parsed.get('title', '')} {parsed.get('description', '')}".lower()
            if is_transport_related(full_text, self._config.language):
                title_key = parsed["title"].strip().lower()
                if title_key and title_key not in seen_titles:
                    seen_titles.add(title_key)
                    transport_count += 1
                    events.append(self._make_event(parsed))

        self._logger.info(
            "%s: %d transport-related events",
            self._config.source_name, transport_count,
        )
        return events

    # -- item discovery --------------------------------------------------

    def _find_items(self, soup: BeautifulSoup) -> list:
        """Find news items using configured selectors, with link-based fallback."""
        for selector in self._config.selectors:
            items = soup.select(selector)
            if items:
                return items

        # Fallback: links matching href markers
        items: list = []
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if any(marker in href.lower() for marker in self._config.fallback_href_markers):
                parent = link.find_parent(["div", "li", "article", "section"])
                if parent and parent not in items:
                    items.append(parent)
        return items

    # -- single item parsing ---------------------------------------------

    def _parse_item(self, item) -> dict | None:
        result: dict = {}

        # Title
        title_el = item.find(["h2", "h3", "h4"])
        if title_el:
            result["title"] = title_el.get_text(strip=True)
        else:
            link = item.find("a")
            if link:
                result["title"] = link.get_text(strip=True)
            else:
                return None

        if not result.get("title") or len(result["title"]) < 5:
            return None

        # Link
        link_el = item.find("a", href=True)
        if link_el:
            href = link_el["href"]
            if href.startswith("/"):
                href = self._config.url_domain + href
            elif not href.startswith("http"):
                href = self._config.url_domain + "/" + href
            result["link"] = href
        else:
            result["link"] = self._config.source_url

        # Description
        desc_el = item.find("p")
        if desc_el:
            result["description"] = desc_el.get_text(strip=True)
        else:
            full_text = item.get_text(strip=True)
            title_text = result.get("title", "")
            desc = full_text.replace(title_text, "").strip()
            result["description"] = desc[:500] if desc else ""

        # Date
        result["date"] = self._extract_date(item)
        return result

    # -- event dict ------------------------------------------------------

    def _make_event(self, parsed: dict) -> dict:
        cfg = self._config
        return {
            "title": parsed.get("title", ""),
            "description": parsed.get("description", ""),
            "date": parsed.get("date", ""),
            "source_url": parsed.get("link", cfg.source_url),
            "raw_text": f"{parsed.get('title', '')}\n{parsed.get('description', '')}",
            "country_code": cfg.country_code,
            "language": cfg.language,
            "source_name": cfg.source_name,
            "trust_score": 1.0,
            "is_official": True,
            "source_type": SourceType.POLICE.value,
            "timestamp": parsed.get("date") or datetime.utcnow().isoformat(),
            "collected_at": datetime.utcnow().isoformat(),
        }

    # -- date extraction -------------------------------------------------

    def _extract_date(self, item) -> str:
        # 1. <time> element
        time_el = item.find("time")
        if time_el:
            dt = time_el.get("datetime", "")
            if dt:
                return dt
            return time_el.get_text(strip=True)

        # 2. Elements with date-related CSS classes
        for cls_name in self._config.date_class_names:
            date_el = item.find(class_=re.compile(cls_name, re.IGNORECASE))
            if date_el:
                return date_el.get_text(strip=True)

        # 3. Regex patterns in text
        text = item.get_text()
        for pattern in self._config.date_patterns:
            m = re.search(pattern, text)
            if m:
                return m.group(1)

        return ""
