"""AustrianPoliceAgent — dual-source scraper (presseportal.de/AT + bmi.gv.at).

Same dual-source pattern as Germany but with Austrian police IDs on
presseportal.de and the BMI (Bundesministerium für Inneres) official site.
"""

import re
from datetime import datetime

from bs4 import BeautifulSoup

from src.agents.base_agent import SourceType
from src.agents.police.base import BasePoliceAgent, PoliceSourceConfig
from src.agents.transport_keywords import is_transport_related

PRESSEPORTAL_AT_URL = "https://www.presseportal.de/blaulicht/nr/56519"
BMI_URL = "https://www.bmi.gv.at/news.aspx"

_CONFIG = PoliceSourceConfig(
    country_code="AT",
    language="de",
    source_name="Polizei \u00d6sterreich",
    source_url=PRESSEPORTAL_AT_URL,
    url_domain="https://www.presseportal.de",
    selectors=(),  # not used — parse() is overridden
    fallback_href_markers=(),
)


class AustrianPoliceAgent(BasePoliceAgent):
    """Dual-source Austrian police scraper.

    Sources:
      1. presseportal.de (Austrian police press IDs)
      2. bmi.gv.at (official BMI news)
    """

    def __init__(self, event_queue=None):
        super().__init__(_CONFIG, event_queue)

    # -- fetch (dual source) ---------------------------------------------

    async def fetch(self) -> str:
        parts: list[str] = []
        for label, url in [
            ("presseportal", PRESSEPORTAL_AT_URL),
            ("bmi", BMI_URL),
        ]:
            try:
                html = await self._fetch_url(url)
                parts.append(f"<!-- SOURCE:{label} -->\n{html}")
            except Exception as e:
                self._logger.warning("%s fetch failed: %s", label, e)
        if not parts:
            raise RuntimeError("Oba zrodla austriackie niedostepne")
        return "\n<!-- SEPARATOR -->\n".join(parts)

    # -- parse (dispatch per source) -------------------------------------

    async def parse(self, raw_data: str) -> list[dict]:
        events: list[dict] = []
        seen: set[str] = set()

        for block in raw_data.split("<!-- SEPARATOR -->"):
            if "SOURCE:presseportal" in block:
                block_events = self._parse_presseportal(block)
            else:
                block_events = self._parse_bmi(block)

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

        self._logger.info("Presseportal AT: znaleziono %d elementow", len(items))
        events: list[dict] = []
        for item in items:
            parsed = self._parse_at_item(item, "https://www.presseportal.de")
            if not parsed:
                continue
            full = f"{parsed['title']} {parsed.get('description', '')}".lower()
            if is_transport_related(full, "de"):
                events.append(
                    self._make_at_event(parsed, "Presseportal/Polizei \u00d6sterreich")
                )
        return events

    # -- BMI parser ------------------------------------------------------

    def _parse_bmi(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        items = (
            soup.select("article")
            or soup.select("div.news-item")
            or soup.select("div.list-item")
            or soup.select("li.list-item")
        )
        if not items:
            items = []
            for link in soup.find_all("a", href=True):
                if "/news/" in link.get("href", "").lower():
                    p = link.find_parent(["div", "li", "article", "section"])
                    if p and p not in items:
                        items.append(p)

        self._logger.info("BMI.gv.at: znaleziono %d elementow", len(items))
        events: list[dict] = []
        for item in items:
            parsed = self._parse_at_item(item, "https://www.bmi.gv.at")
            if not parsed:
                continue
            full = f"{parsed['title']} {parsed.get('description', '')}".lower()
            if is_transport_related(full, "de"):
                events.append(self._make_at_event(parsed, "BMI \u00d6sterreich"))
        return events

    # -- shared item parser (base_url varies per source) -----------------

    def _parse_at_item(self, item, base_url: str) -> dict | None:
        title_el = item.find(["h2", "h3", "h4"])
        if title_el:
            title = title_el.get_text(strip=True)
        else:
            link = item.find("a")
            if not link:
                return None
            title = link.get_text(strip=True)
        if not title or len(title) < 5:
            return None

        link_el = item.find("a", href=True)
        href = base_url
        if link_el:
            h = link_el["href"]
            if h.startswith("/"):
                href = base_url + h
            elif not h.startswith("http"):
                href = base_url + "/" + h
            else:
                href = h

        desc_el = item.find("p")
        if desc_el:
            description = desc_el.get_text(strip=True)
        else:
            full_text = item.get_text(strip=True)
            desc = full_text.replace(title, "").strip()
            description = desc[:500] if desc else ""

        return {
            "title": title, "link": href,
            "description": description, "date": self._extract_at_date(item),
        }

    # -- event builder ---------------------------------------------------

    def _make_at_event(self, parsed: dict, source_label: str) -> dict:
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

    # -- date extraction -------------------------------------------------

    @staticmethod
    def _extract_at_date(item) -> str:
        time_el = item.find("time")
        if time_el:
            dt = time_el.get("datetime", "")
            if dt:
                return dt
            return time_el.get_text(strip=True)
        for cls in ["date", "datum", "news-date"]:
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
