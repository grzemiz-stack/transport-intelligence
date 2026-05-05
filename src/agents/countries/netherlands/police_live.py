"""DutchPoliceAgent — live scraper dla strony Politie Nederland.

Scrapuje komunikaty z:
https://www.politie.nl/actueel/nieuws

Filtruje te dotyczace transportu (diefstal, vrachtwagen, transport, lading).
"""

import asyncio
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.agents.base_agent import BaseAgent, SourceType
from src.agents.transport_keywords import is_transport_related

logger = logging.getLogger(__name__)

POLITIE_URL = "https://www.politie.nl/nieuws"

USER_AGENT = "TransportIntelligence/1.0 (Research Bot; kontakt@example.com)"

RATE_LIMIT_SECONDS = 5.0


class DutchPoliceAgent(BaseAgent):
    """Agent scrapujacy komunikaty Politie Nederland dot. transportu.

    Scrapuje z: politie.nl/actueel/nieuws
    Respektuje robots.txt, rate-limiting, custom User-Agent.
    """

    def __init__(self, event_queue=None):
        super().__init__(
            country_code="NL",
            language="nl",
            source_type=SourceType.POLICE,
            source_name="Politie Nederland",
            source_url=POLITIE_URL,
            trust_score=1.0,
            is_official=True,
            scrape_interval_minutes=60,
            event_queue=event_queue,
            max_retries=3,
            base_retry_delay=10.0,
        )
        self._last_request_time: float = 0.0

    async def _rate_limit(self):
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < RATE_LIMIT_SECONDS:
            await asyncio.sleep(RATE_LIMIT_SECONDS - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def _fetch_url(self, url: str) -> str:
        await self._rate_limit()
        session = await self.get_session()
        headers = {"User-Agent": USER_AGENT}
        self._logger.info("Fetching: %s", url)
        start = asyncio.get_event_loop().time()
        response = await session.get(url, headers=headers)
        response.raise_for_status()
        elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
        self._logger.info("Fetch OK: HTTP %d, %d bytes, %.0fms",
                          response.status_code, len(response.text), elapsed_ms)
        return response.text

    async def fetch(self) -> str:
        return await self._fetch_url(POLITIE_URL)

    async def parse(self, raw_data: str) -> list[dict]:
        soup = BeautifulSoup(raw_data, "html.parser")
        events = []
        seen_titles = set()

        items = (
            soup.select("article")
            or soup.select("div.news-item")
            or soup.select("div.search-result")
            or soup.select("li.list-item")
        )

        if not items:
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if "/nieuws/" in href or "/berichten/" in href:
                    parent = link.find_parent(["div", "li", "article", "section"])
                    if parent and parent not in items:
                        items.append(parent)

        self._logger.info("Politie.nl: znaleziono %d elementow", len(items))
        transport_count = 0

        for item in items:
            parsed = self._parse_item(item)
            if not parsed:
                continue
            full_text = f"{parsed.get('title', '')} {parsed.get('description', '')}".lower()
            if self._is_transport_related(full_text):
                title_key = parsed["title"].strip().lower()
                if title_key and title_key not in seen_titles:
                    seen_titles.add(title_key)
                    transport_count += 1
                    events.append(self._make_event(parsed))

        self._logger.info("Politie.nl: %d transport-related events", transport_count)
        return events

    def _parse_item(self, item) -> dict | None:
        result = {}
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

        link_el = item.find("a", href=True)
        if link_el:
            href = link_el["href"]
            if href.startswith("/"):
                href = "https://www.politie.nl" + href
            elif not href.startswith("http"):
                href = "https://www.politie.nl/" + href
            result["link"] = href
        else:
            result["link"] = POLITIE_URL

        desc_el = item.find("p")
        if desc_el:
            result["description"] = desc_el.get_text(strip=True)
        else:
            full_text = item.get_text(strip=True)
            desc = full_text.replace(result.get("title", ""), "").strip()
            result["description"] = desc[:500] if desc else ""

        result["date"] = self._extract_date(item)
        return result

    def _make_event(self, parsed: dict) -> dict:
        return {
            "title": parsed.get("title", ""),
            "description": parsed.get("description", ""),
            "date": parsed.get("date", ""),
            "source_url": parsed.get("link", POLITIE_URL),
            "raw_text": f"{parsed.get('title', '')}\n{parsed.get('description', '')}",
            "country_code": "NL",
            "language": "nl",
            "source_name": "Politie Nederland",
            "trust_score": 1.0,
            "is_official": True,
            "source_type": SourceType.POLICE.value,
            "timestamp": parsed.get("date") or datetime.utcnow().isoformat(),
            "collected_at": datetime.utcnow().isoformat(),
        }

    def _extract_date(self, item) -> str:
        time_el = item.find("time")
        if time_el:
            dt = time_el.get("datetime", "")
            if dt:
                return dt
            return time_el.get_text(strip=True)
        for cls_name in ["date", "datum", "news-date"]:
            date_el = item.find(class_=re.compile(cls_name, re.IGNORECASE))
            if date_el:
                return date_el.get_text(strip=True)
        text = item.get_text()
        m = re.search(r"(\d{1,2}-\d{1,2}-\d{4})", text)
        if m:
            return m.group(1)
        m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if m:
            return m.group(1)
        return ""

    def _is_transport_related(self, text: str) -> bool:
        return is_transport_related(text, "nl")
