"""FinnishPoliceAgent — live scraper dla strony Poliisi Suomi.

Scrapuje: https://poliisi.fi/uutiset
Keywords FI: varkaus, kuljetus, rekka, moottoritie
"""

import asyncio
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.agents.base_agent import BaseAgent, SourceType
from src.agents.transport_keywords import is_transport_related

logger = logging.getLogger(__name__)

POLICE_URL = "https://poliisi.fi/uutiset"
USER_AGENT = "TransportIntelligence/1.0 (Research Bot; kontakt@example.com)"

RATE_LIMIT_SECONDS = 5.0


class FinnishPoliceAgent(BaseAgent):
    def __init__(self, event_queue=None):
        super().__init__(
            country_code="FI", language="fi",
            source_type=SourceType.POLICE,
            source_name="Poliisi Suomi",
            source_url=POLICE_URL,
            trust_score=1.0, is_official=True,
            scrape_interval_minutes=60,
            event_queue=event_queue, max_retries=3, base_retry_delay=10.0,
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
        self._logger.info("Fetch OK: HTTP %d, %d bytes, %.0fms",
                          response.status_code, len(response.text),
                          (asyncio.get_event_loop().time() - start) * 1000)
        return response.text

    async def fetch(self) -> str:
        return await self._fetch_url(POLICE_URL)

    async def parse(self, raw_data: str) -> list[dict]:
        soup = BeautifulSoup(raw_data, "html.parser")
        events, seen = [], set()
        items = (soup.select("article") or soup.select("div.news-item")
                 or soup.select("div.list-item") or soup.select("li.list-item"))
        if not items:
            for link in soup.find_all("a", href=True):
                if "/uutiset/" in link["href"] or "/tiedotteet/" in link["href"]:
                    p = link.find_parent(["div", "li", "article", "section"])
                    if p and p not in items:
                        items.append(p)
        self._logger.info("Poliisi.fi: znaleziono %d elementow", len(items))
        for item in items:
            parsed = self._parse_item(item)
            if not parsed:
                continue
            full = f"{parsed['title']} {parsed.get('description', '')}".lower()
            if self._is_transport_related(full):
                key = parsed["title"].strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    events.append(self._make_event(parsed))
        self._logger.info("Poliisi.fi: %d transport-related events", len(events))
        return events

    def _parse_item(self, item) -> dict | None:
        title_el = item.find(["h2", "h3", "h4"]) or item.find("a")
        if not title_el:
            return None
        title = title_el.get_text(strip=True)
        if not title or len(title) < 5:
            return None
        link_el = item.find("a", href=True)
        href = POLICE_URL
        if link_el:
            h = link_el["href"]
            href = ("https://poliisi.fi" + h) if h.startswith("/") else (h if h.startswith("http") else "https://poliisi.fi/" + h)
        desc_el = item.find("p")
        return {"title": title, "link": href,
                "description": desc_el.get_text(strip=True) if desc_el else "",
                "date": self._extract_date(item)}

    def _make_event(self, p: dict) -> dict:
        return {
            "title": p["title"], "description": p.get("description", ""),
            "date": p.get("date", ""), "source_url": p["link"],
            "raw_text": f"{p['title']}\n{p.get('description', '')}",
            "country_code": "FI", "language": "fi",
            "source_name": "Poliisi Suomi",
            "trust_score": 1.0, "is_official": True,
            "source_type": SourceType.POLICE.value,
            "timestamp": p.get("date") or datetime.utcnow().isoformat(),
            "collected_at": datetime.utcnow().isoformat(),
        }

    def _extract_date(self, item) -> str:
        time_el = item.find("time")
        if time_el:
            return time_el.get("datetime", "") or time_el.get_text(strip=True)
        for cls in ["date", "pvm", "news-date"]:
            el = item.find(class_=re.compile(cls, re.IGNORECASE))
            if el:
                return el.get_text(strip=True)
        text = item.get_text()
        for pat in [r"(\d{1,2}\.\d{1,2}\.\d{4})", r"(\d{4}-\d{2}-\d{2})"]:
            m = re.search(pat, text)
            if m:
                return m.group(1)
        return ""

    def _is_transport_related(self, text: str) -> bool:
        return is_transport_related(text, "fi")
