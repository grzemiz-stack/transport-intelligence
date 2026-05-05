"""BelgianPoliceAgent — live scraper dla strony Police Belge / Politie België.

Scrapuje komunikaty z:
https://www.police.be/5998/fr/actualites

Filtruje te dotyczace transportu (vol, camion, transport, autoroute).
"""

import asyncio
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.agents.base_agent import BaseAgent, SourceType
from src.agents.transport_keywords import is_transport_related

logger = logging.getLogger(__name__)

POLICE_URL = "https://www.police.be/5998/fr/actualites"

USER_AGENT = "TransportIntelligence/1.0 (Research Bot; kontakt@example.com)"

RATE_LIMIT_SECONDS = 5.0


class BelgianPoliceAgent(BaseAgent):
    def __init__(self, event_queue=None):
        super().__init__(
            country_code="BE",
            language="fr",
            source_type=SourceType.POLICE,
            source_name="Police Belge",
            source_url=POLICE_URL,
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
        self._logger.info("Fetching: %s", url)
        start = asyncio.get_event_loop().time()
        response = await session.get(url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
        self._logger.info("Fetch OK: HTTP %d, %d bytes, %.0fms",
                          response.status_code, len(response.text), elapsed_ms)
        return response.text

    async def fetch(self) -> str:
        return await self._fetch_url(POLICE_URL)

    async def parse(self, raw_data: str) -> list[dict]:
        soup = BeautifulSoup(raw_data, "html.parser")
        events = []
        seen_titles = set()

        items = (soup.select("article") or soup.select("div.view-content div.views-row")
                 or soup.select("div.news-item") or soup.select("li.list-item"))
        if not items:
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if "/actualites/" in href or "/nieuws/" in href:
                    parent = link.find_parent(["div", "li", "article", "section"])
                    if parent and parent not in items:
                        items.append(parent)

        self._logger.info("Police.be: znaleziono %d elementow", len(items))

        for item in items:
            parsed = self._parse_item(item)
            if not parsed:
                continue
            full_text = f"{parsed['title']} {parsed.get('description', '')}".lower()
            if self._is_transport_related(full_text):
                key = parsed["title"].strip().lower()
                if key and key not in seen_titles:
                    seen_titles.add(key)
                    events.append(self._make_event(parsed))

        self._logger.info("Police.be: %d transport-related events", len(events))
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
                href = "https://www.police.be" + href
            elif not href.startswith("http"):
                href = "https://www.police.be/" + href
            result["link"] = href
        else:
            result["link"] = POLICE_URL
        desc_el = item.find("p")
        result["description"] = desc_el.get_text(strip=True) if desc_el else ""
        result["date"] = self._extract_date(item)
        return result

    def _make_event(self, parsed: dict) -> dict:
        return {
            "title": parsed.get("title", ""),
            "description": parsed.get("description", ""),
            "date": parsed.get("date", ""),
            "source_url": parsed.get("link", POLICE_URL),
            "raw_text": f"{parsed.get('title', '')}\n{parsed.get('description', '')}",
            "country_code": "BE", "language": "fr",
            "source_name": "Police Belge",
            "trust_score": 1.0, "is_official": True,
            "source_type": SourceType.POLICE.value,
            "timestamp": parsed.get("date") or datetime.utcnow().isoformat(),
            "collected_at": datetime.utcnow().isoformat(),
        }

    def _extract_date(self, item) -> str:
        time_el = item.find("time")
        if time_el:
            return time_el.get("datetime", "") or time_el.get_text(strip=True)
        for cls in ["date", "datum", "news-date"]:
            el = item.find(class_=re.compile(cls, re.IGNORECASE))
            if el:
                return el.get_text(strip=True)
        text = item.get_text()
        for pat in [r"(\d{1,2}/\d{1,2}/\d{4})", r"(\d{1,2}\.\d{1,2}\.\d{4})", r"(\d{4}-\d{2}-\d{2})"]:
            m = re.search(pat, text)
            if m:
                return m.group(1)
        return ""

    def _is_transport_related(self, text: str) -> bool:
        return is_transport_related(text, "fr")
