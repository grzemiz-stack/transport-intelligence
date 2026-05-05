"""AustrianPoliceAgent — live scraper dla zrodel policji austriackiej.

Scrapuje komunikaty z presseportal.de z austriackimi ID policji.
Alternatywnie: https://www.bmi.gv.at/news.aspx

Filtruje te dotyczace transportu (Diebstahl, LKW, Transport, Autobahn, Ladung).
"""

import asyncio
import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.agents.base_agent import BaseAgent, SourceType
from src.agents.transport_keywords import is_transport_related

logger = logging.getLogger(__name__)

# Presseportal Austria: Landespolizeidirektion sources
PRESSEPORTAL_AT_URL = "https://www.presseportal.de/blaulicht/nr/56519"
BMI_URL = "https://www.bmi.gv.at/news.aspx"

USER_AGENT = "TransportIntelligence/1.0 (Research Bot; kontakt@example.com)"

RATE_LIMIT_SECONDS = 5.0


class AustrianPoliceAgent(BaseAgent):
    """Agent scrapujacy komunikaty policji austriackiej dot. transportu.

    Scrapuje z presseportal.de (austriackie ID policji) + bmi.gv.at.
    Respektuje robots.txt, rate-limiting, custom User-Agent.
    """

    def __init__(self, event_queue=None):
        super().__init__(
            country_code="AT",
            language="de",
            source_type=SourceType.POLICE,
            source_name="Polizei Österreich",
            source_url=PRESSEPORTAL_AT_URL,
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
        """Pobiera HTML z obu zrodel i laczy je."""
        parts = []

        # Source 1: Presseportal Austria
        try:
            html = await self._fetch_url(PRESSEPORTAL_AT_URL)
            parts.append(f"<!-- SOURCE:presseportal -->\n{html}")
        except Exception as e:
            self._logger.warning("Presseportal AT fetch failed: %s", e)

        # Source 2: BMI Austria
        try:
            html = await self._fetch_url(BMI_URL)
            parts.append(f"<!-- SOURCE:bmi -->\n{html}")
        except Exception as e:
            self._logger.warning("BMI.gv.at fetch failed: %s", e)

        if not parts:
            raise RuntimeError("Oba zrodla austriackie niedostepne")

        return "\n<!-- SEPARATOR -->\n".join(parts)

    async def parse(self, raw_data: str) -> list[dict]:
        events = []
        seen_titles = set()

        source_blocks = raw_data.split("<!-- SEPARATOR -->")

        for block in source_blocks:
            if "SOURCE:presseportal" in block:
                block_events = self._parse_presseportal(block)
            elif "SOURCE:bmi" in block:
                block_events = self._parse_bmi(block)
            else:
                block_events = self._parse_bmi(block)

            for ev in block_events:
                title_key = ev.get("title", "").strip().lower()
                if title_key and title_key not in seen_titles:
                    seen_titles.add(title_key)
                    events.append(ev)

        self._logger.info("Parse total: %d transport-related events", len(events))
        return events

    def _parse_presseportal(self, html: str) -> list[dict]:
        """Parsuje komunikaty z presseportal.de (Austria)."""
        soup = BeautifulSoup(html, "html.parser")
        events = []

        items = soup.select("article") or soup.select("div.news-item")
        if not items:
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if "/blaulicht/pm/" in href:
                    parent = link.find_parent(["div", "li", "article", "section"])
                    if parent and parent not in items:
                        items.append(parent)

        self._logger.info("Presseportal AT: znaleziono %d elementow", len(items))

        for item in items:
            parsed = self._parse_item(item, "https://www.presseportal.de")
            if not parsed:
                continue
            full_text = f"{parsed.get('title', '')} {parsed.get('description', '')}".lower()
            if self._is_transport_related(full_text):
                events.append(self._make_event(parsed, "Presseportal/Polizei Österreich"))

        return events

    def _parse_bmi(self, html: str) -> list[dict]:
        """Parsuje komunikaty z bmi.gv.at."""
        soup = BeautifulSoup(html, "html.parser")
        events = []

        items = (
            soup.select("article")
            or soup.select("div.news-item")
            or soup.select("div.list-item")
            or soup.select("li.list-item")
        )

        if not items:
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if "/news/" in href.lower():
                    parent = link.find_parent(["div", "li", "article", "section"])
                    if parent and parent not in items:
                        items.append(parent)

        self._logger.info("BMI.gv.at: znaleziono %d elementow", len(items))

        for item in items:
            parsed = self._parse_item(item, "https://www.bmi.gv.at")
            if not parsed:
                continue
            full_text = f"{parsed.get('title', '')} {parsed.get('description', '')}".lower()
            if self._is_transport_related(full_text):
                events.append(self._make_event(parsed, "BMI Österreich"))

        return events

    def _parse_item(self, item, base_url: str) -> dict | None:
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
                href = base_url + href
            elif not href.startswith("http"):
                href = base_url + "/" + href
            result["link"] = href
        else:
            result["link"] = base_url

        desc_el = item.find("p")
        if desc_el:
            result["description"] = desc_el.get_text(strip=True)
        else:
            full_text = item.get_text(strip=True)
            desc = full_text.replace(result.get("title", ""), "").strip()
            result["description"] = desc[:500] if desc else ""

        result["date"] = self._extract_date(item)
        return result

    def _make_event(self, parsed: dict, source_label: str) -> dict:
        return {
            "title": parsed.get("title", ""),
            "description": parsed.get("description", ""),
            "date": parsed.get("date", ""),
            "source_url": parsed.get("link", PRESSEPORTAL_AT_URL),
            "raw_text": f"{parsed.get('title', '')}\n{parsed.get('description', '')}",
            "country_code": "AT",
            "language": "de",
            "source_name": source_label,
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
        m = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})", text)
        if m:
            return m.group(1)
        m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if m:
            return m.group(1)
        return ""

    def _is_transport_related(self, text: str) -> bool:
        return is_transport_related(text, "de")
