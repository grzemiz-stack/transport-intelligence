"""BundespolizeiAgent — dual-source scraper (bundespolizei.de + presseportal.de).

Overrides fetch() to merge two HTML sources with markers, and parse() to
dispatch each block to a source-specific parser.
"""

import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.agents.base_agent import SourceType
from src.agents.police.base import BasePoliceAgent, PoliceSourceConfig
from src.agents.transport_keywords import is_transport_related

BUNDESPOLIZEI_URL = "https://www.bundespolizei.de/aktuelles/meldungen"
PRESSEPORTAL_URL = "https://www.presseportal.de/blaulicht/d/bundespolizei"

_CONFIG = PoliceSourceConfig(
    country_code="DE",
    language="de",
    source_name="Bundespolizei",
    source_url=BUNDESPOLIZEI_URL,
    url_domain="https://www.bundespolizei.de",
    selectors=(),  # not used — parse() is overridden
    fallback_href_markers=(),
)

# Bundespolizei.de has many possible selectors
_BPOL_SELECTORS = (
    "article", "div.teaser", "div.list-item", "li.list-item",
    "div.c-teaser", "div.meldung", "div.news-item",
    "div.result-item", "ul.list-unstyled > li", "div.c-content-stage",
)


class BundespolizeiAgent(BasePoliceAgent):
    """Dual-source German police scraper.

    Sources:
      1. presseportal.de/blaulicht/d/bundespolizei (press releases)
      2. bundespolizei.de/aktuelles/meldungen (official)
    """

    def __init__(self, event_queue=None):
        super().__init__(_CONFIG, event_queue)

    # -- fetch (dual source) ---------------------------------------------

    async def fetch(self) -> str:
        parts: list[str] = []
        for label, url in [
            ("presseportal", PRESSEPORTAL_URL),
            ("bundespolizei", BUNDESPOLIZEI_URL),
        ]:
            try:
                html = await self._fetch_url(url)
                parts.append(f"<!-- SOURCE:{label} -->\n{html}")
            except Exception as e:
                self._logger.warning("%s fetch failed: %s", label, e)
        if not parts:
            raise RuntimeError("Oba zrodla niedostepne")
        return "\n<!-- SEPARATOR -->\n".join(parts)

    # -- parse (dispatch per source) -------------------------------------

    async def parse(self, raw_data: str) -> list[dict]:
        events: list[dict] = []
        seen: set[str] = set()

        for block in raw_data.split("<!-- SEPARATOR -->"):
            if "SOURCE:presseportal" in block:
                block_events = self._parse_presseportal(block)
            else:
                block_events = self._parse_bundespolizei(block)

            for ev in block_events:
                key = ev.get("title", "").strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    events.append(ev)

        self._logger.info("Parse total: %d transport-related events", len(events))
        return events

    # -- presseportal parser ---------------------------------------------

    def _parse_presseportal(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select("article") or soup.select("div.news-item")
        if not items:
            items = []
            for link in soup.find_all("a", href=True):
                if "/blaulicht/pm/" in link.get("href", ""):
                    p = link.find_parent(["div", "li", "article", "section"])
                    if p and p not in items:
                        items.append(p)

        self._logger.info("Presseportal: znaleziono %d elementow", len(items))
        events: list[dict] = []
        for item in items:
            parsed = self._parse_pp_item(item)
            if not parsed:
                continue
            full = f"{parsed['title']} {parsed.get('description', '')}".lower()
            if is_transport_related(full, "de"):
                events.append(self._make_de_event(parsed, "Presseportal/Bundespolizei"))
        return events

    def _parse_pp_item(self, item) -> dict | None:
        title_el = item.find(["h3", "h2", "h4"])
        if not title_el:
            link = item.find("a")
            if not link:
                return None
            title_el = link
        title = title_el.get_text(strip=True)
        if not title or len(title) < 5:
            return None

        link_el = item.find("a", href=True)
        href = PRESSEPORTAL_URL
        if link_el:
            h = link_el["href"]
            if h.startswith("/"):
                href = "https://www.presseportal.de" + h

        desc_el = item.find("p")
        description = desc_el.get_text(strip=True) if desc_el else ""

        date_el = item.find(class_=re.compile(r"date|datum|time", re.IGNORECASE))
        date = date_el.get_text(strip=True) if date_el else self._extract_date(item)

        return {"title": title, "link": href, "description": description, "date": date}

    # -- bundespolizei.de parser -----------------------------------------

    def _parse_bundespolizei(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")

        items: list = []
        for selector in _BPOL_SELECTORS:
            items = soup.select(selector)
            if items:
                break
        if not items:
            for link in soup.find_all("a", href=True):
                if "/meldungen/" in link.get("href", "").lower():
                    p = link.find_parent(["div", "li", "article"])
                    if p and p not in items:
                        items.append(p)

        self._logger.info("Bundespolizei.de: znaleziono %d elementow", len(items))
        events: list[dict] = []
        for item in items:
            parsed = self._parse_item(item)  # reuse base class parser
            if not parsed:
                continue
            full = f"{parsed['title']} {parsed.get('description', '')}".lower()
            if is_transport_related(full, "de"):
                events.append(self._make_de_event(parsed, "Bundespolizei"))
        return events

    # -- event builder (with per-source label) ---------------------------

    def _make_de_event(self, parsed: dict, source_label: str) -> dict:
        return {
            "title": parsed.get("title", ""),
            "description": parsed.get("description", ""),
            "date": parsed.get("date", ""),
            "source_url": parsed.get("link", BUNDESPOLIZEI_URL),
            "raw_text": f"{parsed.get('title', '')}\n{parsed.get('description', '')}",
            "country_code": "DE",
            "language": "de",
            "source_name": source_label,
            "trust_score": 1.0,
            "is_official": True,
            "source_type": SourceType.POLICE.value,
            "timestamp": parsed.get("date") or datetime.utcnow().isoformat(),
            "collected_at": datetime.utcnow().isoformat(),
        }

    # -- date extraction (DE-specific classes) ---------------------------

    def _extract_date(self, item) -> str:
        time_el = item.find("time")
        if time_el:
            dt = time_el.get("datetime", "")
            if dt:
                return dt
            return time_el.get_text(strip=True)
        for cls in ["date", "datum", "teaser-date", "c-date"]:
            el = item.find(class_=re.compile(cls, re.IGNORECASE))
            if el:
                return el.get_text(strip=True)
        text = item.get_text()
        m = re.search(r"(\d{1,2}\.\d{1,2}\.\d{4})", text)
        if m:
            return m.group(1)
        m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if m:
            return m.group(1)
        return ""
